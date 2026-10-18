from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from presentation_sanity import pages
from presentation_sanity.cli import main

PYPROJECT = """\
[project]
name = "talks"
dependencies = [
    "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.4.0",
]

[dependency-groups]
manim = ["presentation-sanity[manim]"]

[tool.uv]
default-groups = ["manim"]
"""

OLD_PYPROJECT = """\
[project]
name = "talks"
dependencies = [
    "presentation-sanity[manim] @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.3.0",
]
"""


@pytest.fixture
def deployable(project: Path) -> Path:
    (project / "pyproject.toml").write_text(PYPROJECT)
    (project / "uv.lock").write_text("")
    (project / "package-lock.json").write_text("{}")
    return project


def workflow(root: Path) -> dict:
    return yaml.safe_load((root / pages.WORKFLOW_PATH).read_text())


def test_pages_init_writes_the_workflow(deployable: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(deployable)
    assert main(["pages", "init"]) == 0
    wf = workflow(deployable)
    assert wf[True]["push"]["branches"] == ["main"]  # YAML 1.1 reads `on:` as True
    assert wf["permissions"] == {"contents": "read", "pages": "write", "id-token": "write"}

    steps = wf["jobs"]["build"]["steps"]
    uses = [s["uses"] for s in steps if "uses" in s]
    assert uses == [
        "actions/checkout@v7", "actions/configure-pages@v6", "astral-sh/setup-uv@v10.3.0",
        "actions/setup-node@v7", "actions/upload-pages-artifact@v5",
    ]
    runs = " ".join(s.get("run", "") for s in steps)
    assert "uv sync --locked --no-default-groups" in runs
    assert "npm ci" in runs
    assert "--skip-manim --skip-figures" in runs
    assert '--base "${{ steps.pages.outputs.base_path }}/"' in runs
    assert steps[-1]["with"]["path"] == "site"
    assert "if" not in wf["jobs"]["build"]

    deploy = wf["jobs"]["deploy"]
    assert deploy["needs"] == "build" and deploy["environment"]["name"] == "github-pages"
    assert deploy["steps"][0]["uses"] == "actions/deploy-pages@v5"

    out = capsys.readouterr().out
    assert "PUBLIC" in out and "build_type=workflow" in out


def test_pages_init_options(deployable: Path) -> None:
    pages.pages_init(deployable, branch="trunk", only_repo="lab/talks")
    wf = workflow(deployable)
    assert wf[True]["push"]["branches"] == ["trunk"]
    assert wf["jobs"]["build"]["if"] == "github.repository == 'lab/talks'"
    with pytest.raises(pages.PagesError):
        pages.pages_init(deployable, only_repo="not a repo", force=True)


def test_pages_init_never_overwrites_without_force(deployable: Path) -> None:
    pages.pages_init(deployable)
    (deployable / pages.WORKFLOW_PATH).write_text("# mine\n")
    with pytest.raises(pages.PagesError, match="--force"):
        pages.pages_init(deployable)
    pages.pages_init(deployable, force=True)
    assert "configure-pages" in (deployable / pages.WORKFLOW_PATH).read_text()


def test_pages_init_refuses_manim_in_main_dependencies(project: Path) -> None:
    (project / "pyproject.toml").write_text(OLD_PYPROJECT)
    with pytest.raises(pages.PagesError, match="dependency-groups"):
        pages.pages_init(project)
    assert not (project / pages.WORKFLOW_PATH).exists()


def test_pages_init_outside_a_project(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["pages", "init"]) == 1
    assert "presentation-sanity init" in capsys.readouterr().err


def test_notes_for_missing_locks_and_renders(deployable: Path, write) -> None:
    (deployable / "uv.lock").unlink()
    write({"manifest.yaml": (deployable / "manifest.yaml").read_text() + (
        "scenes:\n  intro:\n    source: scenes/intro.py\n    class: IntroScene\n")})
    notes = pages.pages_init(deployable).notes
    assert any("uv.lock" in n for n in notes)
    assert any("public/manim/intro.webm" in n and "not rendered" in n for n in notes)


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_notes_for_gitignored_renders(deployable: Path, write) -> None:
    subprocess.run(["git", "init", "-q"], cwd=deployable, check=True)
    write({
        "manifest.yaml": (deployable / "manifest.yaml").read_text() + (
            "scenes:\n  intro:\n    source: scenes/intro.py\n    class: IntroScene\n"),
        ".gitignore": "public/manim/*.webm\n",
        "public/manim/intro.webm": "video",
    })
    notes = pages.pages_init(deployable).notes
    assert any("gitignored" in n and "public/manim/intro.webm" in n for n in notes)


def test_manim_dependency_detection() -> None:
    assert pages.manim_in_main_dependencies(OLD_PYPROJECT)
    assert not pages.manim_in_main_dependencies(PYPROJECT)


def test_template_snapshot_is_deployable() -> None:
    """The project `init` creates passes pages init's checks out of the box."""
    from presentation_sanity.init_project import bundled_template

    files, _ = bundled_template()
    assert not pages.manim_in_main_dependencies(files["pyproject.toml"].decode())
