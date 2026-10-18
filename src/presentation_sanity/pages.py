"""`presentation-sanity pages init`: deploy a project to GitHub Pages.

Writes `.github/workflows/pages.yml`, which builds `site/` on every push to
the default branch and deploys it with GitHub's own Pages actions.

The runner never renders manim. Rendering needs cairo, pango, ffmpeg and
LaTeX, and the project's dependency line would make `uv sync` compile the
cairo bindings first. Instead the workflow installs with
`uv sync --no-default-groups` — which leaves out the `manim` dependency group
the template declares — and builds with `--skip-manim --skip-figures`, so it
deploys exactly the videos and figures committed in `public/`: the ones you
rendered and looked at. `pages init` checks the project can work that way
(no `[manim]` in the main dependencies, rendered assets present and not
gitignored) and says what to fix when it can't.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .manifest import load_manifest

WORKFLOW_PATH = ".github/workflows/pages.yml"

# Current majors at the time of writing. astral-sh/setup-uv publishes no
# floating major tag, so it is pinned to a release.
ACTIONS = {
    "checkout": "actions/checkout@v7",
    "configure-pages": "actions/configure-pages@v6",
    "setup-uv": "astral-sh/setup-uv@v10.3.0",
    "setup-node": "actions/setup-node@v7",
    "upload-pages-artifact": "actions/upload-pages-artifact@v5",
    "deploy-pages": "actions/deploy-pages@v5",
}
NODE_VERSION = "24"

WORKFLOW = """\
# Build this project's site/ and deploy it to GitHub Pages.
# Written by `presentation-sanity pages init` (v{version}); rerun it with
# --force to regenerate.
#
# A Pages site is PUBLIC, even when this repository is private.
#
# One-time setup: Settings → Pages → Build and deployment → Source: GitHub Actions.
#
# The runner does not render manim (that needs cairo, pango, ffmpeg and LaTeX).
# `uv sync --no-default-groups` leaves out the `manim` dependency group, and
# `build --skip-manim --skip-figures` deploys the videos and figures committed
# in public/ as they are: render locally, commit public/, push.
name: Deploy to GitHub Pages

on:
  push:
    branches: [{branch}]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
{guard}    runs-on: ubuntu-latest
    steps:
      - uses: {checkout}
      - id: pages
        uses: {configure_pages}
      - uses: {setup_uv}
        with:
          enable-cache: true
      - uses: {setup_node}
        with:
          node-version: {node}
          cache: npm
      - name: Install presentation-sanity (no manim)
        run: uv sync --locked --no-default-groups
      - name: Install Slidev and VitePress
        run: npm ci
      - name: Build site/
        # base_path is "/<repo>" for a project site, "" for a custom domain or
        # a <user>.github.io repository. Blogs need it absolute.
        run: >-
          uv run --no-sync presentation-sanity build
          --skip-manim --skip-figures
          --base "${{{{ steps.pages.outputs.base_path }}}}/"
      - uses: {upload}
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    steps:
      - id: deployment
        uses: {deploy}
"""


class PagesError(Exception):
    """The project can't deploy this way yet; nothing was written."""


def render_workflow(*, branch: str = "main", only_repo: str | None = None) -> str:
    guard = ""
    if only_repo:
        guard = (
            "    # Deploy from this repository only: forks and template copies skip it.\n"
            f"    if: github.repository == '{only_repo}'\n"
        )
    return WORKFLOW.format(
        version=__version__,
        branch=branch,
        guard=guard,
        node=NODE_VERSION,
        checkout=ACTIONS["checkout"],
        configure_pages=ACTIONS["configure-pages"],
        setup_uv=ACTIONS["setup-uv"],
        setup_node=ACTIONS["setup-node"],
        upload=ACTIONS["upload-pages-artifact"],
        deploy=ACTIONS["deploy-pages"],
    )


def _project_dependencies(pyproject: str) -> list[str]:
    """`[project].dependencies`, without needing tomllib (Python 3.10)."""
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover — Python 3.10
        m = re.search(r"^\[project\][^\[]*?^dependencies\s*=\s*\[(.*?)\]", pyproject, re.S | re.M)
        return re.findall(r"[\"']([^\"']+)[\"']", m.group(1)) if m else []
    return list(tomllib.loads(pyproject).get("project", {}).get("dependencies", []))


