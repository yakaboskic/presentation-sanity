"""Export Excalidraw figures declared in `manifest.figures` to
public/figures/<key>.<format>.

Mirrors manim_render.py: each figure's source file + export config are hashed;
if the hash matches the cached entry AND the output file exists, export is
skipped. Cache lives in `.cache/figures.json` next to manifest.yaml.

Export is done by the Node CLI `excalidraw-brute-export-cli` (Playwright +
Firefox under the hood), invoked via `npx`. It is an *optional* tool: decks
ship committed SVGs, so `build` degrades gracefully when it isn't installed —
exactly like manim. Install it (and its browser) with:

    npx playwright install-deps        # Linux only
    npx playwright install firefox
    # the exporter itself is fetched on demand by `npx --yes`
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .manifest import Figure, Manifest

EXPORTER = "excalidraw-brute-export-cli"


def is_exporter_available() -> bool:
    """True if the Excalidraw exporter can run *without a network install*.

    Probes `npx --no-install <exporter> --help`: returns 0 only when the
    package is already resolvable, so this never triggers a download. Used by
    `build_all` to decide whether to auto-export or skip — matching the role of
    `manim_render.is_manim_available()`.
    """
    if shutil.which("npx") is None:
        return False
    try:
        proc = subprocess.run(
            ["npx", "--no-install", EXPORTER, "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _figure_hash(fig: Figure) -> str:
    h = hashlib.sha256()
    h.update(fig.source.read_bytes())
    config = {
        "format": fig.format,
        "scale": fig.scale,
        "background": fig.background,
        "dark": fig.dark,
        "embed_scene": fig.embed_scene,
    }
    h.update(json.dumps(config, sort_keys=True).encode())
    return h.hexdigest()[:16]


def _load_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.is_file():
        return {}
    try:
        return json.loads(cache_path.read_text())
    except json.JSONDecodeError:
        return {}


def _save_cache(cache_path: Path, data: dict[str, dict[str, Any]]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _export_one(fig: Figure, output_path: Path, *, verbose: bool = False) -> None:
    """Subprocess the Excalidraw exporter, writing directly to output_path.

    Uses `npx --yes` so the exporter is fetched on demand when missing. The
    underlying Playwright Firefox browser is NOT auto-installed; a failure here
    most often means the browser is absent — the error message says so.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "npx",
        "--yes",
        EXPORTER,
        "-i",
        str(fig.source),
        "--format",
        fig.format,
        "--background",
        "1" if fig.background else "0",
        "--dark-mode",
        "1" if fig.dark else "0",
        "--embed-scene",
        "1" if fig.embed_scene else "0",
        "--scale",
        str(fig.scale),
        "-o",
        str(output_path),
    ]
    if verbose:
        print(f"  $ {' '.join(cmd)}", file=sys.stderr)

    proc = subprocess.run(
        cmd,
        stdout=None if verbose else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise RuntimeError(
            f"{EXPORTER} failed for figure {fig.key!r} (exit {proc.returncode}). "
            "If this is the first run, install the browser it needs:\n"
            "  npx playwright install-deps   # Linux only\n"
            "  npx playwright install firefox"
        )
    if not output_path.is_file():
        raise RuntimeError(
            f"{EXPORTER} reported success but produced no file at {output_path}"
        )


def render_figures(
    manifest: Manifest,
    *,
    force: bool = False,
    verbose: bool = False,
) -> dict[str, str]:
    """Export every figure in the manifest. Returns {key: status} where status
    is one of "rendered", "cached", "skipped" (no source file)."""
    cache_path = manifest.root / ".cache" / "figures.json"
    cache = _load_cache(cache_path)
    out_dir = manifest.root / "public" / "figures"
    statuses: dict[str, str] = {}

    for key, fig in manifest.figures.items():
        if not fig.source.is_file():
            statuses[key] = "skipped"
            continue

        out_file = out_dir / f"{key}.{fig.format}"
        current_hash = _figure_hash(fig)
        cached = cache.get(key, {})
        is_fresh = (
            not force
            and out_file.is_file()
            and cached.get("hash") == current_hash
        )

        if is_fresh:
            statuses[key] = "cached"
            continue

        print(f"  exporting figure {key!r} ({fig.source.name} → {fig.format})")
        _export_one(fig, out_file, verbose=verbose)
        cache[key] = {
            "hash": current_hash,
            "output": str(out_file.relative_to(manifest.root)),
        }
        statuses[key] = "rendered"

    _save_cache(cache_path, cache)
    return statuses
