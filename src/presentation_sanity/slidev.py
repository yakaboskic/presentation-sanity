"""Subprocess wrappers around the Slidev CLI (`npx slidev ...`).

Keeping these in one place so we have a single seam to swap if we ever
want to call Slidev's JS API directly instead of shelling out.
"""

from __future__ import annotations

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
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev", "build", output.entry, "--out", output.out]
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
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
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
    verbose: bool = False,
) -> None:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev", "export", output.entry, "--format", fmt]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)
