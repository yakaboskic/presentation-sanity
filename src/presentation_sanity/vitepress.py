"""Scaffold and drive a VitePress site from the manifest.

Slidev and VitePress sit on the same substrate (Vite + Vue 3 + markdown-it +
Shiki), which is the whole reason VitePress is the blog half of this tool: the
subject's `components/`, `composables/`, `manifest.yaml` and `public/` are
consumed *unchanged* by both. `<DataValue var="n" />` in `blog.md` reads the
same YAML as the same tag in `slides.md`.

`.vitepress/` is generated, not authored — it is rewritten from manifest.yaml
before every dev/build and belongs in .gitignore. That keeps a subject repo
down to its content (entry markdown + manifest + shared components) and lets
theme improvements arrive with a package upgrade instead of a manual merge.

In a project, each presentation's blog gets its own generated root under
`.cache/vitepress/<id>/`, with srcDir pointed back at the project root and the
site narrowed to that presentation's folder.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .bibliography import Bibliography, load_bibliography
from .manifest import PRESENTATIONS_DIR, Manifest, Output

if TYPE_CHECKING:
    from .project import Presentation

CONFIG_DIR = ".vitepress"

# Where a project generates each presentation's VitePress root. One root per
# presentation keeps folders under presentations/ clean and lets two blogs run
# `dev` at once.
PROJECT_VP_ROOT = Path(".cache") / "vitepress"

# path-to-regexp metacharacters, escaped when a folder name lands in a rewrite.
_REWRITE_SPECIAL = re.compile(r"([()\[\]{}*+?:\\])")

# Never treat these as blog pages when srcDir is the subject root.
BASE_SRC_EXCLUDE = [
    "**/node_modules/**",
    "**/dist/**",
    "**/site/**",
    "**/.venv/**",
    "**/exports/**",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
]


def _check_npx() -> None:
    if shutil.which("npx") is None:
        raise RuntimeError(
            "npx not found on PATH. Install Node.js >= 20 (https://nodejs.org)."
        )


def _check_node_modules(root: Path) -> None:
    if not (root / "node_modules" / "vitepress").is_dir():
        raise RuntimeError(
            f"VitePress not installed in {root}. Add it to package.json "
            "(`npm add -D vitepress`) and run `npm install` there first."
        )


def _check_entry(root: Path, output: Output) -> None:
    entry = root / output.entry
    if not entry.is_file():
        raise RuntimeError(f"output {output.key!r}: entry {entry} not found")


def _has_package(root: Path, name: str) -> bool:
    """True if a node package resolves inside the subject's node_modules."""
    return (root / "node_modules" / Path(name)).is_dir()


def vitepress_root(manifest: Manifest, presentation: "Presentation | None") -> Path:
    """The directory VitePress treats as its root (it holds `.vitepress/`)."""
    if presentation is None:
        return manifest.root
    return manifest.root / PROJECT_VP_ROOT / presentation.id


def _rel(path: Path, start: Path) -> str:
    """POSIX relative path for an import/glob literal in generated code."""
    rel = Path(os.path.relpath(path, start)).as_posix()
    return rel if rel.startswith(".") else f"./{rel}"


def _read_asset(name: str) -> str:
    return (
        resources.files("presentation_sanity")
        .joinpath("assets/vitepress")
        .joinpath(name)
        .read_text()
    )


def _normalize_base(base: str | None) -> str:
    """VitePress needs an absolute, slash-terminated base.

    Unlike Slidev, VitePress does server-side rendering and route matching, so
    Vite's relative `./` base is not supported — it would break router links
    even though the assets resolved. Coerce the Slidev-style value rather than
    emitting a site that 404s its own routes.
    """
    if base in (None, "", "./", "."):
        return "/"
    assert base is not None
    if not base.startswith("/"):
        base = "/" + base
    if not base.endswith("/"):
        base = base + "/"
    return base


