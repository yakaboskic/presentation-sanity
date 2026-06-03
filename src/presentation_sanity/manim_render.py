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


def ffmpeg_path() -> str | None:
    """Return the ffmpeg executable on PATH, or None if not installed.

    ffmpeg is optional: it backs the last-frame *poster* extraction. When
    absent we skip posters (and warn) rather than failing the build.
    """
    return shutil.which("ffmpeg")


def poster_path_for(video_path: Path) -> Path:
    """Poster image path for a rendered scene video.

    `public/manim/<key>.<fmt>` → `public/manim/<key>.poster.png`. The manim
    layout points its `<video poster>` here so the *last* frame (usually the
    finished/summary diagram) shows wherever the video can't play: the initial
    paint, and — crucially — static PDF/PPTX exports.
    """
    return video_path.with_suffix(".poster.png")


def _extract_poster(video: Path, poster: Path, *, verbose: bool = False) -> bool:
    """Grab the LAST frame of `video` into `poster` (png) via ffmpeg.

    `-sseof -1` seeks to one second before the end, then a single output frame
    with `-update 1` leaves the final decoded frame on disk. Returns True on
    success, False if ffmpeg is unavailable or errored — for posters that's
    non-fatal, the caller just continues.
    """
    ff = ffmpeg_path()
    if ff is None:
        return False
    poster.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ff, "-y",
        "-sseof", "-1",
        "-i", str(video),
        "-update", "1",
        "-frames:v", "1",
        "-q:v", "2",
        str(poster),
    ]
    if verbose:
        print(f"  $ {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=None if verbose else subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0 and poster.is_file()


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
    is one of "rendered", "cached", "skipped" (no source file).

    After (re)rendering — and for cached scenes whose poster has gone missing —
    a last-frame poster is extracted to `<key>.poster.png` (best effort; needs
    ffmpeg). The poster lets the manim layout show the finished/summary frame
    wherever the video can't play (initial paint, static PDF/PPTX export).
    """
    cache_path = manifest.root / ".cache" / "manim.json"
    cache = _load_cache(cache_path)
    out_dir = manifest.root / "public" / "manim"
    statuses: dict[str, str] = {}
    poster_warned = False

    for key, scene in manifest.scenes.items():
        if not scene.source.is_file():
            statuses[key] = "skipped"
            continue

        out_file = out_dir / f"{key}.{scene.format}"
        poster_file = poster_path_for(out_file)
        current_hash = _scene_hash(scene)
        cached = cache.get(key, {})
        is_fresh = (
            not force
            and out_file.is_file()
            and cached.get("hash") == current_hash
        )

        if is_fresh:
            statuses[key] = "cached"
            # Regenerate a poster that was deleted or never made (older cache).
            if not poster_file.is_file() and out_file.is_file():
                if ffmpeg_path() is None:
                    if not poster_warned:
                        print(
                            "  note: ffmpeg not found — skipping last-frame posters "
                            "(manim slides fall back to a black frame in exports)."
                        )
                        poster_warned = True
                elif _extract_poster(out_file, poster_file, verbose=verbose):
                    print(f"  {key}: poster")
            continue

        print(f"  rendering scene {key!r} ({scene.source.name}::{scene.class_name})")
        _render_one(scene, out_file, verbose=verbose)
        cache[key] = {
            "hash": current_hash,
            "output": str(out_file.relative_to(manifest.root)),
        }
        statuses[key] = "rendered"

        if ffmpeg_path() is None:
            if not poster_warned:
                print(
                    "  note: ffmpeg not found — skipping last-frame posters "
                    "(manim slides fall back to a black frame in exports)."
                )
                poster_warned = True
        elif _extract_poster(out_file, poster_file, verbose=verbose):
            cache[key]["poster"] = str(poster_file.relative_to(manifest.root))

    _save_cache(cache_path, cache)
    return statuses
