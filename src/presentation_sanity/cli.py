"""CLI entry point: argparse-based, matching document-sanity's style.

In a single-subject repo, verbs take an optional output *target* — a key
under `outputs:` in manifest.yaml:

    presentation-sanity build              # every declared output
    presentation-sanity build blog         # just the blog
    presentation-sanity dev slides         # slidev dev server
    presentation-sanity export pdf         # slides only

In a project (a repo with `presentations/`), a target is a presentation id,
optionally with an output — `PRESENTATION[:OUTPUT]`. Inside a presentation's
folder that presentation is the default:

    presentation-sanity list                              # what the project holds
    presentation-sanity new kickoff/v2 --from kickoff/v1  # fork a version
    presentation-sanity build                             # everything → site/
    presentation-sanity build kickoff                     # every version of a talk
    presentation-sanity dev kickoff/v2:blog
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .manifest import Manifest, ManifestError, Output, load_manifest
from .project import Project, find_project_root, load_project, pick_one


def _fail(e: Exception, verbose: bool) -> int:
    if isinstance(e, ManifestError):
        print(f"  manifest error: {e}", file=sys.stderr)
        return 2
    print(f"  error: {e}", file=sys.stderr)
    if verbose:
        import traceback

        traceback.print_exc()
    return 1


def _locate(args: argparse.Namespace) -> tuple[Path, Path, bool]:
    """(root, cwd, is_project). A project is found from anywhere inside it."""
    start = Path(args.root).resolve()
    project_root = find_project_root(start)
    if project_root is not None:
        return project_root, start, True
    return start, start, False


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
    from .build import build_all, build_project

    try:
        root, cwd, is_project = _locate(args)
        options = dict(
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
        if is_project:
            build_project(root, cwd=cwd, **options)
        else:
            build_all(root, **options)
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
        manifest = load_manifest(_locate(args)[0])
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
        manifest = load_manifest(_locate(args)[0])
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
        root, cwd, is_project = _locate(args)
        open_browser = not args.no_open
        if is_project:
            project = load_project(root)
            presentation, output = pick_one(project, args.target, cwd)
            print(f"  dev {presentation.id}:{output.key} ({output.engine})")
            if output.engine == "vitepress":
                vitepress.dev(
                    project.manifest, output, presentation=presentation,
                    open_browser=open_browser, verbose=args.verbose,
                )
            else:
                slidev.dev(
                    project.manifest, output,
                    open_browser=open_browser, verbose=args.verbose,
                )
            return 0
        manifest = load_manifest(root)
        output = _pick_one(manifest, args.target)
        engine = vitepress if output.engine == "vitepress" else slidev
        engine.dev(manifest, output, open_browser=open_browser, verbose=args.verbose)
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_scaffold(args: argparse.Namespace) -> int:
    """Write the generated VitePress config without building."""
    from . import vitepress

    try:
        root, cwd, is_project = _locate(args)
        if is_project:
            project = load_project(root)
            presentation, output = pick_one(project, args.target, cwd, engine="vitepress")
            path = vitepress.scaffold(
                project.manifest, output, presentation=presentation, verbose=args.verbose
            )
        else:
            manifest = load_manifest(root)
            output = _pick_one(manifest, args.target, engine="vitepress")
            path = vitepress.scaffold(manifest, output, verbose=args.verbose)
        print(f"  → {path}")
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_export(args: argparse.Namespace) -> int:
    from . import slidev

    try:
        root, cwd, is_project = _locate(args)
        if is_project:
            project = load_project(root)
            presentation, output = pick_one(project, args.target, cwd, engine="slidev")
            # Next to the deck rather than in the shared cwd: two versions'
            # exports must not overwrite each other.
            out = presentation.dir / "exports" / f"{Path(output.entry).stem}-export"
            slidev.export(
                project.manifest, output, fmt=args.format, out=out, verbose=args.verbose
            )
            return 0
        manifest = load_manifest(root)
        output = _pick_one(manifest, args.target, engine="slidev")
        slidev.export(manifest, output, fmt=args.format, verbose=args.verbose)
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def cmd_export_pptx(args: argparse.Namespace) -> int:
    from . import pptx_export

    try:
        root, cwd, is_project = _locate(args)
        options = dict(
            out=args.out,
            autoplay=not args.no_autoplay,
            with_clicks=not args.no_clicks,
            verbose=args.verbose,
        )
        if is_project:
            project = load_project(root)
            presentation, output = pick_one(project, args.target, cwd, engine="slidev")
            pptx_export.export_pptx(
                root,
                entry=output.entry,
                title=presentation.title,
                exports_dir=presentation.dir / "exports",
                **options,
            )
            return 0
        manifest = load_manifest(root)
        output = _pick_one(manifest, args.target, engine="slidev")
        pptx_export.export_pptx(root, entry=output.entry, **options)
        return 0
    except Exception as e:
        return _fail(e, args.verbose)


def _serve(directory: Path, url_path: str, port: int, open_browser: bool) -> int:
    import functools
    import http.server
    import socketserver
    import webbrowser

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    try:
        with socketserver.TCPServer(("", port), handler) as httpd:
            url = f"http://localhost:{port}/{url_path}"
            print(f"  serving {directory}")
            print(f"  → {url}  (Ctrl-C to stop)")
            if open_browser:
                webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
        return 0
    except OSError as e:
        print(f"  error: {e} (try a different --port)", file=sys.stderr)
        return 1
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    """Serve built output over HTTP so you can preview it locally.

    Browsers refuse to load ES modules from file:// URLs, so opening
    <out>/index.html directly shows a blank page. This subcommand serves
    the output dir via Python's http.server — the same way a static bucket
    will. In a project it serves all of `site/` (so the index and every base
    path behave as deployed) and opens the selected output.
    """
    try:
        root, cwd, is_project = _locate(args)
        url_path = ""
        if args.out is not None:
            directory, label = root / args.out, args.out
        elif is_project:
            project = load_project(root)
            directory, label = project.site_dir, "site"
            if args.target is not None:
                _, output = pick_one(project, args.target, cwd)
                out_dir = Path(output.out)
                try:
                    url_path = out_dir.resolve().relative_to(directory.resolve()).as_posix() + "/"
                except ValueError:
                    directory, label = out_dir, output.out
                if not out_dir.is_dir():
                    print(
                        f"  {args.target} is not built yet. run "
                        f"`presentation-sanity build {args.target}` first.",
                        file=sys.stderr,
                    )
                    return 1
        else:
            output = _pick_one(load_manifest(root), args.target)
            directory, label = root / output.out, output.out
    except Exception as e:
        return _fail(e, args.verbose)

    if not directory.is_dir():
        print(
            f"  no {label}/ at {directory}. run `presentation-sanity build` first.",
            file=sys.stderr,
        )
        return 1
    return _serve(directory, url_path, args.port, not args.no_open)


def _built(path: str | Path) -> str:
    return "built" if Path(path).is_dir() else "-"


def _list_project(project: Project) -> None:
    count = len(project.presentations)
    print(f"  {project.title} — {count} presentation{'s' * (count != 1)}")
    if not count:
        print("    (none yet — `presentation-sanity new <name>`)")
        return
    width = max(len(pid) for pid in project.presentations)
    for pid, p in project.presentations.items():
        outs = "  ".join(f"{k}[{_built(o.out)}]" for k, o in p.outputs.items()) or "(no entry)"
        lineage = f"  (from {p.metadata['from']})" if p.metadata.get("from") else ""
        print(f"    {pid:<{width}}  {outs:<28} {p.title}{lineage}")


def cmd_list(args: argparse.Namespace) -> int:
    """List what this repo builds: a project's presentations, or a subject's outputs."""
    try:
        root, _, is_project = _locate(args)
        if is_project:
            _list_project(load_project(root))
            return 0
        manifest = load_manifest(root)
    except Exception as e:
        return _fail(e, args.verbose)

    if not manifest.outputs:
        print("  no outputs declared under `outputs:` in manifest.yaml")
        return 0
    width = max(len(k) for k in manifest.outputs)
    print(f"  {manifest.title}")
    for key, o in manifest.outputs.items():
        built = _built(manifest.root / o.out)
        print(f"    {key:<{width}}  {o.engine:<9} {o.entry:<14} → {o.out:<14} [{built}]")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """Create a presentation, or fork one into a new version."""
    from .project import create_presentation

    try:
        root, _, is_project = _locate(args)
        if not is_project:
            raise ManifestError(
                "`new` works in a project — a repo with a presentations/ directory "
                "next to manifest.yaml. Create presentations/ and move each deck into "
                "its own folder there first."
            )
        project = load_project(root)
        dest = create_presentation(project, args.id, from_id=args.from_id, title=args.title)
    except Exception as e:
        return _fail(e, args.verbose)

    pid = dest.relative_to(root / "presentations").as_posix()
    print(f"  → {os.path.relpath(dest)}")
    if args.from_id:
        print(f"  forked from {args.from_id}; edit {pid}/slides.md headmatter to retitle")
    print(f"  next: presentation-sanity dev {pid}")
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
        help=(
            "Where to start (default: cwd). Inside a project, the project root is "
            "found by walking up, and a presentation folder selects that presentation."
        ),
    )
    common_root.add_argument("-v", "--verbose", action="store_true")

    target_help = (
        "In a project: PRESENTATION[:OUTPUT] (a presentation id, a folder of "
        "versions, or a path). Otherwise: an output key from `outputs:`."
    )

    p_build = sub.add_parser(
        "build",
        parents=[common_root],
        help="Full build: figures + manim + every selected output",
    )
    p_build.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help=target_help + " Default: everything (or the current presentation).",
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
            "Serve the built site from a subdirectory. In a project this is the "
            "deploy prefix for all of site/ (e.g. '/talks/'). Otherwise Slidev "
            "accepts './' for fully relative paths; VitePress needs an absolute "
            "prefix like '/blog/' (a relative value is coerced to '/')."
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
    p_dev.add_argument("target", nargs="?", metavar="TARGET", help=target_help)
    p_dev.add_argument("--no-open", action="store_true")
    p_dev.set_defaults(func=cmd_dev)

    p_new = sub.add_parser(
        "new",
        parents=[common_root],
        help="Create a presentation in this project, or fork one (--from) into a new version",
    )
    p_new.add_argument("id", help="Folder under presentations/, e.g. kickoff/v2")
    p_new.add_argument(
        "--from", dest="from_id", default=None, metavar="ID",
        help="Copy this presentation's folder instead of starting blank",
    )
    p_new.add_argument("--title", default=None, help="Deck title (headmatter `title:`)")
    p_new.set_defaults(func=cmd_new)

    p_scaffold = sub.add_parser(
        "scaffold",
        parents=[common_root],
        help="Regenerate the VitePress config from manifest.yaml without building",
    )
    p_scaffold.add_argument("target", nargs="?", metavar="TARGET", help=target_help)
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_list = sub.add_parser(
        "list",
        aliases=["outputs"],
        parents=[common_root],
        help="List the presentations (or outputs) this repo builds",
    )
    p_list.set_defaults(func=cmd_list)

    p_export = sub.add_parser(
        "export", parents=[common_root], help="Export slides to PDF/PPTX/PNG/MD"
    )
    p_export.add_argument(
        "format",
        choices=["pdf", "pptx", "png", "md"],
        help="Output format",
    )
    p_export.add_argument("target", nargs="?", metavar="TARGET", help=target_help)
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
    p_export_pptx.add_argument("target", nargs="?", metavar="TARGET", help=target_help)
    p_export_pptx.add_argument(
        "--out",
        default=None,
        help=(
            "Output .pptx path. Default: exports/<deck-title>.pptx (in a project, "
            "inside the presentation's folder)"
        ),
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
        help="Serve built output over HTTP for local preview",
    )
    p_preview.add_argument("target", nargs="?", metavar="TARGET", help=target_help)
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
