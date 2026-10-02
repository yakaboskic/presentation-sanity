"""Read Slidev slide frontmatter without running Slidev.

Shared by the PPTX exporter (which needs every slide's frontmatter to find the
manim slides) and the project index (which only needs the deck's headmatter —
the first slide's frontmatter — for a title).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


def split_slides(markdown: str) -> list[str]:
    """Split deck markdown into per-slide raw blocks, matching Slidev's parser.

    Separators are lines beginning with `---`; a `---` immediately followed by a
    non-blank line opens a frontmatter block that runs to the next `---` (so the
    fences inside frontmatter aren't mistaken for separators). Fenced code blocks
    are skipped so a `---` inside ``` doesn't split a slide.
    """
    lines = markdown.replace("\r\n", "\n").split("\n")
    n = len(lines)
    slides: list[str] = []
    start = 0

    def emit(end: int) -> None:
        nonlocal start
        if start != end:
            slides.append("\n".join(lines[start:end]))
        start = end + 1

    i = 0
    while i < n:
        line = lines[i].rstrip()
        if line.startswith("---"):
            emit(i)
            nxt = lines[i + 1] if i + 1 < n else None
            # `---` (not `----`) followed by content → frontmatter block
            if (len(line) <= 3 or line[3] != "-") and (nxt is not None and nxt.strip()):
                start = i
                i += 1
                while i < n and lines[i].rstrip() != "---":
                    i += 1
        elif line.lstrip().startswith("```"):
            fence = re.match(r"^\s*`+", line).group(0)
            j = i + 1
            while j < n and not lines[j].startswith(fence.lstrip()):
                j += 1
            if j != n:
                i = j
        i += 1
    if start <= n - 1:
        emit(n)
    return slides


def frontmatter(raw: str) -> dict[str, Any]:
    """Parse a slide block's leading YAML frontmatter (`---\\n…\\n---`)."""
    if not raw.lstrip().startswith("---"):
        return {}
    m = re.match(r"^\s*---\n(.*?)\n---", raw, re.S)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def parse_slide_frontmatters(markdown: str) -> list[dict[str, Any]]:
    """Frontmatter dicts for every *rendered* slide, in order.

    Slides with `hide:`/`disabled:` truthy are dropped — Slidev excludes them, so
    this keeps our indices aligned with the PNG export's 1..N numbering.
    """
    out: list[dict[str, Any]] = []
    for raw in split_slides(markdown):
        fm = frontmatter(raw)
        if fm.get("hide") or fm.get("disabled"):
            continue
        out.append(fm)
    return out


def read_headmatter(path: Path) -> dict[str, Any]:
    """The deck-level config: the first slide's frontmatter, or {} if absent."""
    if not path.is_file():
        return {}
    slides = split_slides(path.read_text())
    return frontmatter(slides[0]) if slides else {}
