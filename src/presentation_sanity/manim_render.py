"""Render manim scenes declared in `manifest.scenes` to public/manim/<key>.webm.

Caching: each scene's source file + manifest config are hashed; if the hash
matches the cached entry AND the output file exists, rendering is skipped.
Cache lives in `.cache/manim.json` next to manifest.yaml.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .manifest import Manifest, Scene


def is_manim_available() -> bool:
    """True if the `manim` package is importable from the current Python.

    Used by `build_all` to gracefully skip rendering when manim isn't
    installed. Matches what the subprocess (`sys.executable -m manim`)
    would see, so the two checks stay consistent.
    """
    return importlib.util.find_spec("manim") is not None

QUALITY_DIR = {
    "l": "480p15",
    "m": "720p30",
    "h": "1080p60",
    "p": "1440p60",
    "k": "2160p60",
}


def _scene_hash(scene: Scene) -> str:
    h = hashlib.sha256()
    h.update(scene.source.read_bytes())
    config = {
        "class": scene.class_name,
        "quality": scene.quality,
        "format": scene.format,
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


def _render_one(scene: Scene, output_path: Path, *, verbose: bool = False) -> None:
    """Subprocess manim, then move the rendered file into output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="psanity-manim-") as tmp:
        tmp_dir = Path(tmp)
        cmd = [
            sys.executable,
            "-m",
            "manim",
            "render",
            str(scene.source),
            scene.class_name,
            "--format",
            scene.format,
            "--media_dir",
            str(tmp_dir),
            f"--quality={scene.quality}",
            "-o",
            scene.key,
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
                f"manim failed for scene {scene.key!r} (exit {proc.returncode})"
            )

        # manim writes to: <media_dir>/videos/<source_basename>/<quality_dir>/<-o>.<format>
        quality_dir = QUALITY_DIR.get(scene.quality, scene.quality)
        produced = (
            tmp_dir
            / "videos"
            / scene.source.stem
            / quality_dir
            / f"{scene.key}.{scene.format}"
        )
        if not produced.is_file():
            # Fallback: glob for any matching output (in case manim's layout shifts)
            candidates = sorted(tmp_dir.rglob(f"{scene.key}.{scene.format}"))
            if not candidates:
                candidates = sorted(tmp_dir.rglob(f"*.{scene.format}"))
            if not candidates:
                raise RuntimeError(
                    f"manim produced no {scene.format} file for scene {scene.key!r}"
                )
            produced = candidates[-1]

        shutil.move(str(produced), str(output_path))


def render_scenes(
    manifest: Manifest,
    *,
    force: bool = False,
    verbose: bool = False,
) -> dict[str, str]:
    """Render every scene in the manifest. Returns {key: status} where status
    is one of "rendered", "cached", "skipped" (no source file)."""
    cache_path = manifest.root / ".cache" / "manim.json"
    cache = _load_cache(cache_path)
    out_dir = manifest.root / "public" / "manim"
    statuses: dict[str, str] = {}

    for key, scene in manifest.scenes.items():
        if not scene.source.is_file():
            statuses[key] = "skipped"
            continue

        out_file = out_dir / f"{key}.{scene.format}"
        current_hash = _scene_hash(scene)
        cached = cache.get(key, {})
        is_fresh = (
            not force
            and out_file.is_file()
            and cached.get("hash") == current_hash
        )

        if is_fresh:
            statuses[key] = "cached"
            continue

        print(f"  rendering scene {key!r} ({scene.source.name}::{scene.class_name})")
        _render_one(scene, out_file, verbose=verbose)
        cache[key] = {
            "hash": current_hash,
            "output": str(out_file.relative_to(manifest.root)),
        }
        statuses[key] = "rendered"

    _save_cache(cache_path, cache)
    return statuses
