"""Drawing the images to share: only the ones whose content changed, several at a time.

A job is one image: the renderer to call, its arguments (plain data: the API's payloads, the stamp,
the theme) and where its file goes. Each job's fingerprint is a hash of those arguments and of the
code that draws it (its renderer's module and every project module that imports in turn, and the
fonts), so an image is redrawn when what it shows or how it's drawn changes, and kept otherwise. A
change to the page wording (``static_pages``) redraws the images that draw its sentences, not the
region maps; a change to the maps redraws only the maps. The fingerprints are kept in ``state/images.json``
under the share folder (which nginx doesn't serve).

The jobs left to draw run in separate processes (``SHARE_IMAGE_WORKERS``, default the CPU count, at
most 2), each drawing one image at a time, at full quality: the same renderer, the same PNG settings.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import logging
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from functools import cache
from multiprocessing import get_context
from pathlib import Path

# The renderers, as (module, function): the function takes a job's kwargs and returns its pages (or one
# image). A job names its renderer this way (not the function itself) so a worker process can import it.
REGION_OVERVIEW = ("backend.helpers.region_image", "render_region_overview")
REGION_SCENARIOS = ("backend.helpers.region_image", "render_region_scenarios")
TEAM_SEASON = ("backend.helpers.team_image", "render_team_season")
TEAM_SCENARIOS = ("backend.helpers.team_image", "render_team_scenarios")
CLASS_REGIONS = ("backend.helpers.region_map_image", "render_class_regions")
TEAM_REGION = ("backend.helpers.region_map_image", "render_team_region")
TEAM_REGIONS_COMPARED = ("backend.helpers.region_map_image", "render_team_regions_compared")
CLASS_REGIONS_COMPARED = ("backend.helpers.region_map_image", "render_class_regions_compared")
CLASS_REGIONS_CARD = ("backend.helpers.region_map_image", "render_class_regions_card")
TEAM_REGION_CARD = ("backend.helpers.region_map_image", "render_team_region_card")
# The link previews and the bracket images, each one picture (the renderer returns an image, not a list).
SITE_CARD = ("backend.helpers.share_cards", "render_site_card")
CLASS_CARD = ("backend.helpers.share_cards", "render_class_card")
REGION_CARD = ("backend.helpers.share_cards", "render_region_card")
TEAM_CARD = ("backend.helpers.share_cards", "render_team_card")
BRACKET_CARD = ("backend.helpers.share_cards", "render_bracket_card")
TEAM_BRACKET_CARD = ("backend.helpers.share_cards", "render_team_bracket_card")
BRACKET_IMAGE = ("backend.helpers.bracket_image", "render_bracket_image")
BRACKET_CARD_IMAGE = ("backend.helpers.bracket_image", "render_bracket_card_image")

MANIFEST = Path("state") / "images.json"
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageJob:
    """One image to draw: its file (relative to the share folder), its *renderer* (module, function) and the
    renderer's *kwargs*."""

    path: str
    renderer: tuple[str, str]
    kwargs: dict = field(hash=False)


