"""Parse and validate the deck's manifest.yaml.

The manifest is the single source of configuration for a *subject* — the
thing you are explaining. A subject has shared inputs (variables, manim
scenes, excalidraw figures) and one or more **outputs**: different printouts
of the same material. Today that's a Slidev deck and a VitePress blog; the
`outputs:` map is open-ended so a third renderer is a new entry, not a new
schema section.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Engine inferred from the output key when `engine:` is omitted. Keeps the
# common two-output manifest terse without making the field magic elsewhere.
DEFAULT_ENGINE_BY_KEY = {
    "slides": "slidev",
    "deck": "slidev",
    "blog": "vitepress",
    "post": "vitepress",
    "article": "vitepress",
}

KNOWN_ENGINES = ("slidev", "vitepress")

DEFAULT_ENTRY_BY_ENGINE = {
    "slidev": "slides.md",
    "vitepress": "blog.md",
}


@dataclass
class Variable:
    """One entry under `variables:` in the manifest."""

    key: str
    value: Any
    format: str | None = None
    description: str | None = None
    source: str | None = None
    data: list[str] | None = None  # multi-input list (overrides `source` in graph)
    command: str | None = None
    updated: str | None = None

    @classmethod
    def from_raw(cls, key: str, raw: Any) -> "Variable":
        if not isinstance(raw, dict):
            # Shorthand: `KEY: 1234` — bare value, no provenance.
            return cls(key=key, value=raw)
        data = raw.get("data")
        if data is not None and not isinstance(data, list):
            raise ManifestError(
                f"variable {key!r}: `data` must be a list of strings"
            )
        return cls(
            key=key,
            value=raw.get("value"),
            format=raw.get("format"),
            description=raw.get("description"),
            source=raw.get("source"),
            data=data,
            command=raw.get("command"),
            updated=raw.get("updated"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value}
        for k in ("format", "description", "source", "data", "command", "updated"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out


@dataclass
class Scene:
    """One entry under `scenes:` in the manifest."""

    key: str
    source: Path
    class_name: str
    quality: str = "h"
    format: str = "webm"

    @classmethod
    def from_raw(cls, key: str, raw: dict[str, Any], root: Path) -> "Scene":
        if "source" not in raw:
            raise ManifestError(f"scene {key!r} missing required 'source' field")
        if "class" not in raw:
            raise ManifestError(f"scene {key!r} missing required 'class' field")
        return cls(
            key=key,
            source=(root / raw["source"]).resolve(),
            class_name=raw["class"],
            quality=raw.get("quality", "h"),
            format=raw.get("format", "webm"),
        )


@dataclass
class Figure:
    """One entry under `figures:` in the manifest.

    An Excalidraw source (`<name>.excalidraw`) exported to a static image at
    `public/figures/<key>.<format>` by `presentation-sanity build-figures`.
    Mirrors `Scene` (manim) — same source→public/cache→renderer shape.
    """

    key: str
    source: Path
    format: str = "svg"          # svg | png
    scale: float = 1.0
    background: bool = False     # transparent by default (reads on any theme)
    dark: bool = False           # dark-mode export
    embed_scene: bool = False    # embed editable scene data in the export

    @classmethod
    def from_raw(cls, key: str, raw: dict[str, Any], root: Path) -> "Figure":
        if "source" not in raw:
            raise ManifestError(f"figure {key!r} missing required 'source' field")
        return cls(
            key=key,
            source=(root / raw["source"]).resolve(),
            format=raw.get("format", "svg"),
            scale=float(raw.get("scale", 1.0)),
            background=bool(raw.get("background", False)),
            dark=bool(raw.get("dark", False)),
            embed_scene=bool(raw.get("embed_scene", False)),
        )


# Top-level display environments a writer may reasonably start a line with.
# Starred variants are matched automatically, so listing "align" also covers
# "align*". Deliberately excludes in-math-only envs (matrix, cases, …) — those
# belong inside `$$`, and treating them as block-level would swallow prose.
DEFAULT_MATH_ENVIRONMENTS = (
    "align",
    "alignat",
    "equation",
    "gather",
    "multline",
    "flalign",
    "eqnarray",
    "split",
    "aligned",
    "CD",
)


@dataclass
class MathConfig:
    """The `math:` block — TeX settings shared by every output.

    Macros belong here rather than in a `\\newcommand` inside a document: the
    renderer keeps one TeX instance for the whole build, so an in-document
    definition silently leaks into every later block and page, and whether it
    resolves depends on source order. Declared here they are deterministic and,
    like every other manifest input, identical across printouts.
    """

    macros: dict[str, Any] = field(default_factory=dict)
    tags: str = "none"                  # none | ams | all
    environments: tuple[str, ...] = DEFAULT_MATH_ENVIRONMENTS
    packages: list[str] | None = None   # override MathJax's AllPackages
    tex: dict[str, Any] = field(default_factory=dict)   # raw TeX passthrough
    svg: dict[str, Any] = field(default_factory=dict)   # raw SVG output options

    @classmethod
    def from_raw(cls, raw: Any) -> "MathConfig":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ManifestError("`math:` must be a mapping")

        tags = str(raw.get("tags", "none"))
        if tags not in ("none", "ams", "all"):
            raise ManifestError(
                f"math.tags must be one of none, ams, all — got {tags!r}"
            )

        envs = raw.get("environments", True)
        if envs is True:
            environments = DEFAULT_MATH_ENVIRONMENTS
        elif envs is False:
            environments = ()
        elif isinstance(envs, list):
            environments = tuple(str(e) for e in envs)
        else:
            raise ManifestError(
                "math.environments must be true, false, or a list of names"
            )

        macros = raw.get("macros") or {}
        if not isinstance(macros, dict):
            raise ManifestError("math.macros must be a mapping of name → expansion")

        return cls(
            macros=macros,
            tags=tags,
            environments=environments,
            packages=raw.get("packages"),
            tex=raw.get("tex") or {},
            svg=raw.get("svg") or {},
        )

    def tex_options(self) -> dict[str, Any]:
        """MathJax `tex` input options. Raw `tex:` passthrough wins."""
        opts: dict[str, Any] = {}
        if self.macros:
            opts["macros"] = self.macros
        if self.tags != "none":
            opts["tags"] = self.tags
        if self.packages is not None:
            opts["packages"] = self.packages
        opts.update(self.tex)
        return opts


@dataclass
class BibliographyConfig:
    """The `bibliography:` block — `.bib` sources shared by every output."""

    sources: list[str] = field(default_factory=list)
    style: str = "numeric"        # numeric | author-year
    sort: str = "appearance"      # appearance | author | year
    title: str = "References"
    heading: str = "h2"
    link: bool = True

    @classmethod
    def from_raw(cls, raw: Any) -> "BibliographyConfig":
        if raw is None:
            return cls()
        # Shorthand: `bibliography: refs.bib` or a bare list of files.
        if isinstance(raw, str):
            raw = {"sources": [raw]}
        elif isinstance(raw, list):
            raw = {"sources": raw}
        if not isinstance(raw, dict):
            raise ManifestError("`bibliography:` must be a path, a list, or a mapping")

        sources = raw.get("sources") or raw.get("source") or []
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, list):
            raise ManifestError("bibliography.sources must be a path or list of paths")

        style = str(raw.get("style", "numeric"))
        if style not in ("numeric", "author-year"):
            raise ManifestError(
                f"bibliography.style must be numeric or author-year — got {style!r}"
            )

        sort = str(raw.get("sort", "appearance" if style == "numeric" else "author"))
        if sort not in ("appearance", "author", "year"):
            raise ManifestError(
                f"bibliography.sort must be appearance, author or year — got {sort!r}"
            )

        return cls(
            sources=[str(x) for x in sources],
            style=style,
            sort=sort,
            title=str(raw.get("title", "References")),
            heading=str(raw.get("heading", "h2")),
            link=bool(raw.get("link", True)),
        )


@dataclass
class Output:
    """One entry under `outputs:` — a single printout of the subject.

    Every output shares the same `variables`, `scenes` and `figures`; they
    differ only in renderer and entry document. `extra` carries whatever the
    engine-specific module wants (Slidev theme, VitePress nav, …) without
    this dataclass having to know about it.
    """

    key: str
    engine: str
    entry: str
    out: str
    title: str | None = None
    description: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    # Keys consumed here; everything else falls through to `extra`.
    _RESERVED = ("engine", "entry", "out", "title", "description")

    @property
    def entry_path(self) -> Path:
        return Path(self.entry)

    @classmethod
    def from_raw(cls, key: str, raw: Any) -> "Output":
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ManifestError(
                f"output {key!r}: expected a mapping, got {type(raw).__name__}"
            )

        engine = raw.get("engine") or DEFAULT_ENGINE_BY_KEY.get(key)
        if engine is None:
            raise ManifestError(
                f"output {key!r} missing required 'engine' field "
                f"(one of {', '.join(KNOWN_ENGINES)}). It is only inferred for "
                f"the well-known keys: {', '.join(sorted(DEFAULT_ENGINE_BY_KEY))}."
            )
        if engine not in KNOWN_ENGINES:
            raise ManifestError(
                f"output {key!r}: unknown engine {engine!r} "
                f"(expected one of {', '.join(KNOWN_ENGINES)})"
            )

        return cls(
            key=key,
            engine=engine,
            entry=raw.get("entry") or DEFAULT_ENTRY_BY_ENGINE[engine],
            out=raw.get("out") or f"site/{key}",
            title=raw.get("title"),
            description=raw.get("description"),
            extra={k: v for k, v in raw.items() if k not in cls._RESERVED},
        )


@dataclass
class Manifest:
    root: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    scenes: dict[str, Scene] = field(default_factory=dict)
    figures: dict[str, Figure] = field(default_factory=dict)
    outputs: dict[str, Output] = field(default_factory=dict)
    math: MathConfig = field(default_factory=lambda: MathConfig())
    bibliography: BibliographyConfig = field(
        default_factory=lambda: BibliographyConfig()
    )

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.root.name)

    def outputs_for_engine(self, engine: str) -> dict[str, Output]:
        return {k: o for k, o in self.outputs.items() if o.engine == engine}

    def resolve_targets(self, targets: list[str] | None) -> dict[str, Output]:
        """Select outputs by key, or all of them when `targets` is empty."""
        if not targets:
            return dict(self.outputs)
        missing = [t for t in targets if t not in self.outputs]
        if missing:
            raise ManifestError(
                f"unknown output(s): {', '.join(missing)}. "
                f"manifest.yaml declares: {', '.join(self.outputs) or '(none)'}"
            )
        return {t: self.outputs[t] for t in targets}


class ManifestError(Exception):
    pass


def _default_outputs(root: Path) -> dict[str, Output]:
    """Outputs for a manifest written before `outputs:` existed.

    Such a deck is a lone Slidev target: `slides.md` → `site/`. Preserving the
    old output directory (not `site/slides/`) keeps existing deploy scripts
    and bookmarks working after an upgrade.
    """
    return {
        "slides": Output(
            key="slides", engine="slidev", entry="slides.md", out="site"
        )
    }


def load_manifest(root: Path) -> Manifest:
    """Read manifest.yaml from `root` and validate.

    `root` is the subject directory — i.e., the dir containing manifest.yaml,
    the entry documents, and package.json. Typically the user's CWD when they
    run `presentation-sanity build`.
    """
    path = root / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"manifest.yaml not found at {path}")

    raw = yaml.safe_load(path.read_text()) or {}

    variables = {
        key: Variable.from_raw(key, val)
        for key, val in (raw.get("variables") or {}).items()
    }

    scenes_raw = raw.get("scenes") or {}
    scenes = {
        key: Scene.from_raw(key, val, root) for key, val in scenes_raw.items()
    }
    for scene in scenes.values():
        if not scene.source.is_file():
            print(
                f"  warning: scene {scene.key!r} source {scene.source} not found",
                file=sys.stderr,
            )

    figures_raw = raw.get("figures") or {}
    figures = {
        key: Figure.from_raw(key, val, root) for key, val in figures_raw.items()
    }
    for figure in figures.values():
        if not figure.source.is_file():
            print(
                f"  warning: figure {figure.key!r} source {figure.source} not found",
                file=sys.stderr,
            )

    outputs_raw = raw.get("outputs")
    if outputs_raw is None:
        outputs = _default_outputs(root)
    else:
        if not isinstance(outputs_raw, dict):
            raise ManifestError("`outputs:` must be a mapping of name → config")
        outputs = {
            key: Output.from_raw(key, val) for key, val in outputs_raw.items()
        }

    for output in outputs.values():
        if not (root / output.entry).is_file():
            print(
                f"  warning: output {output.key!r} entry {output.entry} not found",
                file=sys.stderr,
            )

    # One VitePress site per subject: multiple markdown pages belong to the
    # *same* site (add them next to the entry), not to a second one. Two
    # vitepress outputs would fight over the single `.vitepress/` root.
    vp = [k for k, o in outputs.items() if o.engine == "vitepress"]
    if len(vp) > 1:
        raise ManifestError(
            f"only one `vitepress` output is supported per subject, found: "
            f"{', '.join(vp)}. Additional markdown files alongside the entry "
            "become extra pages of the same site."
        )

    return Manifest(
        root=root,
        metadata=raw.get("metadata") or {},
        variables=variables,
        scenes=scenes,
        figures=figures,
        outputs=outputs,
        math=MathConfig.from_raw(raw.get("math")),
        bibliography=BibliographyConfig.from_raw(raw.get("bibliography")),
    )
