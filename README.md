# presentation-sanity

Build interactive HTML presentations from a single `manifest.yaml`. Slidev
under the hood; static deployable; manim scenes baked in. Sibling project
to [`document-sanity`](https://github.com/yakaboskic/document-sanity) — same
philosophy (one source of config, multiple build targets, version-friendly),
applied to slide decks instead of papers.

## What it does

| Command | What runs | When to use |
|---|---|---|
| `presentation-sanity build` | Validate manifest → render stale manim scenes → `slidev build` → `dist/` | Build the deck. |
| `presentation-sanity build --base ./` | Same, but forwards `--base` to `slidev build`/Vite | Deploy to a subdirectory (e.g. `https://host/preview/abc/`). |
| `presentation-sanity dev` | `slidev` with hot reload | Iterate on slide content. |
| `presentation-sanity build-manim` | Render only stale manim scenes | When you've edited a `.py` scene file. |
| `presentation-sanity preview` | `python http.server` on `dist/` | Smoke-test the static build locally (browsers won't load `file://`). |
| `presentation-sanity export pdf` | `slidev export` | PDF output. |
| `presentation-sanity export pptx` | `slidev export --format pptx` | PowerPoint — slides as full-bleed images (limited fidelity by design). |

`build` degrades gracefully when manim isn't installed: it logs a clear
message and continues to `slidev build`, using whatever pre-rendered
videos already live in `public/manim/`. So a deploy environment never
needs cairo/pango/native build tools as long as you committed the videos.

## How it fits together

```
manifest.yaml ─┐
slides.md      │
scenes/*.py    ├──► presentation-sanity build
components/    │     ├─► validate manifest
public/        │     ├─► render stale manim scenes (cached by content hash)
style.css      │     │     → public/manim/<key>.webm
layouts/*.vue  ┘     └─► npx slidev build
                           → dist/  (static, deployable to any HTTP host)
```

- **`manifest.yaml`** — the deck's single source of config. Variables (with
  provenance metadata), manim scenes, theme settings.
- **Slidev** does the actual rendering — Vue + markdown, static HTML output.
- **`<DataValue>`** component reads `manifest.yaml` directly via
  `@modyfi/vite-plugin-yaml` — no Python intermediate for variables.
- **Manim scenes** are pre-rendered to `.webm` and embedded via a custom
  `Manim` layout (full-screen, no chrome).

Variable provenance fields (`description`, `source`, `command`, `updated`)
are **informational** — they show up in `<DataValue>` tooltips but are not
executed at build time. Keeping the build hermetic on purpose.

## Use it for your deck (recommended)

Create a separate repo for each deck and declare `presentation-sanity` as a
dependency. Mirrors the [`document-sanity` paper-repo pattern](https://github.com/yakaboskic/document-sanity).
Use [`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template)
as your starting point — clone it (or use it as a GitHub template) and edit.

**`pyproject.toml`** (deck repo):

```toml
[project]
name = "my-talk"
version = "0.1.0"
requires-python = ">=3.10"
# Default install does NOT pull manim — pre-rendered videos in
# public/manim/ travel with the deck, so deploy environments don't
# need cairo/pango/native build tools.
# To render scenes locally, switch to `presentation-sanity[manim]`.
dependencies = [
    "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@main",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.metadata]
allow-direct-references = true

[tool.hatch.build.targets.wheel]
bypass-selection = true        # the deck repo has no importable Python
```

**`package.json`** (deck repo):

```json
{
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "slidev --open",
    "build": "slidev build"
  },
  "dependencies": {
    "@slidev/cli": "^0.50.0",
    "@slidev/theme-seriph": "latest",
    "vue": "^3.5.0"
  },
  "devDependencies": {
    "@modyfi/vite-plugin-yaml": "^1.1.1"
  }
}
```

Then:

```bash
uv sync                                   # installs presentation-sanity (no manim by default)
npm install                               # installs Slidev side
uv run presentation-sanity build          # full pipeline → dist/
uv run presentation-sanity preview        # http://localhost:8000
```

To render manim scenes locally, swap the dep to
`presentation-sanity[manim]` and `uv sync` again. The `[manim]` extra pulls
manim + cairo + pango bindings; once the videos are rendered into
`public/manim/`, you can drop `[manim]` for deploy.

## Subdirectory deploys

`vite.config.ts` ships with `base: './'`, so the built `dist/` works
unchanged when served from any URL prefix (`https://host/preview/abc/`,
`https://host/talks/2026/`, etc.). To override per-build, pass
`--base` through:

```bash
presentation-sanity build --base ./           # relative paths (default)
presentation-sanity build --base /talks/2026/ # known prefix
```

The `manim` layout uses `import.meta.env.BASE_URL` so video URLs follow
the same rule — no extra config needed.

## Install the tool directly

For local development on the tool itself:

```bash
git clone https://github.com/yakaboskic/presentation-sanity
cd presentation-sanity
uv sync
uv run presentation-sanity --help
```

To iterate on the tool against a real deck, clone
[`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template)
alongside this repo and point its `pyproject.toml` dependency at the local
path (`presentation-sanity[manim] @ file:///…/presentation-sanity`).

## Deck layout

A deck looks like this:

```
my-talk/
├── pyproject.toml          # declares presentation-sanity dep
├── package.json            # Slidev deps
├── vite.config.ts          # registers @modyfi/vite-plugin-yaml
├── manifest.yaml           # variables + scenes + metadata
├── slides.md               # the deck
├── style.css               # opinionated global styles (auto-loaded)
├── components/
│   └── DataValue.vue       # provenance-aware variable rendering
├── layouts/
│   └── manim.vue           # full-screen manim layout (lowercase = layout name)
├── scenes/
│   └── intro.py            # manim source files
├── public/                 # static assets — paths follow Vite's base
│   └── manim/              # rendered videos — committed alongside source
└── dist/                   # build output (gitignored)
```

## manifest.yaml

```yaml
metadata:
  title: "My Talk"
  authors:
    - { name: "Your Name", email: "you@example.com" }
  theme: seriph             # any Slidev theme id, package, or local path

variables:
  num_samples:
    value: 12453
    format: ","             # Python-style spec: , .2e .3f .1%
    description: "Total samples after QC"
    source: "data/results.csv"        # single-file input (informational)
    # — or — for multi-file inputs:
    # data:
    #   - "data/results.csv"
    #   - "data/cohort_metadata.tsv"
    command: "python scripts/fit.py"  # informational — not executed
    updated: "2026-04-29"

scenes:
  intro:
    source: "scenes/intro.py"
    class: "IntroScene"
    quality: "h"            # l | m | h | p | k
    format: "webm"
```

## Slide patterns

**Variable with provenance tooltip:**

```markdown
We analyzed <DataValue var="num_samples" /> samples.
```

**Full-screen manim slide:**

```markdown
---
layout: manim
scene: intro
---

(optional caption text — overlaid at bottom)
```

**Static hosting:** `dist/` is fully self-contained. The deck uses **hash
routing** so URLs work on any dumb static host (S3, R2, GitHub Pages, Netlify)
with no SPA fallback configuration.

## System dependencies

Only required when you want to **render manim scenes locally** (i.e.,
when you've installed the `[manim]` extra):

- macOS: `brew install ffmpeg cairo pango`
- Linux: `apt install ffmpeg libcairo2-dev libpango1.0-dev` (or distro equivalent)
- LaTeX is required for `MathTex`. Install [TeX Live](https://tug.org/texlive/) or BasicTeX.

If you're just building/deploying a deck whose videos are already
rendered (committed in `public/manim/`), you don't need any of these —
`presentation-sanity build` auto-skips manim with a log line and runs
`slidev build` against the existing videos. Pass `--skip-manim`
explicitly if you want the same behavior even when manim *is* installed.

## Library inspiration

- [document-sanity](https://github.com/yakaboskic/document-sanity) — sibling
  project; the manifest/variable/versioning philosophy is shared.
- [Slidev](https://sli.dev) — the actual rendering engine. presentation-sanity
  is a thin orchestration layer around it.
- [manim](https://www.manim.community/) — the math animation engine. Scenes
  are pre-rendered; presentation-sanity handles caching and pathing.