def manim_in_main_dependencies(pyproject: str) -> bool:
    return any(
        re.match(r"presentation-sanity\s*\[[^\]]*\bmanim\b", dep.strip())
        for dep in _project_dependencies(pyproject)
    )


MIGRATE_MANIM = """\
pyproject.toml installs manim with the project itself
  ("presentation-sanity[manim] @ …" under [project] dependencies), so the
  runner would have to compile the cairo and pango bindings. Move the extra
  into a default dependency group — `uv sync` still installs it locally, and
  the workflow's `uv sync --no-default-groups` leaves it out:

    [project]
    dependencies = [
        "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@vX.Y.Z",
    ]

    [dependency-groups]
    manim = ["presentation-sanity[manim]"]

    [tool.uv]
    default-groups = ["manim"]

  then run `uv lock` and commit pyproject.toml and uv.lock."""


def _ignored(root: Path, paths: list[Path]) -> set[Path]:
    """Which of `paths` git would ignore (empty outside a git repository)."""
    if not paths or shutil.which("git") is None:
        return set()
    rels = [p.relative_to(root).as_posix() for p in paths]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *rels], cwd=root, capture_output=True, text=True
    )
    if result.returncode not in (0, 1):  # 128: not a git repository
        return set()
    return {root / line for line in result.stdout.split()}


@dataclass
class Report:
    path: Path
    notes: list[str] = field(default_factory=list)


def check_assets(root: Path) -> list[str]:
    """What the runner would be missing: rendered assets absent or gitignored."""
    manifest = load_manifest(root)
    expected: list[tuple[str, Path]] = []
    for scene in manifest.scenes.values():
        video = root / "public" / "manim" / f"{scene.key}.{scene.format}"
        expected += [("scene", video), ("poster", video.with_name(f"{scene.key}.poster.png"))]
    for fig in manifest.figures.values():
        expected.append(("figure", root / "public" / "figures" / f"{fig.key}.{fig.format}"))

    notes = []
    missing = [p for kind, p in expected if not p.is_file() and kind != "poster"]
    if missing:
        notes.append(
            "not rendered yet (run `presentation-sanity build` locally, then commit): "
            + ", ".join(p.relative_to(root).as_posix() for p in missing)
        )
    ignored = sorted(_ignored(root, [p for _, p in expected]))
    if ignored:
        notes.append(
            "gitignored, so the runner would never see them — remove the matching "
            "lines from .gitignore and commit the files: "
            + ", ".join(p.relative_to(root).as_posix() for p in ignored)
        )
    return notes


def pages_init(
    root: Path, *, branch: str = "main", only_repo: str | None = None, force: bool = False
) -> Report:
    path = root / WORKFLOW_PATH
    if path.exists() and not force:
        raise PagesError(f"{WORKFLOW_PATH} already exists — pass --force to regenerate it")
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        raise PagesError(
            "no pyproject.toml — the workflow installs presentation-sanity with uv "
            "from this project's own pin"
        )
    if manim_in_main_dependencies(pyproject.read_text()):
        raise PagesError(MIGRATE_MANIM)
    if only_repo is not None and not re.fullmatch(r"[\w.-]+/[\w.-]+", only_repo):
        raise PagesError(f"--only-repo expects OWNER/NAME, got {only_repo!r}")

    notes = []
    for lock, how in (("uv.lock", "uv lock"), ("package-lock.json", "npm install")):
        if not (root / lock).is_file():
            notes.append(f"no {lock} — run `{how}` and commit it (the workflow installs from it)")
    notes += check_assets(root)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_workflow(branch=branch, only_repo=only_repo))
    return Report(path, notes)


def github_remote(root: Path) -> tuple[str, str] | None:
    """(owner, repo) of the `origin` remote when it points at GitHub."""
    if shutil.which("git") is None:
        return None
    out = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=root, capture_output=True, text=True
    )
    m = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", out.stdout.strip())
    return (m.group(1), m.group(2)) if m else None
