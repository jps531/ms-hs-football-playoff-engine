"""Drawing the images to share: only the ones whose content changed, several at a time.

A job is one image: the renderer to call, its arguments (plain data: the API's payloads, the stamp,
the theme) and where its file goes. Each job's fingerprint is a hash of those arguments and of the
drawing code itself (the renderer modules and the fonts), so an image is redrawn when what it shows
or how it's drawn changes, and kept otherwise. The fingerprints are kept in ``state/images.json``
under the share folder (which nginx doesn't serve).

The jobs left to draw run in separate processes (``SHARE_IMAGE_WORKERS``, default the CPU count, at
most 2), each drawing one image at a time, at full quality: the same renderer, the same PNG settings.
"""

from __future__ import annotations

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
from multiprocessing import get_context
from pathlib import Path

# The renderers, as (module, function): the function takes a job's kwargs and returns its pages. A job
# names its renderer this way (not the function itself) so a worker process can import it.
REGION_OVERVIEW = ("backend.helpers.region_image", "render_region_overview")
REGION_SCENARIOS = ("backend.helpers.region_image", "render_region_scenarios")
TEAM_SEASON = ("backend.helpers.team_image", "render_team_season")
TEAM_SCENARIOS = ("backend.helpers.team_image", "render_team_scenarios")

# The code an image's look depends on; a change to any of it redraws every image.
_CODE = (
    "backend.helpers.region_image",
    "backend.helpers.team_image",
    "backend.helpers.bracket_image",
    "backend.helpers.share_cards",
    "backend.helpers.static_pages",
    "backend.helpers.image_jobs",
)
MANIFEST = Path("state") / "images.json"
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageJob:
    """One image to draw: its file (relative to the share folder), its *renderer* (module, function) and the
    renderer's *kwargs*."""

    path: str
    renderer: tuple[str, str]
    kwargs: dict = field(hash=False)


def code_fingerprint() -> str:
    """A hash of the drawing code and the fonts it draws with."""
    from backend.helpers.share_cards import FONT_DIR

    h = hashlib.sha256()
    for module in _CODE:
        h.update(Path(importlib.util.find_spec(module).origin).read_bytes())
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
    code = code_fingerprint()
    todo, kept, files_for = [], 0, {}
    for job in jobs:
        fp = job_fingerprint(job, code)
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
