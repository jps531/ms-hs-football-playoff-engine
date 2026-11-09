"""scripts/deploy.sh and scripts/deploy_ssh.sh, run for real against a scratch server checkout, with docker and
curl replaced by recorders: what a deploy does in order, that a failed check rolls back, and what it refuses."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

DOCKER = r"""#!/usr/bin/env bash
# Record each call with the IMAGE_TAG it saw; answer the pipeline checks and `ps -a`.
echo "IMAGE_TAG=${IMAGE_TAG:-} $*" >> "$CALLS"
case "$*" in
  *"exec -T prefect-worker"*) echo "${RUNNING_FLOWS:-0}" ;;
  *"exec -T db"*) echo "0" ;;
  *"ps -a"*) printf 'api running\nnginx running\n' ;;
esac
"""
CURL = r"""#!/usr/bin/env bash
# Healthy unless the checkout's marker says otherwise (the "broken" commit).
[ -f "$SERVER/broken" ] && exit 22
exit 0
"""


def _git(cwd, *args):
    """Run git, returning its output."""
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def server(tmp_path):
    """A 'GitHub' repository with three commits on main (good, good, broken) and one on a branch, and the
    server's clone checked out at the first, with recording docker and curl on PATH."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "user.email", "t@example.com")
    _git(origin, "config", "user.name", "T")
    (origin / "scripts").mkdir()
    for name in ("deploy.sh", "deploy_ssh.sh"):
        shutil.copy(ROOT / "scripts" / name, origin / "scripts" / name)
    (origin / "scripts" / "migrate.py").write_text(
        '#!/bin/sh\necho "migrate $(git rev-parse --short HEAD)" >> "$CALLS"\n'
    )
    (origin / "scripts" / "migrate.py").chmod(0o755)
    (origin / "nginx").mkdir()
    (origin / "nginx" / "nginx.conf").write_text("one\n")
    _git(origin, "add", ".")
    _git(origin, "commit", "-q", "-m", "first")
    shas = {"first": _git(origin, "rev-parse", "HEAD")}
    (origin / "nginx" / "nginx.conf").write_text("two\n")
    _git(origin, "commit", "-q", "-am", "second: nginx.conf changed")
    shas["second"] = _git(origin, "rev-parse", "HEAD")
    (origin / "broken").write_text("x\n")
    _git(origin, "add", "broken")
    _git(origin, "commit", "-q", "-m", "broken")
    shas["broken"] = _git(origin, "rev-parse", "HEAD")
    _git(origin, "checkout", "-q", "-b", "feature", shas["first"])
    (origin / "branch-only").write_text("x\n")
    _git(origin, "add", "branch-only")
    _git(origin, "commit", "-q", "-m", "a branch's commit")
    shas["branch"] = _git(origin, "rev-parse", "HEAD")
    _git(origin, "checkout", "-q", "main")

    clone = tmp_path / "server"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "checkout", "-q", "--detach", shas["first"])
    (clone / ".deployed-image-tag").write_text(shas["first"] + "\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER), ("curl", CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    calls = tmp_path / "calls.log"
    calls.touch()
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CALLS": str(calls),
        "SERVER": str(clone),
        "DEPLOY_LOCK": str(tmp_path / "deploy.lock"),
        "DEPLOY_HEALTH_TRIES": "2",
        "DEPLOY_HEALTH_PAUSE": "0",
        "DEPLOY_WAIT_MINUTES": "0",
    }

    def deploy(sha, script="deploy.sh", **extra):
        """Run the server's script for *sha*; (exit code, output)."""
        run_env = {**env, **extra}
        args = [str(clone / "scripts" / script)] + ([sha] if script == "deploy.sh" else [])
        if script == "deploy_ssh.sh":
            run_env["SSH_ORIGINAL_COMMAND"] = sha
        done = subprocess.run(args, cwd=clone, env=run_env, capture_output=True, text=True, check=False)
        return done.returncode, done.stdout + done.stderr

    return type(
        "Server",
        (),
        {
            "deploy": staticmethod(deploy),
            "origin": origin,
            "shas": shas,
            "head": staticmethod(lambda: _git(clone, "rev-parse", "HEAD")),
            "tag": staticmethod(lambda: (clone / ".deployed-image-tag").read_text().strip()),
            "calls": staticmethod(lambda: calls.read_text().splitlines()),
        },
    )