def _theme_config(manifest: Manifest, output: Output) -> dict[str, Any]:
    """themeConfig, with manifest authors surfaced as a footer by default."""
    extra = output.extra
    theme: dict[str, Any] = {}

    if "nav" in extra:
        theme["nav"] = extra["nav"]
    if "sidebar" in extra:
        theme["sidebar"] = extra["sidebar"]
    if "socialLinks" in extra:
        theme["socialLinks"] = extra["socialLinks"]
    if "outline" in extra:
        theme["outline"] = extra["outline"]
    else:
        theme["outline"] = [2, 3]

    if "footer" in extra:
        theme["footer"] = extra["footer"]
    else:
        authors = manifest.metadata.get("authors") or []
        names = [a.get("name") for a in authors if isinstance(a, dict) and a.get("name")]
        if names:
            theme["footer"] = {"message": " · ".join(names)}

    # User-supplied themeConfig wins over everything derived above.
    theme.update(extra.get("themeConfig") or {})
    return theme


def _project_src_exclude(
    manifest: Manifest, presentation: "Presentation", output: Output
) -> list[str]:
    """Globs that leave exactly one presentation's pages in the site.

    srcDir stays the project root — VitePress copies `<srcDir>/public` verbatim
    and resolves `public/` from it, which is what makes the shared assets work —
    so everything else under the root has to be excluded. There is no include
    list and fast-glob can't un-ignore, so name the outside explicitly: other
    top-level dirs, root-level markdown, and at each level from presentations/
    down to this folder, the sibling folders and loose markdown files.
    """
    root = manifest.root
    exclude = list(BASE_SRC_EXCLUDE) + ["*.md"]
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith(".") and child.name != PRESENTATIONS_DIR:
            exclude.append(f"{child.name}/**")

    level = root / PRESENTATIONS_DIR
    for part in presentation.dir.relative_to(level).parts:
        level_rel = level.relative_to(root).as_posix()
        exclude.append(f"{level_rel}/*.md")
        for sibling in sorted(level.iterdir()):
            if sibling.is_dir() and sibling.name != part:
                exclude.append(f"{level_rel}/{sibling.name}/**")
        level = level / part

    pres_rel = presentation.dir.relative_to(root).as_posix()
    for other in presentation.outputs.values():
        if other.key != output.key:
            exclude.append(Path(other.entry).relative_to(root).as_posix())
    exclude.append(f"{pres_rel}/exports/**")
    exclude += [f"{pres_rel}/{g}" for g in (output.extra.get("exclude") or [])]
    return exclude


def _project_rewrites(manifest: Manifest, presentation: "Presentation", output: Output) -> dict[str, str]:
    """Serve the presentation's entry at `/` and its other pages beside it."""
    root = manifest.root
    pres_rel = _REWRITE_SPECIAL.sub(r"\\\1", presentation.dir.relative_to(root).as_posix())
    entry_rel = _REWRITE_SPECIAL.sub(
        r"\\\1", Path(output.entry).relative_to(presentation.dir).as_posix()
    )
    # Ordered: VitePress applies the first rule that matches a page.
    return {f"{pres_rel}/{entry_rel}": "index.md", f"{pres_rel}/:slug*": ":slug*"}


