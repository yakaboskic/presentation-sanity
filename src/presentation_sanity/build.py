"""End-to-end build orchestrator.

One subject, many printouts. Shared inputs (figures, manim scenes) are
rendered *once* into `public/`, then every declared output in `manifest.outputs`
renders from that same pool with its own engine.
"""

from __future__ import annotations

import html
from pathlib import Path

from . import figures_render, manim_render, slidev, vitepress
from .manifest import Manifest, ManifestError, Output


def build_shared(
    manifest: Manifest,
    *,
    skip_manim: bool = False,
    force_manim: bool = False,
    skip_figures: bool = False,
    force_figures: bool = False,
    verbose: bool = False,
) -> None:
    """Render the engine-agnostic artifacts every output draws from.

    Both renderers read `public/` at the same URL prefix, so a scene rendered
    here is embeddable as `<ManimFigure scene="x" />` in the blog and
    `layout: manim` in the deck without a second render.
    """
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
    # installed so the build still completes (the renderer portion runs fine
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


def build_output(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    verbose: bool = False,
) -> None:
    """Render a single output with whichever engine it declares."""
    print(f"  building output {output.key!r} ({output.engine}: {output.entry})")
    if output.engine == "slidev":
        slidev.build(manifest, output, base=base, verbose=verbose)
    elif output.engine == "vitepress":
        vitepress.build(manifest, output, base=base, verbose=verbose)
    else:  # pragma: no cover — Output.from_raw validates the engine
        raise ManifestError(f"no builder for engine {output.engine!r}")
    print(f"  → {manifest.root / output.out}")


def write_index(manifest: Manifest, outputs: dict[str, Output]) -> Path | None:
    """Write a landing page linking every printout that shares a parent dir.

    Only makes sense when there is more than one output and they nest under a
    common directory (the `site/<key>` default). Returns the written path, or
    None when the layout doesn't call for one.
    """
    if len(outputs) < 2:
        return None
    parents = {Path(o.out).parent for o in outputs.values()}
    if len(parents) != 1:
        return None
    parent = parents.pop()
    if parent in (Path("."), Path("/")):
        return None

    index = manifest.root / parent / "index.html"
    if not index.parent.is_dir():
        return None

    title = html.escape(manifest.title)
    links = "\n".join(
        f'      <li><a href="./{html.escape(Path(o.out).name)}/">'
        f"{html.escape(o.title or o.key)}</a> "
        f'<span class="engine">{html.escape(o.engine)}</span></li>'
        for o in outputs.values()
    )
    index.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 ui-sans-serif, system-ui, sans-serif;
         max-width: 34rem; margin: 18vh auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 600; margin: 0 0 1.5rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin: 0.4rem 0; }}
  a {{ text-decoration: none; border-bottom: 1px solid currentColor; }}
  .engine {{ opacity: 0.45; font-size: 0.8em; margin-left: 0.5em; }}
</style>
<h1>{title}</h1>
<ul>
{links}
</ul>
"""
    )
    return index


def build_all(
    root: Path,
    *,
    targets: list[str] | None = None,
    skip_manim: bool = False,
    force_manim: bool = False,
    skip_figures: bool = False,
    force_figures: bool = False,
    skip_render: bool = False,
    base: str | None = None,
    out: str | None = None,
    verbose: bool = False,
) -> None:
    """Run the full pipeline against the subject at `root`.

    Steps:
      1. Parse and validate manifest.yaml
      2. Export any stale Excalidraw figures → public/figures/<key>.<format>
      3. Render any stale manim scenes  → public/manim/<key>.<format>
      4. Render every selected output with its engine

    The `<DataValue>` component reads manifest.yaml directly (via
    @modyfi/vite-plugin-yaml) in both engines, so there's no separate
    variables-resolution step.
    """
    from .manifest import load_manifest

    manifest = load_manifest(root)
    selected = manifest.resolve_targets(targets)
    print(
        f"  manifest: {len(manifest.variables)} variables, "
        f"{len(manifest.scenes)} scenes, {len(manifest.figures)} figures, "
        f"{len(selected)}/{len(manifest.outputs)} outputs"
    )
    if not selected:
        print("  no outputs declared in manifest.yaml under `outputs:` — nothing to do")
        return

    if out is not None:
        if len(selected) != 1:
            raise ManifestError(
                "--out overrides a single output's directory; name one target "
                f"(e.g. `build {next(iter(selected))} --out {out}`)"
            )
        next(iter(selected.values())).out = out

    build_shared(
        manifest,
        skip_manim=skip_manim,
        force_manim=force_manim,
        skip_figures=skip_figures,
        force_figures=force_figures,
        verbose=verbose,
    )

    if skip_render:
        print("  skipping output rendering (--skip-render)")
        return

    for output in selected.values():
        build_output(manifest, output, base=base, verbose=verbose)

    # Only write a landing page for a full build — a partial one would list
    # targets that were not (re)built in this run.
    if targets is None:
        index = write_index(manifest, selected)
        if index is not None:
            print(f"  → {index}")