@cache
def code_modules(module: str) -> tuple[str, ...]:
    """The project's modules *module* draws with: itself and every ``backend`` module it imports,
    directly or through another (read from their source, so nothing is imported)."""
    seen: set[str] = set()

    def visit(name: str) -> None:
        """Add *name* and what it imports, if it's a module not seen yet."""
        if name in seen:
            return
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            spec = None
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            return  # a name imported from a module (``from backend.x import y``), not a module itself
        seen.add(name)
        for node in ast.walk(ast.parse(Path(spec.origin).read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend"):
                visit(node.module)
                for alias in node.names:
                    visit(f"{node.module}.{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("backend"):
                        visit(alias.name)

    visit(module)
    return tuple(sorted(seen))


@cache
def code_fingerprint(module: str) -> str:
    """A hash of the code an image drawn by *module* depends on (``code_modules``, and this module), the
    fonts it draws with, and the county lines when it draws the map. A change to any of them redraws
    that renderer's images, and only those."""
    from backend.helpers.region_map import COUNTIES_PATH
    from backend.helpers.share_cards import FONT_DIR

    h = hashlib.sha256()
    for name in sorted({*code_modules(module), __name__}):
        h.update(name.encode())
        h.update(Path(importlib.util.find_spec(name).origin).read_bytes())
    if "backend.helpers.region_map" in code_modules(module):
        h.update(COUNTIES_PATH.read_bytes())  # the map the region maps draw
    for font in sorted(FONT_DIR.glob("*")):
        if font.suffix.lower() in {".otf", ".ttf", ".woff2"}:
            h.update(font.name.encode())
            h.update(str(font.stat().st_size).encode())
    return h.hexdigest()


def job_fingerprint(job: ImageJob, code: str) -> str:
    """A hash of everything the image shows and how it's drawn."""
    body = json.dumps(
        {"renderer": list(job.renderer), "kwargs": job.kwargs}, sort_keys=True, default=str, ensure_ascii=False
    )
    return hashlib.sha256(f"{code}\n{body}".encode()).hexdigest()


def _write_png_atomic(path: Path, image) -> None:
    """Write a Pillow image as an optimized PNG, atomically (a reader never sees half a file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(fd)
    try:
        image.save(tmp, "PNG", optimize=True)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def page_paths(path: str, pages: int) -> list[str]:
    """An image's files: its path for one page; ``…-1.png``, ``…-2.png`` … for more."""
    if pages == 1:
        return [path]
    stem = path.removesuffix(".png")
    return [f"{stem}-{i}.png" for i in range(1, pages + 1)]


def _draw(args: tuple[str, str, tuple[str, str], dict]) -> list[str]:
    """Draw one job (in a worker process) and write its pages; returns the files written, relative."""
    out_dir, path, (module, name), kwargs = args
    pages = getattr(importlib.import_module(module), name)(**kwargs)
    if not isinstance(pages, list):  # a renderer that draws one picture
        pages = [pages]
    files = page_paths(path, len(pages))
    for rel, image in zip(files, pages, strict=True):
        _write_png_atomic(Path(out_dir) / rel, image)
    return files


def _workers() -> int:
    """How many images to draw at once."""
    configured = os.environ.get("SHARE_IMAGE_WORKERS")
    if configured:
        return max(1, int(configured))
    return max(1, min(2, os.cpu_count() or 1))


def draw_images(
    out_dir: Path, jobs: list[ImageJob], prune: list[str] = (), files_out: dict[str, list[str]] | None = None
) -> dict[str, int]:
    """Draw the *jobs* whose fingerprint changed (or whose files are missing), keep the rest, and remove
    any other PNG in the *prune* folders (relative to *out_dir*): images no job makes any more. A job
    whose renderer returns no pages (nothing to show) makes no file.

    Returns {"drawn", "kept", "removed"}; *files_out*, when given, gets each job's files (path -> pages).
    """
    manifest_path = out_dir / MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        manifest = {}
    todo, kept, files_for = [], 0, {}
    for job in jobs:
        fp = job_fingerprint(job, code_fingerprint(job.renderer[0]))
        entry = manifest.get(job.path) or {}
        files = entry.get("files") or []
        if entry.get("fp") == fp and "files" in entry and all((out_dir / f).exists() for f in files):
            kept += 1
            files_for[job.path] = entry
            continue
        todo.append((job, fp))
    args = [(str(out_dir), job.path, job.renderer, job.kwargs) for job, _ in todo]
    results = None
    if len(args) > 1 and _workers() > 1:
        try:
            with ProcessPoolExecutor(max_workers=_workers(), mp_context=get_context("spawn")) as pool:
                results = list(pool.map(_draw, args))
        except BrokenProcessPool:
            _log.warning("Drawing in parallel failed; drawing the %d images one at a time", len(args))
    if results is None:
        results = [_draw(a) for a in args]
    for (job, fp), files in zip(todo, results, strict=True):
        old = set((manifest.get(job.path) or {}).get("files") or [])
        for stale in old - set(files):  # fewer pages than last time
            (out_dir / stale).unlink(missing_ok=True)
        files_for[job.path] = {"fp": fp, "files": files}
    if files_out is not None:
        files_out.update({path: list(e["files"]) for path, e in files_for.items()})
    keep = {f for e in files_for.values() for f in e["files"]}
    removed = 0
    for folder in prune:
        for png in (out_dir / folder).glob("*.png") if (out_dir / folder).is_dir() else []:
            rel = str(png.relative_to(out_dir))
            if rel not in keep:
                png.unlink()
                removed += 1
    # Entries for files outside the pruned folders stay; the rest are what was just made or kept.
    pruned = tuple(f.rstrip("/") + "/" for f in prune)
    manifest = {k: v for k, v in manifest.items() if not k.startswith(pruned)} | files_for
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=manifest_path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(manifest, f, indent=0, sort_keys=True)
    os.replace(tmp, manifest_path)
    return {"drawn": len(todo), "kept": kept, "removed": removed}


def sweep(out_dir: Path, folders: list[str], keep: set[str]) -> int:
    """Remove every PNG under the *folders* (relative to *out_dir*, searched all the way down) that isn't in
    *keep*, the files this run made or kept, and the folders that leaves empty; drop the manifest's entries
    for what's gone. So images nothing makes any more (a season the site no longer has, a region that went
    away in a realignment, a team that moved) don't pile up. Returns how many files were removed."""
    removed = 0
    for folder in folders:
        root = out_dir / folder
        if not root.is_dir():
            continue
        for png in sorted(root.rglob("*.png")):
            if str(png.relative_to(out_dir)) not in keep:
                png.unlink()
                removed += 1
        for sub in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            if not any(sub.iterdir()):
                sub.rmdir()
    manifest_path = out_dir / MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return removed
    # An entry goes with its files; one that made none (nothing to show, as a region's scenarios once its
    # games are played) stays, so its job isn't drawn again for nothing.
    swept = tuple(f.rstrip("/") + "/" for f in folders)
    kept = {
        path: entry
        for path, entry in manifest.items()
        if not path.startswith(swept) or not entry.get("files") or any(f in keep for f in entry["files"])
    }
    if kept != manifest:
        fd, tmp = tempfile.mkstemp(dir=manifest_path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(kept, f, indent=0, sort_keys=True)
        os.replace(tmp, manifest_path)
    return removed
