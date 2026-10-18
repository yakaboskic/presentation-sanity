from __future__ import annotations

from pathlib import Path

from presentation_sanity.cli import main

from .conftest import PROJECT_MANIFEST

MANIFEST = PROJECT_MANIFEST + """\
scenes:
  intro:
    source: scenes/intro.py
    class: IntroScene
figures:
  pipeline:
    source: figures/pipeline.excalidraw
bibliography:
  sources: [refs.bib]
"""

DECK = """\
---
title: Deck
---

# Hello

We saw <DataValue var="n" /> things and <DataValue var="m" /> others.

---
layout: manim
scene: intro
---

---
layout: manim
scene: outro
---

Cited in a deck \\cite{known}.
"""

BLOG = """\
---
title: Post
---

Text with <DataValue
var="n" /> and a figure <FigureImage figure="pipelne" />.

A claim \\cite{known} and another \\citep[p. 3]{known,missing}.

`<DataValue var="in_code" />` and

```md
<DataValue var="in_fence" /> \\cite{in_fence}
```

<!-- <DataValue var="in_comment" /> -->

<ManimFigure scene="intro" caption="x" />

\\bibliography
"""


def setup(write) -> Path:
    return write({
        "manifest.yaml": MANIFEST,
        "refs.bib": "@article{known, title={T}, author={A, B}, year={2020}}\n",
        "presentations/talk/slides.md": DECK,
        "presentations/talk/blog.md": BLOG,
        "public/manim/intro.webm": "v",
    })


def test_check_reports_unknown_references(write, monkeypatch, capsys) -> None:
    root = setup(write)
    monkeypatch.chdir(root)
    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert "slides.md:7" in out and 'var="m"' in out  # unknown variable, with its line
    assert "scene `outro`" in out
    assert "pipelne" in out and "did you mean `pipeline`" in out
    assert "\\cite{missing}" in out and "\\cite{known}" not in out.replace("in a deck", "")
    assert "cite in a deck" in out  # a warning, not an error
    for skipped in ("in_code", "in_fence", "in_comment"):
        assert skipped not in out
    assert "4 errors" in out


def test_check_passes_and_warns_about_unrendered(write, monkeypatch, capsys) -> None:
    root = write({
        "manifest.yaml": MANIFEST,
        "refs.bib": "@book{known, title={T}, year={2020}}\n",
        "presentations/ok/blog.md": (
            "# ok\n\nSee <DataValue var=\"n\" />, <FigureImage figure=\"pipeline\" /> "
            "and <ManimFigure scene=\"intro\" /> \\cite{known}.\n"
        ),
    })
    monkeypatch.chdir(root)
    assert main(["check", "ok"]) == 0
    out = capsys.readouterr().out
    assert "scene `intro` isn't rendered" in out
    assert "figure `pipeline` isn't exported" in out
    assert "ok: every reference resolves" in out
