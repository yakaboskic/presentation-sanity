"""End-to-end build orchestrator: validate manifest → render manim → slidev build."""

from __future__ import annotations

import sys
from pathlib import Path

from . import figures_render, manim_render, slidev
from .manifest import Manifest, ManifestError, load_manifest
from .slidev import DEFAULT_OUT


def build_all(
    root: Path,
    *,
    skip_manim: bool = False,
    force_manim: bool = False,
    skip_figures: bool = False,
    force_figures: bool = False,
    skip_slidev: bool = False,
    base: str | None = None,
    out: str = DEFAULT_OUT,
    verbose: bool = False,
) -> None:
    """Run the full pipeline against the deck at `root`.

    Steps:
      1. Parse and validate manifest.yaml
      2. Export any stale Excalidraw figures → public/figures/<key>.<format>
      3. Render any stale manim scenes → public/manim/<key>.<format>
      4. Subprocess `npx slidev build` → <out>/ (default "site")

    The `<DataValue>` component reads manifest.yaml directly (via
    @modyfi/vite-plugin-yaml), so there's no separate variables-resolution
    step at this point.
    """
    manifest = load_manifest(root)
    print(
        f"  manifest: {len(manifest.variables)} variables, "
        f"{len(manifest.scenes)} scenes, {len(manifest.figures)} figures"
    )

    # Export Excalidraw figures. Like manim, auto-skip when the exporter isn't
    # installed so the build still completes against committed SVGs in
    # public/figures/. The availability probe never triggers a network install.
    exporter_available = figures_render.is_exporter_available()
    figures_auto_skip = not skip_figures and manifest.figures and not exporter_available

    if skip_figures:
        print("  skipping figure export (--skip-figures)")
    elif not manifest.figures:
        print("  no figures declared — skipping figure export")
    elif figures_auto_skip:
        print(
            "  excalidraw exporter not installed — skipping figure export. "
            "run `presentation-sanity build-figures` to export "
            "(installs the exporter on demand)."
        )
    else:
        statuses = figures_render.render_figures(
            manifest, force=force_figures, verbose=verbose
        )
        rendered = sum(1 for s in statuses.values() if s == "rendered")
        cached = sum(1 for s in statuses.values() if s == "cached")
        skipped = sum(1 for s in statuses.values() if s == "skipped")
        print(f"  figures: {rendered} exported, {cached} cached, {skipped} skipped")

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
        if base is not None:
            print(f"  running slidev build (base={base})...")
        else:
            print("  running slidev build...")
        slidev.build(root, base=base, out=out, verbose=verbose)
        print(f"  done → {root / out}")
