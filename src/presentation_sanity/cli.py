"""CLI entry point: argparse-based, matching document-sanity's style."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build_all
    from .manifest import ManifestError

    try:
        build_all(
            Path(args.root).resolve(),
            skip_manim=args.skip_manim,
            force_manim=args.force_manim,
            skip_slidev=args.skip_slidev,
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


def cmd_preview(args: argparse.Namespace) -> int:
    """Serve dist/ over HTTP so you can preview the static build locally.

    Browsers refuse to load ES modules from file:// URLs, so opening
    dist/index.html directly shows a blank page. This subcommand serves
    dist/ via Python's http.server — the same way a static bucket will.
    """
    import functools
    import http.server
    import socketserver
    import webbrowser

    dist = Path(args.root).resolve() / "dist"
    if not dist.is_dir():
        print(
            f"  no dist/ at {dist}. run `presentation-sanity build` first.",
            file=sys.stderr,
        )
        return 1

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(dist)
    )

    try:
        with socketserver.TCPServer(("", args.port), handler) as httpd:
            url = f"http://localhost:{args.port}/"
            print(f"  serving {dist}")
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
    p_build.set_defaults(func=cmd_build)

    p_manim = sub.add_parser(
        "build-manim", parents=[common_root], help="Render manim scenes only"
    )
    p_manim.add_argument(
        "--force", action="store_true", help="Re-render all scenes ignoring cache"
    )
    p_manim.set_defaults(func=cmd_build_manim)

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

    p_preview = sub.add_parser(
        "preview",
        parents=[common_root],
        help="Serve dist/ over HTTP for local preview (no Slidev dev server)",
    )
    p_preview.add_argument("--port", type=int, default=8000)
    p_preview.add_argument("--no-open", action="store_true")
    p_preview.set_defaults(func=cmd_preview)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
