"""`presentation-sanity check`: does everything a document uses exist?

Reads each selected presentation's markdown and resolves every reference
against the project manifest, without running Slidev or VitePress:

- `<DataValue var="…">`               → `variables:`
- `layout: manim` + `scene:` (decks),
  `<ManimFigure scene="…">` (blogs)    → `scenes:`, rendered in public/manim/
- `<FigureImage figure="…">`          → `figures:`, exported to public/figures/
- `\\cite{…}` and friends               → the keys in `bibliography.sources`

An unknown reference is an error (the page would show `??key??` or `[?key]`).
A declared scene or figure that hasn't been rendered is a warning: the build
would ship an old file or none. Code spans, fenced code and HTML comments are
skipped, as the renderers skip them.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .bibliography import parse_bibtex
from .manifest import Manifest
from .markdown_meta import split_slides, frontmatter

_ATTR = r"<{tag}\b[^>]*?(?<![:\w-]){attr}\s*=\s*[\"']([^\"']+)[\"']"
DATAVALUE = re.compile(_ATTR.format(tag="DataValue", attr="var"))
MANIMFIGURE = re.compile(_ATTR.format(tag="ManimFigure", attr="scene"))
FIGUREIMAGE = re.compile(_ATTR.format(tag="FigureImage", attr="figure"))
# The commands the blog's markdown-it rule understands (assets/vitepress/config.mts).
CITE = re.compile(r"\\(?:cite|citep|citealp|citet|citealt|nocite)\s*(?:\[[^\]]*\])?\{([^}]*)\}")
_SKIP_DIRS = {"exports", "node_modules", ".slidev", "components", "layouts", "public"}


@dataclass
class Finding:
    path: Path
    line: int
    message: str


@dataclass
class Report:
    documents: int = 0
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)


def _blank(text: str) -> str:
    """Code and comments replaced by spaces, so offsets (and lines) still match."""
    def spaces(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    text = re.sub(r"<!--.*?-->", spaces, text, flags=re.S)
    text = re.sub(r"^(\s*)(`{3,}|~{3,}).*?^\1\2", spaces, text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]+`", spaces, text)


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _hint(key: str, known: list[str]) -> str:
    close = difflib.get_close_matches(key, known, n=1)
    return f" (did you mean `{close[0]}`?)" if close else ""


def _bib_keys(manifest: Manifest) -> set[str] | None:
    sources = manifest.bibliography.sources
    if not sources:
        return None
    keys: set[str] = set()
    for src in sources:
        path = manifest.root / src
        if path.is_file():
            keys |= set(parse_bibtex(path.read_text(), origin=src))
    return keys


def _slide_scenes(text: str) -> list[tuple[str, int]]:
    """(scene, line) for every `layout: manim` slide in a deck."""
    found, offset = [], 0
    for raw in split_slides(text):
        start = text.find(raw, offset)
        offset = max(start, offset)
        fm = frontmatter(raw)
        if fm.get("layout") == "manim" and fm.get("scene"):
            found.append((str(fm["scene"]), _line(text, offset)))
    return found


def check_documents(manifest: Manifest, docs: list[tuple[Path, bool]]) -> Report:
    """Check `docs` — (path, is_deck) pairs — against `manifest`."""
    report = Report(documents=len(docs))
    bib = _bib_keys(manifest)
    used_scenes: dict[str, tuple[Path, int]] = {}
    used_figures: dict[str, tuple[Path, int]] = {}

    def err(path: Path, line: int, msg: str) -> None:
        report.errors.append(Finding(path, line, msg))

    for path, is_deck in docs:
        raw = path.read_text()
        text = _blank(raw)
        for m in DATAVALUE.finditer(text):
            key = m.group(1)
            if key not in manifest.variables:
                err(path, _line(text, m.start()),
                    f"<DataValue var=\"{key}\">: no variable `{key}` in manifest.yaml"
                    + _hint(key, list(manifest.variables)))
        scenes = [(m.group(1), _line(text, m.start())) for m in MANIMFIGURE.finditer(text)]
        if is_deck:
            scenes += _slide_scenes(raw)
        for key, line in scenes:
            if key not in manifest.scenes:
                err(path, line, f"scene `{key}`: not declared under `scenes:`"
                    + _hint(key, list(manifest.scenes)))
            else:
                used_scenes.setdefault(key, (path, line))
        for m in FIGUREIMAGE.finditer(text):
            key, line = m.group(1), _line(text, m.start())
            if key not in manifest.figures:
                err(path, line, f"<FigureImage figure=\"{key}\">: not declared under `figures:`"
                    + _hint(key, list(manifest.figures)))
            else:
                used_figures.setdefault(key, (path, line))
        for m in CITE.finditer(text):
            line = _line(text, m.start())
            if is_deck:
                report.warnings.append(Finding(
                    path, line, "\\cite in a deck renders as plain text — citations work in blogs"))
                continue
            for key in (k.strip() for k in m.group(1).split(",")):
                if not key or key == "*":
                    continue
                if bib is None:
                    err(path, line, f"\\cite{{{key}}}: no `bibliography:` sources in manifest.yaml")
                elif key not in bib:
                    err(path, line, f"\\cite{{{key}}}: no such key in the bibliography"
                        + _hint(key, sorted(bib)))

    for key, (path, line) in used_scenes.items():
        scene = manifest.scenes[key]
        video = manifest.root / "public" / "manim" / f"{key}.{scene.format}"
        if not video.is_file():
            report.warnings.append(Finding(
                path, line, f"scene `{key}` isn't rendered yet — run `presentation-sanity build-manim`"))
    for key, (path, line) in used_figures.items():
        fig = manifest.figures[key]
        image = manifest.root / "public" / "figures" / f"{key}.{fig.format}"
        if not image.is_file():
            report.warnings.append(Finding(
                path, line, f"figure `{key}` isn't exported yet — run `presentation-sanity build-figures`"))
    return report


def presentation_documents(pres_dir: Path, deck_entries: set[Path]) -> list[tuple[Path, bool]]:
    """Every markdown page a presentation builds from, decks flagged."""
    docs = []
    for path in sorted(pres_dir.rglob("*.md")):
        rel = path.relative_to(pres_dir)
        if _SKIP_DIRS.intersection(rel.parts[:-1]) or rel.name == "README.md":
            continue
        docs.append((path, path.resolve() in deck_entries))
    return docs
