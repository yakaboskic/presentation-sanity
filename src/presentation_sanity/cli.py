"""CLI entry point: argparse-based, matching document-sanity's style.

Verbs take an optional output *target* — a key under `outputs:` in
manifest.yaml:

    presentation-sanity build              # every declared output
    presentation-sanity build blog         # just the blog
    presentation-sanity dev blog           # vitepress dev server
    presentation-sanity dev slides         # slidev dev server
    presentation-sanity preview blog
    presentation-sanity export pdf         # slides only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .manifest import Manifest, ManifestError, Output, load_manifest


def _fail(e: Exception, verbose: bool) -> int:
    if isinstance(e, ManifestError):
        print(f"  manifest error: {e}", file=sys.stderr)
        return 2
    print(f"  error: {e}", file=sys.stderr)
    if verbose:
        import traceback

        traceback.print_exc()
    return 1


def _pick_one(
    manifest: Manifest, target: str | None, *, engine: str | None = None
) -> Output:
    """Resolve the single output a verb like `dev` or `preview` acts on.

    With no target, pick the only candidate; if several qualify, list them
    rather than guessing — silently developing the wrong printout is worse
    than one extra keystroke.
    """
    pool = manifest.outputs
    if engine is not None:
        pool = manifest.outputs_for_engine(engine)
        if not pool:
            raise ManifestError(
                f"manifest.yaml declares no `{engine}` output. Add one under "
                f"`outputs:` with `engine: {engine}`."
            )
    if target is not None:
        if target not in manifest.outputs:
            raise ManifestError(
                f"unknown output {target!r}. manifest.yaml declares: "
                f"{', '.join(manifest.outputs) or '(none)'}"
            )
        output = manifest.outputs[target]
        if engine is not None and output.engine != engine:
            raise ManifestError(
                f"output {target!r} uses engine {output.engine!r}, "
                f"but this command needs {engine!r}"
            )
        return output
    if len(pool) == 1:
        return next(iter(pool.values()))
    raise ManifestError(
        f"several outputs to choose from ({', '.join(pool)}) — name one, "
        f"e.g. `{', '.join(list(pool)[:1])}`"
    )


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build_all

    try:
        build_all(
            Path(args.root).resolve(),
            targets=args.targets or None,
            skip_manim=args.skip_manim,
            force_manim=args.force_manim,
            skip_figures=args.skip_figures,
            force_figures=args.force_figures,
            skip_render=args.skip_render,
            base=args.base,
            out=args.out,
            verbose=args.verbose,
        )
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_build_manim(args: argparse.Namespace) -> int:
    from . import manim_render

    if not manim_render.is_manim_available():
        print(
            "  error: manim is not installed.\n"
            "  install with: pip install presentation-sanity[manim]",
            file=sys.stderr,
        )
        return 1

    try:
        manifest = load_manifest(Path(args.root).resolve())
        statuses = manim_render.render_scenes(
            manifest, force=args.force, verbose=args.verbose
        )
        for key, status in statuses.items():
            print(f"  {key}: {status}")
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_build_figures(args: argparse.Namespace) -> int:
    from . import figures_render

    try:
        manifest = load_manifest(Path(args.root).resolve())
        if not manifest.figures:
            print("  no figures declared in manifest.yaml under `figures:`")
            return 0
        statuses = figures_render.render_figures(
            manifest, force=args.force, verbose=args.verbose
        )
        for key, status in statuses.items():
            print(f"  {key}: {status}")
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_dev(args: argparse.Namespace) -> int:
    from . import slidev, vitepress

    try:
        manifest = load_manifest(Path(args.root).resolve())
        output = _pick_one(manifest, args.target)
        engine = vitepress if output.engine == "vitepress" else slidev
        engine.dev(
            manifest,
            output,
            open_browser=not args.no_open,
            verbose=args.verbose,
        )
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Write `.vitepress/` without building — useful for editor tooling."""
    from . import vitepress

    try:
        manifest = load_manifest(Path(args.root).resolve())
        output = _pick_one(manifest, args.target, engine="vitepress")
        path = vitepress.scaffold(manifest, output, verbose=args.verbose)
        print(f"  → {path}")
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_export(args: argparse.Namespace) -> int:
    from . import slidev

    try:
        manifest = load_manifest(Path(args.root).resolve())
        output = _pick_one(manifest, args.target, engine="slidev")
        slidev.export(manifest, output, fmt=args.format, verbose=args.verbose)
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_export_pptx(args: argparse.Namespace) -> int:
    from . import pptx_export

    try:
        root = Path(args.root).resolve()
        manifest = load_manifest(root)
        output = _pick_one(manifest, args.target, engine="slidev")
        pptx_export.export_pptx(
            root,
            entry=output.entry,
            out=args.out,
            autoplay=not args.no_autoplay,
            with_clicks=not args.no_clicks,
            verbose=args.verbose,
        )
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_preview(args: argparse.Namespace) -> int:
    """Serve a built output over HTTP so you can preview it locally.

    Browsers refuse to load ES modules from file:// URLs, so opening
    <out>/index.html directly shows a blank page. This subcommand serves
    the output dir via Python's http.server — the same way a static bucket
    will.
    """
    import functools
    import http.server
    import socketserver
    import webbrowser

    root = Path(args.root).resolve()
    try:
        manifest = load_manifest(root)
        if args.out is not None:
            out_dir = root / args.out
            label = args.out
        else:
            output = _pick_one(manifest, args.target)
            out_dir = root / output.out
            label = output.out
    except Exception as e:
        return _fail(e, args.verbose)

    if not out_dir.is_dir():
        print(
            f"  no {label}/ at {out_dir}. run `presentation-sanity build` first.",
            file=sys.stderr,
        )
        return 1

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(out_dir)
    )

    try:
        with socketserver.TCPServer(("", args.port), handler) as httpd:
            url = f"http://localhost:{args.port}/"
            print(f"  serving {out_dir}")
            print(f"  → {url}  (Ctrl-C to stop)")
            if not args.no_open:
                webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
        return 0
    except OSError as e:
        print(f"  error: {e} (try a different --port)", file=sys.stderr)
        return 1
    return 0