def test_a_deploy_pulls_migrates_restarts_and_records_the_commit(server):
    sha = server.shas["second"]
    code, out = server.deploy(sha)
    assert code == 0, out
    assert server.head() == sha and server.tag() == sha
    calls = server.calls()
    steps = [c for c in calls if " pull " in c or c.startswith("migrate") or " up -d" in c]
    assert (
        steps[0] == f"IMAGE_TAG={sha} compose --env-file .env.local --profile local-db pull --quiet api prefect-worker"
    )
    assert steps[1] == f"migrate {sha[:7]}"
    assert steps[2] == f"IMAGE_TAG={sha} compose --env-file .env.local --profile local-db up -d --no-build"
    assert "--force-recreate nginx" in steps[3]  # nginx.conf changed between the two commits
    assert f"Deployed {sha[:7]}" in out


def test_a_failed_check_rolls_back_to_the_previous_commit_and_images(server):
    first, broken = server.shas["first"], server.shas["broken"]
    code, out = server.deploy(broken)
    assert code == 1
    assert server.head() == first and server.tag() == first
    assert f"rolling back to {first[:7]}" in out and f"Rolled back to {first[:7]}; {broken[:7]} was not deployed" in out
    ups = [c for c in server.calls() if " up -d --no-build" in c and "nginx" not in c]
    assert ups[-1].startswith(f"IMAGE_TAG={first} ")


def test_a_commit_not_on_main_is_never_deployed(server):
    code, out = server.deploy(server.shas["branch"])
    assert code == 1 and "isn't on origin/main" in out
    assert server.head() == server.shas["first"] and not [c for c in server.calls() if " up " in c]


def test_it_waits_for_running_pipelines_and_gives_up_after_the_limit(server):
    code, out = server.deploy(server.shas["second"], RUNNING_FLOWS="1")
    assert code == 1 and "Pipelines still running" in out
    assert server.head() == server.shas["first"] and not [c for c in server.calls() if " pull " in c]


@pytest.mark.parametrize("sent", ["", "main", "abc123", "rm -rf /", "0" * 39, "g" * 40])
def test_the_deploy_key_runs_only_a_deploy_of_one_commit(server, sent):
    """Whatever an SSH client asks for, the forced command only passes a 40-character sha to deploy.sh."""
    code, out = server.deploy(sent, script="deploy_ssh.sh")
    assert code == 2 and "This key only deploys" in out and server.calls() == []


def test_the_deploy_key_deploys_a_sha(server):
    sha = server.shas["second"]
    code, out = server.deploy(sha, script="deploy_ssh.sh")
    assert code == 0, out
    assert server.head() == sha


def test_the_workflow_deploys_main_after_ci_and_waits_for_approval():
    """Only after CI passes on a push to main in this repository; the deploy job is in the protected
    production environment; images are pushed with packages: write on that job only."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "deploy.yml").read_text())
    on = workflow[True]
    assert on["workflow_run"] == {"workflows": ["CI"], "types": ["completed"], "branches": ["main"]}
    images, deploy = workflow["jobs"]["images"], workflow["jobs"]["deploy"]
    condition = " ".join(images["if"].split())
    assert "github.event.workflow_run.event == 'push'" in condition
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in condition
    assert workflow["permissions"] == {"contents": "read"}
    assert images["permissions"] == {"contents": "read", "packages": "write"}
    assert deploy["environment"]["name"] == "production" and deploy["needs"] == "images"
    assert "StrictHostKeyChecking=yes" in deploy["steps"][0]["run"]


def test_a_commit_that_rewrites_the_deploy_script_still_deploys_cleanly(server):
    """The running script checks out a commit that changes it (here, 200 lines added at its top), and the
    run carries on as it started."""
    script = server.origin / "scripts" / "deploy.sh"
    lines = script.read_text().split("\n")
    script.write_text("\n".join([lines[0], *["# padding"] * 200, *lines[1:]]))
    _git(server.origin, "rm", "-q", "broken")  # (built on the broken commit: mend it too)
    _git(server.origin, "commit", "-q", "-am", "the deploy script changed")
    sha = _git(server.origin, "rev-parse", "HEAD")
    code, out = server.deploy(sha)
    assert code == 0, out
    assert server.head() == sha and f"Deployed {sha[:7]}" in out