def build_config(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    presentation: "Presentation | None" = None,
) -> dict[str, Any]:
    """The VitePress site config derived from the manifest.

    `srcDir` stays at the subject root so `public/` resolves to the shared
    `<root>/public` (VitePress resolves publicDir relative to srcDir) — the
    same `/manim/<key>.webm` URL the Slidev deck uses. Every *other* output's
    entry document is excluded so `slides.md` doesn't become a blog page, and
    the entry is rewritten to `index.md` so the post is served at `/`.

    In a project (`presentation` given) srcDir is the project root and the site
    is narrowed to that presentation's folder; paths are absolute because the
    generated root lives under `.cache/vitepress/<id>/`.
    """
    root = manifest.root
    extra = output.extra

    if presentation is None:
        exclude = list(BASE_SRC_EXCLUDE)
        exclude += [
            o.entry for o in manifest.outputs.values() if o.key != output.key
        ]
        exclude += list(extra.get("exclude") or [])
        title = output.title or manifest.title
        description = output.description or manifest.metadata.get("description") or ""
        paths: dict[str, Any] = {
            # outDir is resolved relative to the VitePress root, which we always
            # invoke as the subject root — so this matches `output.out` verbatim.
            "outDir": output.out,
            "cacheDir": ".cache/vitepress",
            "rewrites": {output.entry: "index.md"},
        }
    else:
        exclude = _project_src_exclude(manifest, presentation, output)
        title = output.title or presentation.title
        description = (
            output.description or presentation.metadata.get("description") or ""
        )
        vp_root = vitepress_root(manifest, presentation)
        paths = {
            "srcDir": str(root),
            "outDir": str((root / output.out).resolve()),
            "cacheDir": str(vp_root / "cache"),
            "rewrites": _project_rewrites(manifest, presentation, output),
        }

    config: dict[str, Any] = {
        "title": title,
        "description": description,
        "base": _normalize_base(base if base is not None else extra.get("base")),
        **{k: v for k, v in paths.items() if k != "rewrites"},
        "srcExclude": exclude,
        # Emit `foo.html` rather than extensionless routes: works on a dumb
        # static bucket with no rewrite rules, same premise as the deck's
        # hash routing.
        "cleanUrls": False,
        "rewrites": paths["rewrites"],
        "lastUpdated": bool(extra.get("lastUpdated", True)),
        "themeConfig": _theme_config(manifest, output),
    }

    if extra.get("head"):
        config["head"] = extra["head"]

    # Escape hatch for top-level VitePress options this schema doesn't name —
    # `appearance`, `lang`, `titleTemplate`, `ignoreDeadLinks`, `sitemap`, … .
    # Merged last so it can also override anything derived above; `outDir` and
    # `rewrites` are excluded because the build orchestrator owns where output
    # lands and which entry becomes `/`.
    passthrough = dict(extra.get("vitepress") or {})
    for owned in ("outDir", "rewrites", "cacheDir", "srcDir"):
        passthrough.pop(owned, None)
    config.update(passthrough)

    markdown: dict[str, Any] = dict(extra.get("markdown") or {})
    # Math is opt-in in VitePress and needs a peer package. Enable it only when
    # that package is installed, so a subject without it still builds.
    if "math" not in markdown:
        if _has_package(root, "markdown-it-mathjax3"):
            # Forwarded verbatim to markdown-it-mathjax3, which hands `tex` to
            # MathJax's TeX input jax (macros, tags, packages) and `svg` to its
            # SVG output jax. `true` would work but loses the manifest's macros.
            math_opts: dict[str, Any] = {}
            tex = manifest.math.tex_options()
            if tex:
                math_opts["tex"] = tex
            if manifest.math.svg:
                math_opts["svg"] = manifest.math.svg
            markdown["math"] = math_opts or True
        else:
            markdown["math"] = False
    config["markdown"] = markdown

    return config


def resolve_bibliography(manifest: Manifest) -> Bibliography | None:
    """Parse the manifest's `.bib` sources, or None when none are declared."""
    cfg = manifest.bibliography
    if not cfg.sources:
        return None
    return load_bibliography(
        manifest.root,
        cfg.sources,
        style=cfg.style,
        sort=cfg.sort,
        title=cfg.title,
        heading=cfg.heading,
        link=cfg.link,
    )


def _component_dirs(manifest: Manifest, presentation: "Presentation | None") -> list[Path]:
    """Component directories in priority order — later ones override earlier."""
    root = manifest.root
    if presentation is None:
        return [root / "components"]
    return [root / "shared" / "components", presentation.dir / "components"]


def _aliases(manifest: Manifest, presentation: "Presentation | None") -> dict[str, str]:
    """Import aliases for components; a single subject keeps relative imports."""
    if presentation is None:
        return {}
    root = manifest.root
    return {"@project": str(root), "@shared": str(root / "shared")}


def _stylesheets(manifest: Manifest, presentation: "Presentation | None") -> list[Path]:
    """Blog stylesheets that exist, imported last so they win over defaults."""
    root = manifest.root
    if presentation is None:
        candidates = [root / "blog.css"]
    else:
        candidates = [root / "shared" / "blog.css", presentation.dir / "blog.css"]
    return [c for c in candidates if c.is_file()]


