"""Subprocess wrappers around the Slidev CLI (`npx slidev ...`).

Keeping these in one place so we have a single seam to swap if we ever
want to call Slidev's JS API directly instead of shelling out.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Default build-output directory. Deliberately NOT "dist"/"build"/"out" — those
# names are on the default ignore lists of many static hosts and deploy tools,
# which silently skip the build when serving. "site" is neutral and picked up.
DEFAULT_OUT = "site"


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
    root: Path,
    *,
    base: str | None = None,
    out: str = DEFAULT_OUT,
    verbose: bool = False,
) -> None:
    """Run `npx slidev build` against the deck at `root`.

    `base` (optional) is forwarded to slidev as `--base <value>` and lets
    the built site be served from a subdirectory. Pass e.g. `./` for
    fully relative asset paths, or `/preview/abc/` for a known prefix.

    `out` is the output directory (forwarded as `--out`), default
    `DEFAULT_OUT` ("site") rather than slidev's "dist".
    """
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "slidev", "build", "--out", out]
    if base is not None:
        cmd.extend(["--base", base])
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
