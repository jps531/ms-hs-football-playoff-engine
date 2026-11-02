"""Drawing the images to share: only what changed, the same at any number of workers."""

import json

from PIL import Image

from backend.helpers import image_jobs
from backend.helpers.image_jobs import MANIFEST, ImageJob, draw_images, page_paths

SOLID = ("backend.tests.unit.image_jobs_test", "solid")


def solid(color: str, pages: int = 1) -> list[Image.Image]:
    """A tiny image (or several) in one color: a stand-in renderer."""
    return [Image.new("RGB", (8, 10), color) for _ in range(pages)]


def _jobs(**colors: str) -> list[ImageJob]:
    """One job per name: region/2026/<name>.png in that color."""
    return [ImageJob(f"region/2026/{name}.png", SOLID, {"color": c}) for name, c in colors.items()]


def test_an_unchanged_image_is_kept_and_a_changed_one_redrawn(tmp_path):
    assert draw_images(tmp_path, _jobs(a="red", b="blue"), prune=["region/2026"]) == {
        "drawn": 2,
        "kept": 0,
        "removed": 0,
    }
    first = (tmp_path / "region/2026/a.png").stat().st_mtime_ns
    assert draw_images(tmp_path, _jobs(a="red", b="blue"), prune=["region/2026"]) == {
        "drawn": 0,
        "kept": 2,
        "removed": 0,
    }
    assert (tmp_path / "region/2026/a.png").stat().st_mtime_ns == first  # not written again
    assert draw_images(tmp_path, _jobs(a="red", b="green"), prune=["region/2026"])["drawn"] == 1
    assert Image.open(tmp_path / "region/2026/b.png").getpixel((0, 0)) == (0, 128, 0)
    # A missing file is drawn again, whatever the record says.
    (tmp_path / "region/2026/a.png").unlink()
    assert draw_images(tmp_path, _jobs(a="red", b="green"), prune=["region/2026"])["drawn"] == 1


def test_a_change_to_the_drawing_code_redraws_everything(tmp_path, monkeypatch):
    draw_images(tmp_path, _jobs(a="red", b="blue"))
    monkeypatch.setattr(image_jobs, "code_fingerprint", lambda: "different code")
    assert draw_images(tmp_path, _jobs(a="red", b="blue"))["drawn"] == 2


def test_images_no_job_makes_are_removed(tmp_path):
    draw_images(tmp_path, _jobs(a="red", b="blue"), prune=["region/2026"])
    (tmp_path / "region/2025").mkdir(parents=True)
    (tmp_path / "region/2025/old.png").write_bytes(b"x")  # outside the pruned folder: left alone
    assert draw_images(tmp_path, _jobs(a="red"), prune=["region/2026"])["removed"] == 1
    assert sorted(p.name for p in (tmp_path / "region/2026").iterdir()) == ["a.png"]
    assert (tmp_path / "region/2025/old.png").exists()
    manifest = json.loads((tmp_path / MANIFEST).read_text())
    assert list(manifest) == ["region/2026/a.png"]


def test_an_image_of_several_pages_numbers_them_and_drops_pages_it_no_longer_has(tmp_path):
    assert page_paths("region/2026/x.png", 1) == ["region/2026/x.png"]
    assert page_paths("region/2026/x.png", 2) == ["region/2026/x-1.png", "region/2026/x-2.png"]
    job = [ImageJob("region/2026/x.png", SOLID, {"color": "red", "pages": 3})]
    draw_images(tmp_path, job, prune=["region/2026"])
    assert sorted(p.name for p in (tmp_path / "region/2026").iterdir()) == ["x-1.png", "x-2.png", "x-3.png"]
    job = [ImageJob("region/2026/x.png", SOLID, {"color": "red", "pages": 2})]
    draw_images(tmp_path, job, prune=["region/2026"])
    assert sorted(p.name for p in (tmp_path / "region/2026").iterdir()) == ["x-1.png", "x-2.png"]


def test_drawing_in_parallel_makes_the_same_files(tmp_path, monkeypatch):
    jobs = _jobs(a="red", b="blue", c="green", d="white")
    monkeypatch.setenv("SHARE_IMAGE_WORKERS", "1")
    draw_images(tmp_path / "one", jobs)
    monkeypatch.setenv("SHARE_IMAGE_WORKERS", "2")
    assert draw_images(tmp_path / "two", jobs)["drawn"] == 4
    for name in "abcd":
        one = (tmp_path / "one" / f"region/2026/{name}.png").read_bytes()
        assert one == (tmp_path / "two" / f"region/2026/{name}.png").read_bytes()
    assert not list(tmp_path.rglob("*.tmp"))


def test_a_broken_worker_pool_still_draws_every_image(tmp_path, monkeypatch):
    """If the worker processes can't run, the images are drawn one at a time instead of not at all."""
    from concurrent.futures.process import BrokenProcessPool

    class Broken:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise BrokenProcessPool("no workers")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(image_jobs, "ProcessPoolExecutor", Broken)
    monkeypatch.setenv("SHARE_IMAGE_WORKERS", "2")
    assert draw_images(tmp_path, _jobs(a="red", b="blue"))["drawn"] == 2
    assert (tmp_path / "region/2026/a.png").exists() and (tmp_path / "region/2026/b.png").exists()


def test_an_image_with_nothing_to_show_makes_no_file_and_says_which_files_each_made(tmp_path):
    jobs = [*_jobs(a="red"), ImageJob("region/2026/none.png", SOLID, {"color": "red", "pages": 0})]
    files: dict = {}
    assert draw_images(tmp_path, jobs, prune=["region/2026"], files_out=files)["drawn"] == 2
    assert files == {"region/2026/a.png": ["region/2026/a.png"], "region/2026/none.png": []}
    assert sorted(p.name for p in (tmp_path / "region/2026").iterdir()) == ["a.png"]
    # Unchanged, it's kept (not drawn again), like any other.
    assert draw_images(tmp_path, jobs, prune=["region/2026"])["kept"] == 2