def scaffold(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    presentation: "Presentation | None" = None,
    verbose: bool = False,
) -> Path:
    """(Re)generate the `.vitepress/` directory and return its path.

    A single subject gets `<root>/.vitepress/`; a presentation in a project
    gets `<root>/.cache/vitepress/<id>/.vitepress/`.
    """
    root = manifest.root
    config_dir = vitepress_root(manifest, presentation) / CONFIG_DIR
    theme_dir = config_dir / "theme"
    theme_dir.mkdir(parents=True, exist_ok=True)

    config = build_config(manifest, output, base=base, presentation=presentation)

    # --- config.mts ---------------------------------------------------------
    imports: list[str] = []
    plugins: list[str] = []
    if _has_package(root, "@modyfi/vite-plugin-yaml"):
        imports.append("import yaml from '@modyfi/vite-plugin-yaml'")
        plugins.append("yaml()")
    else:
        print(
            "  warning: @modyfi/vite-plugin-yaml is not installed — "
            "<DataValue> cannot import manifest.yaml. "
            "run `npm add -D @modyfi/vite-plugin-yaml`.",
            file=sys.stderr,
        )
    if not config["markdown"].get("math"):
        print(
            "  note: math rendering off — `npm add -D markdown-it-mathjax3` "
            "to enable $…$ in the blog."
        )

    environments = (
        list(manifest.math.environments) if config["markdown"].get("math") else []
    )

    # Citations are formatted here, once, and injected as a literal: the
    # markdown-it side only picks labels and ordering, so the published page
    # carries no citation runtime — the same bargain the math rendering makes.
    bib = resolve_bibliography(manifest)
    if bib is not None:
        print(f"  bibliography: {len(bib.entries)} entries")
    bib_json = json.dumps(
        bib.to_json_dict() if bib is not None else None, indent=2
    )

    config_src = (
        _read_asset("config.mts")
        .replace("__IMPORTS__", "\n".join(imports))
        .replace("__CONFIG_JSON__", json.dumps(config, indent=2))
        .replace("__ENVIRONMENTS__", json.dumps(environments))
        .replace("__BIBLIOGRAPHY__", bib_json)
        .replace("__VITE_PLUGINS__", ", ".join(plugins))
        .replace("__ALIASES__", json.dumps(_aliases(manifest, presentation)))
    )
    (config_dir / "config.mts").write_text(config_src)

    # --- theme/index.ts -----------------------------------------------------
    (theme_dir / "citations.css").write_text(_read_asset("citations.css"))
    theme_imports = ["import './citations.css'"]
    theme_imports += [f"import '{_rel(css, theme_dir)}'" for css in _stylesheets(manifest, presentation)]

    globs = "\n".join(
        f"  import.meta.glob<Record<string, any>>('{_rel(d, theme_dir)}/*.vue', {{ eager: true }}),"
        for d in _component_dirs(manifest, presentation)
    )
    theme_src = (
        _read_asset("theme.ts")
        .replace("__THEME_IMPORTS__", "\n".join(theme_imports))
        .replace("__COMPONENT_GLOBS__", globs)
    )
    (theme_dir / "index.ts").write_text(theme_src)

    if verbose:
        print(f"  scaffolded {config_dir}", file=sys.stderr)
    return config_dir


def build(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    presentation: "Presentation | None" = None,
    verbose: bool = False,
) -> None:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    _check_entry(root, output)
    scaffold(manifest, output, base=base, presentation=presentation, verbose=verbose)
    cmd = ["npx", "vitepress", "build", str(vitepress_root(manifest, presentation))]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)


def dev(
    manifest: Manifest,
    output: Output,
    *,
    presentation: "Presentation | None" = None,
    open_browser: bool = True,
    verbose: bool = False,
) -> None:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    _check_entry(root, output)
    scaffold(manifest, output, presentation=presentation, verbose=verbose)
    cmd = ["npx", "vitepress", "dev", str(vitepress_root(manifest, presentation))]
    if open_browser:
        cmd.append("--open")
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=False)
