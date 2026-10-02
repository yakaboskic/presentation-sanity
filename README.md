# presentation-sanity

Build a subject once, print it many ways. A single `manifest.yaml` declares
shared variables (with provenance), manim scenes and Excalidraw figures, plus
the **outputs** that render them: a Slidev deck, a VitePress blog post, or both.
Static and deployable; manim baked in. Sibling project to
[`document-sanity`](https://github.com/yakaboskic/document-sanity) — same
philosophy (one source of config, multiple build targets, version-friendly).

Slides and a blog post are two printouts of the same material, not two
projects. Slidev and VitePress sit on the same substrate (Vite + Vue 3 +
markdown-it + Shiki), so one `components/` directory, one manifest and one
`public/` folder back both: `<DataValue var="n" />` in `blog.md` reads the same
YAML as the same tag in `slides.md`, and a manim scene renders once and embeds
twice.

One level up, a repo can be a **project**: many presentations — and versions of
them — sharing that same manifest, `public/` and components, each in its own
folder under `presentations/` (see [Projects](#projects-many-presentations-one-repo)).
A new version of a talk is a folder, not a branch or a copied repo.

## What it does

Verbs take an optional **target** — a key under `outputs:` in the manifest, or
in a project `PRESENTATION[:OUTPUT]` (e.g. `kickoff/v2:blog`).

| Command | What runs | When to use |
|---|---|---|
| `presentation-sanity list` | List the presentations (in a project) or outputs (`outputs` is an alias) | Check what exists and what's built. |
| `presentation-sanity new kickoff/v2 --from kickoff/v1` | Copy a presentation into a new folder and record the lineage | Start a new version (project only). |
| `presentation-sanity build` | Validate manifest → export stale figures → render stale manim scenes → render **every** output | Build everything. |
| `presentation-sanity build blog` | Same, but only the named output(s) | Build one printout. |
| `presentation-sanity dev blog` | `vitepress dev` with hot reload | Write the post. |
| `presentation-sanity dev slides` | `slidev` with hot reload | Iterate on slide content. |
| `presentation-sanity scaffold` | Regenerate `.vitepress/` from the manifest, without building | Editor tooling / inspecting the generated config. |
| `presentation-sanity build-manim` | Render only stale manim scenes | You edited a `.py` scene file. |
| `presentation-sanity build-figures` | Export only stale Excalidraw figures | You edited an `.excalidraw` source. |
| `presentation-sanity preview blog` | `python http.server` on that output's dir | Smoke-test the static build (browsers won't load `file://`). |
| `presentation-sanity export pdf` | `slidev export` | PDF output (slides only). |
| `presentation-sanity export-pptx` | PPTX with **embedded, playable** manim video | PowerPoint that isn't just images. |

`build` degrades gracefully when manim isn't installed: it logs a clear
message and continues to the renderers, using whatever pre-rendered videos
already live in `public/manim/`. So a deploy environment never needs
cairo/pango/native build tools as long as you committed the videos.

**Figures (Excalidraw → image).** Declare `.excalidraw` sources under
`figures:` in the manifest; `build-figures` exports each to
`public/figures/<key>.<format>` (content-hash cached, same as manim).
Export uses [`excalidraw-brute-export-cli`](https://github.com/realazthat/excalidraw-brute-export-cli)
(Playwright + Firefox) via `npx`; first run needs `npx playwright install firefox`.
The exporter is **optional** — `build` auto-skips figure export when it isn't
installed and uses the committed images in `public/figures/`, so deploys never
need a headless browser. Reference a figure from either output with
`<FigureImage figure="<key>" />`.

## Projects: many presentations, one repo

A repo whose root holds `manifest.yaml` **and a `presentations/` directory** is a
project. Every folder under `presentations/` that contains an output's entry
document (`slides.md`, `blog.md`) is a presentation, and its path is its id.
Folders without one just group presentations — that is all a version is:

```
pigean/
├── manifest.yaml                 # SHARED: variables, scenes, figures, bibliography, math,
│                                 #   plus defaults for every presentation's outputs
├── public/  scenes/  refs.bib    # shared assets and sources
├── shared/                       # shared Vue layer, a local Slidev addon (below)
└── presentations/
    ├── decode-pigean/            # grouping folder
    │   ├── cfde-2026/slides.md   #   id decode-pigean/cfde-2026
    │   └── eurac-2026/           #   id decode-pigean/eurac-2026
    │       ├── slides.md
    │       ├── manifest.yaml     #   optional: metadata + output overrides
    │       └── components/X.vue  #   optional: overrides shared/components/X.vue
    └── ashg-2026/slides.md
```

- **Outputs** come from the files a presentation has: `slides` for `slides.md`,
  `blog` for `blog.md`. The project's `outputs:` are defaults for all of them
  (`out:` is not allowed there); each builds to `site/<id>/<output>/`, and
  `site/index.html` — refreshed on every build — lists them grouped by folder.
- **A presentation's `manifest.yaml`** may only hold `metadata` (title, date,
  venue, authors, `from`) and `outputs` overrides (deep-merged; `blog: false`
  opts out). Variables, scenes, figures, bibliography and math are project-wide,
  so they never fork: when a number changes, add a new key and point the new
  version at it.
- **Targets**: `build` with no target builds everything (or, inside a
  presentation's folder, that presentation). A grouping folder selects every
  presentation in it (`build decode-pigean`), and paths work too.
- **`new <id> [--from <id>] [--title T]`** creates a presentation, or copies one
  (skipping `exports/` and Slidev's scratch state), retitles its headmatter and
  records `from:` in its manifest.
- **`--base`** is the deploy prefix for all of `site/`: decks build with a
  relative `./`, blogs with `<prefix><id>/<output>/`.
- A repo **without** `presentations/` is a single subject and builds exactly as
  before.

### The shared layer is a Slidev addon

Slidev takes components, layouts, global layers, styles and `vite.config.ts`
from the folder of the deck it builds, so a deck at `presentations/<id>/` sees
nothing at the project root. The shared files therefore live in `shared/`,
packaged as a local addon and enabled once for every deck:

```jsonc
// package.json
"devDependencies": { "psanity-shared": "file:./shared" },
"slidev": { "addons": ["psanity-shared"] }
```

`shared/package.json` (just a `name`) is required. `shared/vite.config.ts` sets an
**absolute** `publicDir` (the project's `public/` — a relative one would resolve
against the deck's folder), registers the YAML plugin, defines `@project` /
`@shared` aliases for depth-independent imports, and sets
`slidev.components.allowOverrides` so a presentation's `components/X.vue` wins
over the shared one. A package name is used rather than a relative path because
Slidev resolves relative addon paths against the deck's *parent* folder.

For blogs, the generated VitePress config does the equivalent: `srcDir` stays the
project root (VitePress copies `<srcDir>/public` verbatim), the site is narrowed
to one presentation with `srcExclude` + `rewrites`, the same two aliases are
defined, and the theme registers `shared/components` then the presentation's
own `components`. Each blog's config is written to
`.cache/vitepress/<id>/.vitepress/`, so two blogs can run `dev` at once.

`build`/`dev` stop early with "run `npm install`" when the addon isn't linked
into `node_modules`, and warn when a project still has `components/` or
`layouts/` at its root, where decks can't see them.

## Outputs

```yaml
outputs:
  blog:
    engine: vitepress      # inferred for keys blog/post/article
    entry: blog.md         # rewritten to `/` in the built site
    out: site/blog
  slides:
    engine: slidev         # inferred for keys slides/deck
    entry: slides.md
    out: site/slides
    theme: seriph
```

Delete an entry to stop building that format; add one to start. Unknown keys in
an output are forwarded to the engine (VitePress: `nav`, `sidebar`,
`socialLinks`, `head`, `markdown`, `themeConfig`, `exclude`, `base`).

A manifest with no `outputs:` block is treated as a lone Slidev deck
(`slides.md` → `site/`), so decks written before this existed keep building to
the same place.

**One VitePress output per subject.** Extra markdown files next to the entry
become extra *pages of the same site* — that's the model, rather than two
sites. Every other output's `entry` lands in `srcExclude` automatically, so
`slides.md` never becomes a blog page.

### The generated `.vitepress/`

`presentation-sanity` writes `.vitepress/config.mts` and
`.vitepress/theme/index.ts` from the manifest before every `dev`/`build` (in a
project, under `.cache/vitepress/<id>/`). The directory is generated,
gitignored, and never hand-edited. The theme:

- glob-registers every `components/*.vue` globally under its filename — the
  same convention Slidev uses, so components work in markdown with no imports;
- mounts `ProvenancePanel` in the `layout-bottom` slot — the VitePress
  equivalent of Slidev's `global-bottom.vue` singleton;
- imports `blog.css` when present.

The generated config sets **`vite.configFile: false`**, which is load-bearing:
a subject root also carries a `vite.config.ts` for Slidev, and merging it in
would apply `@modyfi/vite-plugin-yaml` a *second* time — the double pass
re-parses the emitted JS as YAML and hands every component a string instead of
the manifest — as well as Slidev's `base: './'`, which VitePress's router
cannot use.

Optional Node packages are detected at scaffold time, so a subject without them
still builds (with a note): `markdown-it-mathjax3` enables `$math$`,
`@modyfi/vite-plugin-yaml` is what lets `<DataValue>` read the manifest.

`presentation-sanity scaffold` regenerates the directory without building — use
it to read exactly what was produced.

### Theming levers

Because there is no page file to edit, theming happens through four levers:

| Lever | Where | Reaches |
|---|---|---|
| `outputs.<key>:` keys | `manifest.yaml` | `nav`, `sidebar`, `socialLinks`, `outline`, `footer`, `head`, `markdown`, `base`, `title`, `description`, `exclude`, `lastUpdated` |
| `themeConfig:` | `manifest.yaml` | any other default-theme option — `logo`, `aside`, `search`, `editLink`, `docFooter`, … |
| `vitepress:` | `manifest.yaml` | any other top-level VitePress option — `appearance`, `lang`, `titleTemplate`, `sitemap`, … . `outDir`, `rewrites` and `cacheDir` stay owned by the build orchestrator |
| `blog.css` | subject root | imported **last** into the generated theme, so it overrides VitePress's CSS variables *and* the built-in citation styles |

Per-page frontmatter (`layout: doc`/`page`/`home`, `aside`, `sidebar`,
`outline`, `pageClass`) and anything dropped into `components/` work as usual.
To go further, copy the generated directory elsewhere and run VitePress
yourself.

## Math

The blog renders LaTeX to **static SVG at build time** (MathJax via
`markdown-it-mathjax3`, with MathJax's full package set). No client-side math
runtime, no flash of unstyled TeX, and it prints correctly.

`$…$` and `$$…$$` work as expected, and display environments can be written
bare — the way you would in a `.tex` file:

```markdown
\begin{align}
h^2 &= \frac{\sigma^2_A}{\sigma^2_P} \\
    &= \frac{\sigma^2_A}{\sigma^2_A + \sigma^2_E}
\end{align}
```

`markdown-it-mathjax3` only recognises `$` delimiters, so a bare environment
would otherwise fall through to the paragraph rule and render as literal text
with its `\\` row breaks eaten. `presentation-sanity` adds a markdown-it block
rule that consumes `\begin{env}…\end{env}` and hands it to the same renderer, so
it behaves exactly as if it had been fenced in `$$`.

Environments not on the list (`\begin{itemize}`, say) stay literal, and an
unterminated `\begin{…}` falls back to a paragraph rather than swallowing the
rest of the document. Nested constructs like `cases` and `pmatrix` still need
`$$` fencing — they are not block-level environments.

```yaml
math:
  macros:
    Var: "\\operatorname{Var}"
    RR: "\\mathbb{R}"
    given: "\\mid"
    norm: ["\\left\\lVert #1 \\right\\rVert", 1]   # [expansion, arg count]
  tags: none            # none | ams | all
  environments: true    # or false, or an explicit list of env names
  packages: [...]       # optional; overrides MathJax's AllPackages
  tex: {}               # raw markdown-it-mathjax3 `tex` passthrough
  svg: {}               # raw `svg` output passthrough
```

**Define macros here, not with an in-document `\newcommand`.** The renderer
keeps one TeX instance for the whole build, so an in-document definition leaks
into every later block *and every later page*, and whether it resolves depends
on source order. Declared in the manifest they are deterministic.

`tags: ams` numbers display equations and enables `\label`/`\eqref`. The same
shared-instance behaviour applies to the counter: numbering runs across the
whole build and its starting point depends on page processing order. That is
fine for a single-page post; with several pages prefer an explicit `\tag{…}`
(stable and order-independent) or reset a page with
`\setcounter{equation}{0}`.

> The deck renders math with **KaTeX** (Slidev's built-in), not MathJax, so
> `math.macros` currently reaches the blog only. Configure the deck's macros in
> Slidev's `setup/katex.ts` if you need them in both.

## Citations

LaTeX-shaped citing without a LaTeX toolchain. Name `.bib` sources in the
manifest, cite with `\cite{key}`, and mark the reference list with
`\bibliography`:

```yaml
bibliography:
  sources: ["refs.bib"]     # a path, a list of paths, or a full mapping
  style: numeric            # numeric → [1]  |  author-year → (Smith et al., 2020)
  sort: appearance          # appearance | author | year
  title: "References"
  heading: h2
  link: true                # render the DOI / URL as a link
```

```markdown
Heritability is routinely misread \cite{visscher2008}. The framing goes back
further \cite{falconer1996,lewontin1974}. \citet{lewontin1974} argued the
analysis of variance cannot recover the analysis of causes, at
\cite[pp. 401--403]{lewontin1974}.

\bibliography
```

| Command | numeric | author-year |
|---|---|---|
| `\cite{k}`, `\citep{k}` | `[1]` | `(Smith et al., 2020)` |
| `\citet{k}` | `Smith et al. [1]` | `Smith et al. (2020)` |
| `\cite{a,b}` | `[1, 2]` | `(Doe, 1996; Smith, 2020)` |
| `\cite[p. 12]{k}` | `[1, p. 12]` | `(Smith et al., 2020, p. 12)` |
| `\nocite{k}` | — (listed, not cited inline) | — |
| `\bibliography`, `\printbibliography` | the reference list | |

Parsing and formatting happen at build time on the Python side; the generated
VitePress config carries the finished HTML for each entry, so the published
page ships plain anchors and **no citation runtime** — the same bargain the
math rendering makes. Every citation links to its entry and carries the full
reference as a hover tooltip.

Numbering is resolved in a second pass over the parsed document, so
`style: numeric` with `sort: author` renumbers the in-text markers *and* the
list together rather than only reordering the list.

The BibTeX parser is dependency-free and handles the things real `.bib` files
contain: `@string` macros and `#` concatenation, `"…"` and `{…}` values,
case-insensitive fields, brace-protected capitalisation (`{DNA}`), LaTeX
accents (`M{\"u}ller` → Müller), `--`/`---` dashes, `and others` → et al., and
inline math in titles (`$\alpha$` → α). `@comment` and `@preamble` are skipped.

A `\cite{}` of an unknown key renders a visible `[?key]` marker and logs a
build warning rather than failing or silently vanishing — the same treatment
`<DataValue>` gives a missing variable. Citation commands inside code spans and
math are left alone.

> Two caveats. The generated config is written once when `dev` starts, so
> editing a `.bib` file needs a dev-server restart (editing the document
> itself hot-reloads normally). And like `math.macros`, this currently reaches
> the **blog only** — the deck's markdown pipeline is Slidev's.

## How it fits together

```
                     SHARED, RENDERED ONCE              PER-OUTPUT
manifest.yaml ─┐
scenes/*.py    │   ┌─ validate manifest
components/    ├──►├─ export stale figures  → public/figures/<key>.svg ─┐
composables/   │   └─ render stale scenes   → public/manim/<key>.webm  ─┤
public/        ┘      (both content-hash cached)                        │
                                                                        ▼
blog.md   ──────────────────────────────────►  npx vitepress build → site/blog/
slides.md ──────────────────────────────────►  npx slidev build    → site/slides/
                                                                   → site/index.html
```

> Output dirs default to **`site/<key>/`** (not `dist`/`build`/`out`, which many
> static hosts and deploy tools auto-ignore). Set `out:` per output, or override
> a single target with `build <target> --out <dir>`. A full build of more than
> one output also writes a small `site/index.html` linking each printout.

- **`manifest.yaml`** — the subject's single source of config: variables (with
  provenance metadata), manim scenes, figures, and the outputs that print them.
- **Slidev** renders the deck, **VitePress** renders the blog — both Vue +
  markdown, both static HTML output.
- **`<DataValue>`** reads `manifest.yaml` directly via
  `@modyfi/vite-plugin-yaml` — no Python intermediate for variables, in either
  engine.
- **Manim scenes** are pre-rendered to `.webm` (plus a last-frame poster) and
  embedded full-screen by the Slidev `manim` layout, or inline by
  `<ManimFigure scene="…" />` in the blog.

Variable provenance fields (`description`, `source`, `command`, `updated`)
are **informational** — they show up in `<DataValue>` tooltips but are not
executed at build time. Keeping the build hermetic on purpose.

## Use it for your subject (recommended)

Create a separate repo per subject and declare `presentation-sanity` as a
dependency. Mirrors the [`document-sanity` paper-repo pattern](https://github.com/yakaboskic/document-sanity).
Use [`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template)
as your starting point — clone it (or use it as a GitHub template) and edit.

**`pyproject.toml`** (subject repo):

```toml
[project]
name = "my-talk"
version = "0.1.0"
requires-python = ">=3.10"
# The [manim] extra lets `build` render scenes (the machine needs ffmpeg,
# cairo, pango and LaTeX); drop it for a deploy environment that only
# serves committed videos from public/manim/.
# Pin a release tag (https://github.com/yakaboskic/presentation-sanity/releases),
# not @main; to upgrade, change the tag and run `uv lock`.
dependencies = [
    "presentation-sanity[manim] @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.3.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.metadata]
allow-direct-references = true

[tool.hatch.build.targets.wheel]
bypass-selection = true        # the deck repo has no importable Python
```

**`package.json`** (subject repo) — install only the engines you actually use;
a blog-only repo can drop the Slidev dependencies entirely:

```json
{
  "private": true,
  "type": "module",
  "dependencies": {
    "@slidev/cli": "^0.50.0",
    "@slidev/theme-seriph": "latest",
    "vue": "^3.5.0"
  },
  "devDependencies": {
    "@modyfi/vite-plugin-yaml": "^1.1.1",
    "markdown-it-mathjax3": "^4.3.2",
    "vitepress": "^1.6.3"
  }
}
```

Then:

```bash
uv sync                                   # installs presentation-sanity (no manim by default)
npm install                               # installs the JS engines
uv run presentation-sanity outputs        # what this subject declares
uv run presentation-sanity build          # full pipeline → site/
uv run presentation-sanity preview blog   # http://localhost:8000
```

To render manim scenes locally, swap the dep to
`presentation-sanity[manim]` and `uv sync` again. The `[manim]` extra pulls
manim + cairo + pango bindings; once the videos are rendered into
`public/manim/`, you can drop `[manim]` for deploy.

## Subdirectory deploys

The two engines differ here, and it matters:

- **Slidev** accepts a *relative* base. `vite.config.ts` ships with
  `base: './'`, so the built deck works unchanged at any URL prefix
  (`https://host/preview/abc/`, `https://host/talks/2026/`).
- **VitePress** does SSR and route matching, so it needs an *absolute* prefix.
  `presentation-sanity` coerces a relative value to `/` rather than emitting a
  site that 404s its own routes.

```bash
presentation-sanity build slides --base ./              # relative (Slidev default)
presentation-sanity build blog   --base /talks/2026/    # absolute (VitePress)
```

Or set `base:` per output in the manifest. `<ManimFigure>`, `<FigureImage>` and
the Slidev `manim` layout all read `import.meta.env.BASE_URL`, so asset URLs
follow whichever base is in force — no extra config needed.

In a **project**, `--base` names the prefix the whole `site/` is served from,
and each output's base is derived from it: decks get `./`, blogs get
`<prefix><id>/<output>/`.

```bash
presentation-sanity build --base /pigean/    # blog of kickoff/v2 → /pigean/kickoff/v2/blog/
```

## Install the tool directly

For local development on the tool itself:

```bash
git clone https://github.com/yakaboskic/presentation-sanity
cd presentation-sanity
uv sync
uv run presentation-sanity --help
```

To iterate on the tool against a real subject, clone
[`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template)
alongside this repo and point its dependency at the local checkout:

```toml
[tool.uv.sources]
presentation-sanity = { path = "../presentation-sanity", editable = true }
```

### Releasing

Subject repos and the template pin release tags, so a change reaches them
only through a release:

1. Bump `version` in `pyproject.toml` and `__version__` in
   `src/presentation_sanity/__init__.py`, update the tag in the dependency
   snippet above, run `uv run pytest`, and push to `main`.
2. Tag and publish:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z — summary" && git push origin vX.Y.Z
   gh release create vX.Y.Z --verify-tag --title "vX.Y.Z — summary" --notes-file notes.md
   ```
3. Move the template to it: in `presentation-sanity-template`, change the tag in
   the `pyproject.toml` dependency line and in the README's "Upgrading
   presentation-sanity" example; run `uv lock`, build the example presentation
   (it renders its manim scene), and push.

## Subject layout

```
my-subject/
├── pyproject.toml          # declares presentation-sanity dep
├── package.json            # Slidev and/or VitePress deps
├── manifest.yaml           # outputs + variables + scenes + figures
│
├── blog.md                 # ← VitePress entry (served at /)
├── slides.md               # ← Slidev entry
│
├── components/             # SHARED, auto-registered globally in both engines
│   ├── DataValue.vue       #   provenance-aware variable rendering
│   ├── ProvenancePanel.vue #   the slide-in provenance graph (singleton)
│   ├── ManimFigure.vue     #   a manim scene as an inline blog figure
│   └── FigureImage.vue     #   an exported Excalidraw figure
├── composables/            # SHARED
├── layouts/manim.vue       # Slidev-only: full-screen manim slide
├── scenes/intro.py         # SHARED manim sources
├── public/                 # SHARED static assets — paths follow Vite's base
│   ├── manim/              #   rendered videos + posters, committed with source
│   └── figures/            #   exported Excalidraw images
│
├── style.css               # Slidev-only globals (auto-loaded by Slidev)
├── blog.css                # VitePress-only styles (imported into the theme)
├── vite.config.ts          # SLIDEV ONLY — VitePress builds with configFile:false
│
├── .vitepress/             # GENERATED from manifest.yaml each build (gitignored)
└── site/                   # build output (gitignored; not "dist" — see above)
    ├── index.html          #   landing page linking each printout
    ├── blog/
    └── slides/
```

## manifest.yaml

```yaml
metadata:
  title: "My Subject"
  description: "One line, used as the blog's meta description"
  authors:
    - { name: "Your Name", email: "you@example.com" }

outputs:                    # one entry per printout; omit for a lone deck
  blog:
    engine: vitepress
    entry: blog.md
    out: site/blog
  slides:
    engine: slidev
    entry: slides.md
    out: site/slides
    theme: seriph           # any Slidev theme id, package, or local path

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

figures:
  pipeline:
    source: "excalidraw/pipeline.excalidraw"
    format: "svg"           # svg | png  (default svg)
    scale: 1                # export scale (default 1)
    background: false       # transparent by default
    dark: false             # dark-mode export
    embed_scene: false      # embed editable scene data in the export
```

## Content patterns

**Variable with provenance panel** — identical in both outputs:

```markdown
We analyzed <DataValue var="num_samples" /> samples.
```

Click the underlined value and a panel slides in from the right showing
`inputs → command → variable` as a vertical graph.

**A manim scene, two ways.** Full-screen slide (Slidev):

```markdown
---
layout: manim
scene: intro
---

(optional caption text — overlaid at bottom)
```

Inline figure (VitePress) — plays when scrolled into view, pauses when scrolled
out, so a long post with several scenes doesn't run them all at once:

```markdown
<ManimFigure scene="intro" caption="What this shows." />
```

Both read `public/manim/intro.webm` plus the last-frame poster that
`build-manim` extracts with ffmpeg, so the finished diagram shows wherever the
video can't play (initial paint, PDF/PPTX export, print).

> **Writing tip.** Keep a component tag off the *start* of a line in markdown —
> markdown-it treats a line beginning with `<Tag` as an HTML *block* and closes
> the surrounding paragraph around it. Wrap so the tag lands mid-line.

**Static hosting:** `site/` is fully self-contained. The deck uses **hash
routing** and the blog builds real `.html` routes (`cleanUrls: false`), so both
work on any dumb static host (S3, R2, GitHub Pages, Netlify) with no SPA
fallback or rewrite configuration.

## System dependencies

Only required when you want to **render manim scenes locally** (i.e.,
when you've installed the `[manim]` extra):

- macOS: `brew install ffmpeg cairo pango`
- Linux: `apt install ffmpeg libcairo2-dev libpango1.0-dev` (or distro equivalent)
- LaTeX is required for `MathTex`. Install [TeX Live](https://tug.org/texlive/) or BasicTeX.

If you're just building/deploying a subject whose videos are already
rendered (committed in `public/manim/`), you don't need any of these —
`presentation-sanity build` auto-skips manim with a log line and runs the
renderers against the existing videos. Pass `--skip-manim` explicitly if you
want the same behavior even when manim *is* installed.

## Library inspiration

- [document-sanity](https://github.com/yakaboskic/document-sanity) — sibling
  project; the manifest/variable/versioning philosophy is shared.
- [Slidev](https://sli.dev) — renders the deck. presentation-sanity is a thin
  orchestration layer around it.
- [VitePress](https://vitepress.dev) — renders the blog. Chosen because it
  shares Slidev's substrate (Vite + Vue 3 + markdown-it + Shiki), which is what
  lets one `components/` directory and one manifest back both outputs.
- [manim](https://www.manim.community/) — the math animation engine. Scenes
  are pre-rendered; presentation-sanity handles caching and pathing.
