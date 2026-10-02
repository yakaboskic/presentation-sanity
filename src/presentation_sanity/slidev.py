"""Subprocess wrappers around the Slidev CLI (`npx slidev ...`).

Keeping these in one place so we have a single seam to swap if we ever
want to call Slidev's JS API directly instead of shelling out.

Every command runs from the subject (or project) root, where `node_modules`
lives. In a project the entry is `presentations/<id>/slides.md`, which makes
that folder Slidev's user root: root-level components, layouts and styles no
longer apply there, so they ship as the `shared/` addon instead (wired once in
the root package.json — see `check_shared_addon`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .manifest import Manifest, Output

# Default build-output directory for a manifest that predates `outputs:`.
# Deliberately NOT "dist"/"build"/"out" — those names are on the default ignore
# lists of many static hosts and deploy tools, which silently skip the build
# when serving. "site" is neutral and picked up.
DEFAULT_OUT = "site"

DEFAULT_ENTRY = "slides.md"

SHARED_ADDON_DIR = "shared"


def _check_npx() -> None:
    if shutil.which("npx") is None:
        raise RuntimeError(
            "npx not found on PATH. Install Node.js >= 20 (https://nodejs.org)."
        )


def _check_node_modules(root: Path) -> None:
    if not (root / "node_modules" / "@slidev" / "cli").is_dir():
        raise RuntimeError(
            f"Slidev not installed in {root}. Run `npm install` there first."
        )


def _check_entry(root: Path, output: Output) -> None:
    # Slidev offers to *create* a missing entry and then exits 0 when that is
    # declined — a "successful" build that produced nothing. Fail loudly first.
    entry = root / output.entry
    if not entry.is_file():
        raise RuntimeError(f"output {output.key!r}: entry {entry} not found")


def check_shared_addon(manifest: Manifest) -> None:
    """In a project, make sure decks will actually see the shared Vue layer.

    A deck under presentations/ only gets components, layouts, global layers
    and the YAML plugin through the `shared/` addon, which npm links into
    node_modules from the root package.json's `file:` dependency.
    """
    if not manifest.project_mode:
        return
    root = manifest.root
    pkg = root / SHARED_ADDON_DIR / "package.json"
    if not pkg.is_file():
        if (root / "components").is_dir() or (root / "layouts").is_dir():
            print(
                "  warning: components/ and layouts/ at the project root are not "
                "visible to decks under presentations/. Move them into a shared/ "
                "addon (see the presentation-sanity README, 'Projects').",
                file=sys.stderr,
            )
        return
    try:
        name = json.loads(pkg.read_text())["name"]
    except (json.JSONDecodeError, KeyError) as e:
        raise RuntimeError(f"{pkg} needs a JSON `name` field") from e
    if not (root / "node_modules" / name).exists():
        raise RuntimeError(
            f"the shared addon {name!r} is not installed — run `npm install` in {root}"
        )


def _prepare(manifest: Manifest, output: Output) -> Path:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    _check_entry(root, output)
    check_shared_addon(manifest)
    return root


def build(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    verbose: bool = False,
) -> None:
    """Run `npx slidev build <entry>` for one Slidev output.

    `base` (optional) is forwarded to slidev as `--base <value>` and lets
    the built site be served from a subdirectory. Pass e.g. `./` for
    fully relative asset paths, or `/preview/abc/` for a known prefix.
    """
    root = _prepare(manifest, output)
    # Slidev resolves --out against the deck's folder, not the cwd.
    out = str((root / output.out).resolve())
    cmd = ["npx", "slidev", "build", output.entry, "--out", out]
    effective_base = base if base is not None else output.extra.get("base")
    if effective_base is not None:
        cmd.extend(["--base", str(effective_base)])
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)


def dev(
    manifest: Manifest,
    output: Output,
    *,
    open_browser: bool = True,
    verbose: bool = False,
) -> None:
    root = _prepare(manifest, output)
    cmd = ["npx", "slidev", output.entry]
    if open_browser:
        cmd.append("--open")
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=False)


def export(
    manifest: Manifest,
    output: Output,
    *,
    fmt: str = "pdf",
    out: Path | None = None,
    verbose: bool = False,
) -> None:
    """`slidev export`. `out` (without extension for pdf/pptx) defaults to
    Slidev's own `<entry>-export` in the cwd."""
    root = _prepare(manifest, output)
    cmd = ["npx", "slidev", "export", output.entry, "--format", fmt]
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--output", str(out)])  # relative to the cwd, so absolute
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)
