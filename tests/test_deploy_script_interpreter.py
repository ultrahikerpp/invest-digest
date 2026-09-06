"""Regression coverage for deploy.sh's interpreter and rebuild behavior.

Context: cmd_deploy() builds the site in-process with the venv's Python
(which has yfinance -> real fundamentals enrichment), then shells out to
deploy.sh, which used to hardcode `python3 build_site.py`. On this machine
bare `python3` is a different interpreter without yfinance installed, so
deploy.sh silently rebuilt the site a second time with fundamentals
skipped, overwriting the enriched output before it was ever committed.
cmd_approve() calls deploy.sh directly (no prior build), so deploy.sh must
still be able to build on its own -- it just needs to prefer the venv's
Python when one exists, and skip rebuilding entirely when told the caller
already built.
"""
import os
import stat
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import runner

DEPLOY_SH = Path(__file__).parent.parent / "deploy.sh"


def _make_fake_project(tmp_path: Path, *, with_venv: bool) -> Path:
    """Build an isolated copy of the repo shape deploy.sh expects."""
    project = tmp_path / "project"
    project.mkdir()
    (project / DEPLOY_SH.name).write_text(DEPLOY_SH.read_text(encoding="utf-8"), encoding="utf-8")
    (project / DEPLOY_SH.name).chmod(0o755)

    # build_site.py stub: record which interpreter actually ran it.
    (project / "build_site.py").write_text(
        "import sys, pathlib\n"
        "marker = pathlib.Path(__file__).parent / 'ran_with.txt'\n"
        "marker.write_text(sys.executable)\n"
        "docs_data = pathlib.Path(__file__).parent / 'docs' / 'data'\n"
        "docs_data.mkdir(parents=True, exist_ok=True)\n"
        "(docs_data / 'episodes.json').write_text('[]')\n",
        encoding="utf-8",
    )

    if with_venv:
        venv_bin = project / "venv" / "bin"
        venv_bin.mkdir(parents=True)
        fake_python = venv_bin / "python3"
        fake_python.write_text(f"#!/bin/bash\nexec \"{sys.executable}\" \"$@\"\n", encoding="utf-8")
        fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=project, check=True)
    (project / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=project, check=True)
    # deploy.sh's `git push` step is unreachable in these tests: SKIP_BUILD
    # tests never reach it (no docs/ change to commit), and the with_venv
    # build test only asserts on ran_with.txt / stdout before push would run.

    return project


def test_deploy_sh_prefers_venv_python_when_present(tmp_path):
    project = _make_fake_project(tmp_path, with_venv=True)

    result = subprocess.run(
        ["bash", "deploy.sh"], cwd=project, capture_output=True, text=True,
    )

    assert (project / "build_site.py").parent.joinpath("ran_with.txt").exists(), (
        f"build_site.py never ran.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    ran_with = (project / "ran_with.txt").read_text(encoding="utf-8")
    assert ran_with == sys.executable, (
        "deploy.sh must prefer the project's own venv/bin/python3 (which shells out "
        f"to {sys.executable} in this test) over bare `python3` on PATH; got {ran_with!r}"
    )


def test_deploy_sh_falls_back_to_system_python_without_venv(tmp_path):
    project = _make_fake_project(tmp_path, with_venv=False)

    result = subprocess.run(
        ["bash", "deploy.sh"], cwd=project, capture_output=True, text=True,
    )

    ran_with = (project / "ran_with.txt").read_text(encoding="utf-8")
    assert ran_with != sys.executable, (
        "without a venv, deploy.sh should fall through to whatever `python3` is on PATH, "
        "not the fake venv interpreter"
    )


def test_deploy_sh_skips_build_when_skip_build_env_set(tmp_path):
    project = _make_fake_project(tmp_path, with_venv=True)
    # Caller (cmd_deploy) already built -- docs/data/episodes.json must
    # already exist or deploy.sh's own post-build check would fail it.
    docs_data = project / "docs" / "data"
    docs_data.mkdir(parents=True)
    (docs_data / "episodes.json").write_text("[]", encoding="utf-8")

    env = {**os.environ, "SKIP_BUILD": "1"}
    subprocess.run(["bash", "deploy.sh"], cwd=project, capture_output=True, text=True, env=env)

    assert not (project / "ran_with.txt").exists(), "SKIP_BUILD=1 must skip re-running build_site.py"


def test_cmd_deploy_tells_deploy_sh_to_skip_the_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "cmd_build", lambda: None)
    monkeypatch.setattr(runner, "WEEKLY_DIR", tmp_path / "weekly")

    captured = {}

    def fake_run(args, cwd=None, env=None):
        captured["env"] = env
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner, "subprocess", types.SimpleNamespace(run=fake_run))

    try:
        runner.cmd_deploy()
    except SystemExit as e:
        assert e.code == 0

    assert captured["env"] is not None, "cmd_deploy must pass an env to deploy.sh"
    assert captured["env"].get("SKIP_BUILD") == "1", (
        "cmd_deploy already built the site itself -- deploy.sh must not build it again"
    )
