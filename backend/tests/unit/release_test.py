"""scripts/release.py: each version's notes from CHANGELOG.md, and where each version first appeared on main,
for the Release workflow (.github/workflows/release.yml)."""

import importlib.util
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)

CHANGELOG = """# Changelog

Intro.

## 1.2.0

- **Big.** A feature.
- A fix.

## 1.1.0

- Older.
"""


def test_a_versions_notes_are_its_entry():
    """Under its heading, up to the next one; the last entry runs to the end; a missing one is None."""
    assert release.notes(CHANGELOG, "1.2.0") == "- **Big.** A feature.\n- A fix."
    assert release.notes(CHANGELOG, "1.1.0") == "- Older."
    assert release.notes(CHANGELOG, "1.1") is None and release.notes(CHANGELOG, "9.9.9") is None


def test_the_current_version_has_its_notes():
    """The workflow releases backend/version.py's version with its CHANGELOG entry, so it must have one."""
    version = release.version_in((ROOT / "backend" / "version.py").read_text())
    assert version and release.notes((ROOT / "CHANGELOG.md").read_text(), version)
    assert release.main(["version"]) == 0


def test_where_each_version_first_appeared_on_main(tmp_path):
    """The main line's first commit stating each version, oldest first; a branch merged in counts at its
    merge, not at its own commit."""

    def git(*args):
        """Run git in the scratch repository."""
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def commit(version, message):
        """Write backend/version.py stating *version* and commit it."""
        (tmp_path / "backend").mkdir(exist_ok=True)
        (tmp_path / "backend" / "version.py").write_text(f'"""{message}"""\n\nVERSION = "{version}"\n')
        git("add", ".")
        git("commit", "-q", "-m", message)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    commit("1.0.0", "first")
    git("checkout", "-q", "-b", "feature")
    commit("1.1.0", "bump on a branch")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "feature", "-m", "merge the feature")
    commit("1.1.0", "unrelated change, same version")
    sha = lambda ref: subprocess.run(  # noqa: E731
        ["git", "rev-parse", ref], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert release.history("main", cwd=tmp_path) == [("1.0.0", sha("main~2")), ("1.1.0", sha("main~1"))]


def test_the_workflow_releases_only_after_ci_passes_on_main():
    """Triggered by CI on main, and only for a passing push in this repository (never a pull request's run)."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
    on = workflow[True]  # YAML reads the key "on" as True
    assert on["workflow_run"] == {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]}
    condition = " ".join(workflow["jobs"]["release"]["if"].split())
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in condition
    assert workflow["permissions"] == {"contents": "write"}
