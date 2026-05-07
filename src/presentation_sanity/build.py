"""End-to-end build orchestrator: validate manifest → render manim → slidev build."""

from __future__ import annotations

import sys
from pathlib import Path

from . import manim_render, slidev
from .manifest import Manifest, ManifestError, load_manifest


def build_all(
    root: Path,
    *,
    skip_manim: bool = False,
    force_manim: bool = False,
    skip_slidev: bool = False,
    verbose: bool = False,
) -> None:
    """Run the full pipeline against the deck at `root`.

    Steps:
      1. Parse and validate manifest.yaml
      2. Render any stale manim scenes → public/manim/<key>.<format>
      3. Subprocess `npx slidev build` → dist/

    The `<DataValue>` component reads manifest.yaml directly (via
    @modyfi/vite-plugin-yaml), so there's no separate variables-resolution
    step at this point.
    """
    manifest = load_manifest(root)
    print(f"  manifest: {len(manifest.variables)} variables, {len(manifest.scenes)} scenes")

    # Decide whether to render manim. Auto-skip if the package isn't
    # installed so the build still completes (slidev portion runs fine
    # against pre-rendered videos sitting in public/manim/).
    manim_available = manim_render.is_manim_available()
    auto_skip = not skip_manim and manifest.scenes and not manim_available

    if skip_manim:
        print("  skipping manim rendering (--skip-manim)")
    elif not manifest.scenes:
        print("  no scenes declared — skipping manim")
    elif auto_skip:
        print(
            "  manim not installed — skipping render. "
            "install with `pip install presentation-sanity[manim]` to render scenes."
        )
    else:
        statuses = manim_render.render_scenes(
            manifest, force=force_manim, verbose=verbose
        )
        rendered = sum(1 for s in statuses.values() if s == "rendered")
        cached = sum(1 for s in statuses.values() if s == "cached")
        skipped = sum(1 for s in statuses.values() if s == "skipped")
        print(f"  manim: {rendered} rendered, {cached} cached, {skipped} skipped")

    if skip_slidev:
        print("  skipping slidev build")
    else:
        print("  running slidev build...")
        slidev.build(root, verbose=verbose)
        print(f"  done → {root / 'dist'}")