def cmd_outputs(args: argparse.Namespace) -> int:
    """List the printouts this subject declares."""
    try:
        manifest = load_manifest(Path(args.root).resolve())
    except Exception as e:
        return _fail(e, args.verbose)

    if not manifest.outputs:
        print("  no outputs declared under `outputs:` in manifest.yaml")
        return 0
    width = max(len(k) for k in manifest.outputs)
    print(f"  {manifest.title}")
    for key, o in manifest.outputs.items():
        built = "built" if (manifest.root / o.out).is_dir() else "-"
        print(f"    {key:<{width}}  {o.engine:<9} {o.entry:<14} → {o.out:<14} [{built}]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="presentation-sanity",
        description="Build slides and blogs from a single manifest.yaml.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common_root = argparse.ArgumentParser(add_help=False)
    common_root.add_argument(
        "--root",
        default=".",
        help="Subject root directory (containing manifest.yaml). Default: cwd",
    )
    common_root.add_argument("-v", "--verbose", action="store_true")

    p_build = sub.add_parser(
        "build",
        parents=[common_root],
        help="Full build: figures + manim + every declared output",
    )
    p_build.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help="Output key(s) from `outputs:`. Default: all of them.",
    )
    p_build.add_argument("--skip-manim", action="store_true")
    p_build.add_argument(
        "--skip-render",
        action="store_true",
        help="Render shared artifacts only; skip slidev/vitepress.",
    )
    p_build.add_argument(
        "--force-manim", action="store_true", help="Re-render all scenes ignoring cache"
    )
    p_build.add_argument("--skip-figures", action="store_true")
    p_build.add_argument(
        "--force-figures",
        action="store_true",
        help="Re-export all figures ignoring cache",
    )
    p_build.add_argument(
        "--base",
        default=None,
        help=(
            "Serve the built site from a subdirectory. Slidev accepts './' for "
            "fully relative paths; VitePress needs an absolute prefix like "
            "'/blog/' (a relative value is coerced to '/')."
        ),
    )
    p_build.add_argument(
        "--out",
        default=None,
        help="Override the output directory. Requires exactly one TARGET.",
    )
    p_build.set_defaults(func=cmd_build)

    p_manim = sub.add_parser(
        "build-manim", parents=[common_root], help="Render manim scenes only"
    )
    p_manim.add_argument(
        "--force", action="store_true", help="Re-render all scenes ignoring cache"
    )
    p_manim.set_defaults(func=cmd_build_manim)

    p_figures = sub.add_parser(
        "build-figures",
        parents=[common_root],
        help="Export Excalidraw figures only (installs the exporter on demand)",
    )
    p_figures.add_argument(
        "--force", action="store_true", help="Re-export all figures ignoring cache"
    )
    p_figures.set_defaults(func=cmd_build_figures)

    p_dev = sub.add_parser(
        "dev",
        parents=[common_root],
        help="Hot-reload dev server for one output (slidev or vitepress)",
    )
    p_dev.add_argument("target", nargs="?", metavar="TARGET")
    p_dev.add_argument("--no-open", action="store_true")
    p_dev.set_defaults(func=cmd_dev)

    p_scaffold = sub.add_parser(
        "scaffold",
        parents=[common_root],
        help="Regenerate .vitepress/ from manifest.yaml without building",
    )
    p_scaffold.add_argument("target", nargs="?", metavar="TARGET")
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_outputs = sub.add_parser(
        "outputs", parents=[common_root], help="List the outputs this subject declares"
    )
    p_outputs.set_defaults(func=cmd_outputs)

    p_export = sub.add_parser(
        "export", parents=[common_root], help="Export slides to PDF/PPTX/PNG/MD"
    )
    p_export.add_argument(
        "format",
        choices=["pdf", "pptx", "png", "md"],
        help="Output format",
    )
    p_export.add_argument("target", nargs="?", metavar="TARGET")
    p_export.set_defaults(func=cmd_export)

    p_export_pptx = sub.add_parser(
        "export-pptx",
        parents=[common_root],
        help=(
            "Export a PPTX that EMBEDS the manim videos (playable in PowerPoint), "
            "unlike `export pptx` which rasterises every slide. Needs ffmpeg + "
            "python-pptx (pip install presentation-sanity[pptx])."
        ),
    )
    p_export_pptx.add_argument("target", nargs="?", metavar="TARGET")
    p_export_pptx.add_argument(
        "--out",
        default=None,
        help="Output .pptx path. Default: exports/<deck-title>.pptx",
    )
    p_export_pptx.add_argument(
        "--no-autoplay",
        action="store_true",
        help="Embed videos as click-to-play instead of auto-starting on slide entry.",
    )
    p_export_pptx.add_argument(
        "--no-clicks",
        action="store_true",
        help=(
            "Collapse each build slide to its final state (one slide per slide) "
            "instead of expanding every v-click into its own slide."
        ),
    )
    p_export_pptx.set_defaults(func=cmd_export_pptx)

    p_preview = sub.add_parser(
        "preview",
        parents=[common_root],
        help="Serve a built output over HTTP for local preview",
    )
    p_preview.add_argument("target", nargs="?", metavar="TARGET")
    p_preview.add_argument("--port", type=int, default=8000)
    p_preview.add_argument(
        "--out",
        default=None,
        help="Serve this directory instead of the target's `out:`.",
    )
    p_preview.add_argument("--no-open", action="store_true")
    p_preview.set_defaults(func=cmd_preview)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
