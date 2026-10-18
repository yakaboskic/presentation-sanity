# export: PDF, PPTX, PNG

Exports land next to the deck, in `presentations/<id>/exports/`, so two
versions never overwrite each other.

| Want | Run | Needs |
|---|---|---|
| PDF handout | `uv run presentation-sanity export pdf <id>` | `npm i -D playwright-chromium` once |
| PPTX with **playable** manim video | `uv run --with python-pptx presentation-sanity export-pptx <id>` | ffmpeg, python-pptx, playwright-chromium |
| PPTX of flat images | `uv run presentation-sanity export pptx <id>` | playwright-chromium |
| one PNG per slide | `uv run presentation-sanity export png <id>` | playwright-chromium |

`export-pptx` is usually the one people want for PowerPoint. Ordinary slides
become images; manim slides embed the real video. Options: `--no-autoplay`
(click to play), `--no-clicks` (one slide per slide instead of one per
`v-click`), `--out path.pptx`.

Before exporting: run `check`, and make sure the scenes are rendered
(`build-manim`). Exports use what's in `public/manim/`.

Exports are build output. Don't commit them unless the user asks.
