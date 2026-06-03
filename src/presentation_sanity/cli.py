"""CLI entry point: argparse-based, matching document-sanity's style."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .slidev import DEFAULT_OUT


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build_all
    from .manifest import ManifestError

    try:
        build_all(
            Path(args.root).resolve(),
            skip_manim=args.skip_manim,
            force_manim=args.force_manim,
            skip_figures=args.skip_figures,
            force_figures=args.force_figures,
            skip_slidev=args.skip_slidev,
            base=args.base,
            out=args.out,
            verbose=args.verbose,
        )
        return 0
    except ManifestError as e:
        print(f"  manifest error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_build_manim(args: argparse.Namespace) -> int:
    from . import manim_render
    from .manifest import ManifestError, load_manifest

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
    except ManifestError as e:
        print(f"  manifest error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_build_figures(args: argparse.Namespace) -> int:
    from . import figures_render
    from .manifest import ManifestError, load_manifest

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
    except ManifestError as e:
        print(f"  manifest error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_dev(args: argparse.Namespace) -> int:
    from . import slidev

    try:
        slidev.dev(Path(args.root).resolve(), open_browser=not args.no_open)
        return 0
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        return 1


def cmd_export(args: argparse.Namespace) -> int:
    from . import slidev

    try:
        slidev.export(Path(args.root).resolve(), fmt=args.format, verbose=args.verbose)
        return 0
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        return 1


def cmd_export_pptx(args: argparse.Namespace) -> int:
    from . import pptx_export

    try:
        pptx_export.export_pptx(
            Path(args.root).resolve(),
            out=args.out,
            autoplay=not args.no_autoplay,
            with_clicks=not args.no_clicks,
            verbose=args.verbose,
        )
        return 0
    except Exception as e:
        print(f"  error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_preview(args: argparse.Namespace) -> int:
    """Serve the build output over HTTP so you can preview it locally.

    Browsers refuse to load ES modules from file:// URLs, so opening
    <out>/index.html directly shows a blank page. This subcommand serves
    the output dir via Python's http.server — the same way a static bucket
    will. Defaults to the same dir `build` writes to (DEFAULT_OUT).
    """
    import functools
    import http.server
    import socketserver
    import webbrowser

    out_dir = Path(args.root).resolve() / args.out
    if not out_dir.is_dir():
        print(
            f"  no {args.out}/ at {out_dir}. run `presentation-sanity build` first.",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="presentation-sanity",
        description="Build presentations from a single manifest.yaml.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    common_root = argparse.ArgumentParser(add_help=False)
    common_root.add_argument(
        "--root",
        default=".",
        help="Deck root directory (containing manifest.yaml). Default: cwd",
    )
    common_root.add_argument("-v", "--verbose", action="store_true")

    p_build = sub.add_parser(
        "build", parents=[common_root], help="Full build: manim + slidev"
    )
    p_build.add_argument("--skip-manim", action="store_true")
    p_build.add_argument("--skip-slidev", action="store_true")
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
            "Forward to `slidev build --base <value>` so the built site can be "
            "served from a subdirectory. Use './' for relative asset paths, or a "
            "specific prefix like '/preview/abc/'."
        ),
    )
    p_build.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=(
            f"Output directory (forwarded to `slidev build --out`). Default "
            f"{DEFAULT_OUT!r} — not 'dist'/'build'/'out', which many hosts and "
            "tools auto-ignore."
        ),
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

    p_dev = sub.add_parser("dev", parents=[common_root], help="slidev dev (hot reload)")
    p_dev.add_argument("--no-open", action="store_true")
    p_dev.set_defaults(func=cmd_dev)

    p_export = sub.add_parser(
        "export", parents=[common_root], help="Export to PDF/PPTX/PNG/MD"
    )
    p_export.add_argument(
        "format",
        choices=["pdf", "pptx", "png", "md"],
        help="Output format",
    )
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
        help="Serve the build output over HTTP for local preview (no Slidev dev server)",
    )
    p_preview.add_argument("--port", type=int, default=8000)
    p_preview.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"Directory to serve (must match `build --out`). Default {DEFAULT_OUT!r}.",
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
