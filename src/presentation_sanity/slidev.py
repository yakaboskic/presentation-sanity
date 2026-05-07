"""Subprocess wrappers around the Slidev CLI (`npx slidev ...`).

Keeping these in one place so we have a single seam to swap if we ever
want to call Slidev's JS API directly instead of shelling out.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


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


def build(root: Path, *, verbose: bool = False) -> None:
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev", "build"]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)


def dev(root: Path, *, open_browser: bool = True) -> None:
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev"]
    if open_browser:
        cmd.append("--open")
    subprocess.run(cmd, cwd=root, check=False)


def export(root: Path, *, fmt: str = "pdf", verbose: bool = False) -> None:
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev", "export", "--format", fmt]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)
