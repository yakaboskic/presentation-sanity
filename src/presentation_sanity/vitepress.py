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
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from .bibliography import Bibliography, load_bibliography
from .manifest import Manifest, Output

CONFIG_DIR = ".vitepress"

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


def _has_package(root: Path, name: str) -> bool:
    """True if a node package resolves inside the subject's node_modules."""
    return (root / "node_modules" / Path(name)).is_dir()


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


def build_config(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
) -> dict[str, Any]:
    """The VitePress site config derived from the manifest.

    `srcDir` stays at the subject root so `public/` resolves to the shared
    `<root>/public` (VitePress resolves publicDir relative to srcDir) — the
    same `/manim/<key>.webm` URL the Slidev deck uses. Every *other* output's
    entry document is excluded so `slides.md` doesn't become a blog page, and
    the entry is rewritten to `index.md` so the post is served at `/`.
    """
    root = manifest.root
    extra = output.extra

    exclude = list(BASE_SRC_EXCLUDE)
    exclude += [
        o.entry for o in manifest.outputs.values() if o.key != output.key
    ]
    exclude += list(extra.get("exclude") or [])

    config: dict[str, Any] = {
        "title": output.title or manifest.title,
        "description": output.description
        or manifest.metadata.get("description")
        or "",
        "base": _normalize_base(base if base is not None else extra.get("base")),
        # outDir is resolved relative to the VitePress root, which we always
        # invoke as the subject root — so this matches `output.out` verbatim.
        "outDir": output.out,
        "cacheDir": ".cache/vitepress",
        "srcExclude": exclude,
        # Emit `foo.html` rather than extensionless routes: works on a dumb
        # static bucket with no rewrite rules, same premise as the deck's
        # hash routing.
        "cleanUrls": False,
        "rewrites": {output.entry: "index.md"},
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
    for owned in ("outDir", "rewrites", "cacheDir"):
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


def scaffold(
    manifest: Manifest,
    output: Output,
    *,
    base: str | None = None,
    verbose: bool = False,
) -> Path:
    """(Re)generate `<root>/.vitepress/` and return its path."""
    root = manifest.root
    config_dir = root / CONFIG_DIR
    theme_dir = config_dir / "theme"
    theme_dir.mkdir(parents=True, exist_ok=True)

    config = build_config(manifest, output, base=base)

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
    )
    (config_dir / "config.mts").write_text(config_src)

    # --- theme/index.ts -----------------------------------------------------
    theme_imports: list[str] = []
    layout = ""
    if (root / "components" / "ProvenancePanel.vue").is_file():
        theme_imports.append(
            "import ProvenancePanel from '../../components/ProvenancePanel.vue'"
        )
        layout = (
            "  Layout() {\n"
            "    return h(DefaultTheme.Layout, null, {\n"
            "      'layout-bottom': () => h(ProvenancePanel),\n"
            "    })\n"
            "  },"
        )
    else:
        # `h` would be an unused import without the Layout override.
        theme_imports.append("void h")

    (theme_dir / "citations.css").write_text(_read_asset("citations.css"))
    theme_imports.append("import './citations.css'")

    blog_css = root / "blog.css"
    if blog_css.is_file():
        # Last, so the subject's own styles win over the defaults above.
        theme_imports.append("import '../../blog.css'")

    theme_src = (
        _read_asset("theme.ts")
        .replace("__THEME_IMPORTS__", "\n".join(theme_imports))
        .replace("__LAYOUT__", layout)
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
    verbose: bool = False,
) -> None:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    scaffold(manifest, output, base=base, verbose=verbose)
    cmd = ["npx", "vitepress", "build", "."]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=True)


def dev(
    manifest: Manifest,
    output: Output,
    *,
    open_browser: bool = True,
    verbose: bool = False,
) -> None:
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    scaffold(manifest, output, verbose=verbose)
    cmd = ["npx", "vitepress", "dev", "."]
    if open_browser:
        cmd.append("--open")
    subprocess.run(cmd, cwd=root, check=False)


def preview(
    manifest: Manifest,
    output: Output,
    *,
    port: int = 4173,
    verbose: bool = False,
) -> None:
    """`vitepress preview` — serves outDir with the configured base applied."""
    root = manifest.root
    _check_npx()
    _check_node_modules(root)
    cmd = ["npx", "vitepress", "preview", ".", "--port", str(port)]
    if verbose:
        print(f"  $ (cwd={root}) {' '.join(cmd)}", file=sys.stderr)
    subprocess.run(cmd, cwd=root, check=False)
