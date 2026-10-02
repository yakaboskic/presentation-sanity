"""End-to-end build orchestrator.

One subject, many printouts. Shared inputs (figures, manim scenes) are
rendered *once* into `public/`, then every declared output in `manifest.outputs`
renders from that same pool with its own engine.

A project is the same idea one level up: shared inputs render once at the
project root, then each selected presentation's outputs build into
`site/<presentation>/<output>/`, and `site/index.html` links them all.
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import TYPE_CHECKING

from . import figures_render, manim_render, slidev, vitepress
from .manifest import Manifest, ManifestError, Output

if TYPE_CHECKING:
    from .project import Presentation, Project


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
    presentation: "Presentation | None" = None,
    verbose: bool = False,
) -> None:
    """Render a single output with whichever engine it declares."""
    entry = os.path.relpath(manifest.root / output.entry, manifest.root)
    label = f"{presentation.id}:{output.key}" if presentation else repr(output.key)
    print(f"  building {label} ({output.engine}: {entry})")
    if output.engine == "slidev":
        slidev.build(manifest, output, base=base, verbose=verbose)
    elif output.engine == "vitepress":
        vitepress.build(
            manifest, output, base=base, presentation=presentation, verbose=verbose
        )
    else:  # pragma: no cover — Output.from_raw validates the engine
        raise ManifestError(f"no builder for engine {output.engine!r}")
    print(f"  → {manifest.root / output.out}")


def project_base(project: "Project", output: Output, prefix: str | None) -> str | None:
    """The base one output is built with, given the deploy prefix (`--base`).

    Slidev gets `./` — relative assets work under any prefix. VitePress needs an
    absolute base, so it is the prefix plus the output's path under `site/`. An
    output with its own `base:` keeps it (None lets the engine read it).
    """
    if "base" in output.extra:
        return None
    if output.engine == "slidev":
        return "./"
    prefix = (prefix or "/").strip()
    if prefix in ("", ".", "./"):
        prefix = "/"
    try:
        rel = Path(output.out).resolve().relative_to(project.site_dir.resolve())
    except ValueError:
        return prefix  # built outside site/ — the prefix is all we know
    return prefix.rstrip("/") + "/" + rel.as_posix() + "/"


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


def write_project_index(project: "Project") -> Path | None:
    """`site/index.html`: every built presentation, grouped by folder.

    Regenerated on every project build from what actually exists on disk, so a
    partial build never drops (or invents) links.
    """
    site = project.site_dir
    built: dict[str, list[tuple["Presentation", list[Output]]]] = {}
    for p in project.presentations.values():
        outs = [o for o in p.outputs.values() if (Path(o.out) / "index.html").is_file()]
        if outs:
            built.setdefault(p.group, []).append((p, outs))
    if not built:
        return None

    def item(p: "Presentation", outs: list[Output]) -> str:
        meta = " · ".join(
            html.escape(str(p.metadata[k])) for k in ("date", "venue") if p.metadata.get(k)
        )
        links = " ".join(
            f'<a href="./{html.escape(Path(os.path.relpath(o.out, site)).as_posix())}/">'
            f"{html.escape(o.key)}</a>"
            for o in outs
        )
        lineage = (
            f'<span class="from">from {html.escape(str(p.metadata["from"]))}</span>'
            if p.metadata.get("from")
            else ""
        )
        return (
            f'      <li><span class="title">{html.escape(p.title)}</span>'
            f' <span class="links">{links}</span>'
            + (f'<br><span class="meta">{meta}</span>' if meta else "")
            + f' <code>{html.escape(p.id)}</code> {lineage}</li>'
        )

    sections = []
    for group in sorted(built):
        heading = f"    <h2>{html.escape(group)}</h2>\n" if group else ""
        items = "\n".join(item(p, outs) for p, outs in built[group])
        sections.append(f"{heading}    <ul>\n{items}\n    </ul>")

    title = html.escape(project.title)
    index = site / "index.html"
    site.mkdir(parents=True, exist_ok=True)
    index.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 ui-sans-serif, system-ui, sans-serif;
         max-width: 42rem; margin: 12vh auto; padding: 0 1.5rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 600; margin: 0 0 1.5rem; }}
  h2 {{ font-size: 1rem; font-weight: 600; margin: 2rem 0 0.4rem; opacity: 0.6; }}
  ul {{ list-style: none; padding: 0; margin: 0; }}
  li {{ margin: 0.7rem 0; }}
  a {{ text-decoration: none; border-bottom: 1px solid currentColor; margin-right: 0.4em; }}
  .title {{ font-weight: 500; margin-right: 0.6em; }}
  .meta, .from, code {{ opacity: 0.5; font-size: 0.8em; }}
</style>
<h1>{title}</h1>
{chr(10).join(sections)}
"""
    )
    return index


def build_project(
    root: Path,
    *,
    targets: list[str] | None = None,
    cwd: Path | None = None,
    skip_manim: bool = False,
    force_manim: bool = False,
    skip_figures: bool = False,
    force_figures: bool = False,
    skip_render: bool = False,
    base: str | None = None,
    out: str | None = None,
    verbose: bool = False,
) -> None:
    """Build selected presentations of the project at `root`.

    Shared inputs render once; then each selected (presentation, output) pair
    builds into `site/<id>/<output>/`; then the project index is refreshed.
    """
    from .project import load_project, select

    project = load_project(root)
    manifest = project.manifest
    pairs = select(project, targets, cwd or root)
    print(
        f"  project: {len(project.presentations)} presentations, "
        f"{len(manifest.variables)} variables, {len(manifest.scenes)} scenes, "
        f"{len(manifest.figures)} figures — building {len(pairs)} output(s)"
    )
    if not pairs:
        print(
            "  nothing to build — add a presentation with "
            "`presentation-sanity new <name>`"
        )
        return

    if out is not None:
        if len(pairs) != 1:
            raise ManifestError(
                "--out overrides a single output's directory; name one target "
                "(e.g. `build <presentation>:slides --out …`)"
            )
        pairs[0][1].out = str((root / out).resolve())

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

    for presentation, output in pairs:
        build_output(
            manifest,
            output,
            base=project_base(project, output, base),
            presentation=presentation,
            verbose=verbose,
        )

    index = write_project_index(project)
    if index is not None:
        print(f"  → {index}")


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
