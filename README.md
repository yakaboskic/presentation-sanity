<a href="https://sanitism.dev"><img src="https://sanitism.dev/media/one-number-poster.jpg" alt="One number in manifest.yaml and a sentence in docs/results.md build into LaTeX, PDF, Word, HTML, slides and a blog post, each showing 12,453." width="100%"></a>

# presentation-sanity

**Every talk you give about a project, from one manifest: Slidev decks, VitePress blog posts and PowerPoint with playable manim scenes, sharing the same numbers, figures and animations.**

Part of [Sanitism](https://sanitism.dev): built for autists to communicate their work, sanely. The sibling for papers and proposals is [document-sanity](https://github.com/yakaboskic/document-sanity).

**See it:** [the example deck](https://presentation.sanitism.dev/example/slides/) and [its blog post](https://presentation.sanitism.dev/example/blog/), built from [presentation-sanity-template](https://github.com/yakaboskic/presentation-sanity-template).

## Start a project

<img src="https://sanitism.dev/figures/two-ways-in.svg" alt="A template repo leads two ways. Use this template on GitHub gives the project a repo with history. Running uvx init gives a plain folder with no git. Both arrive at the same project." width="100%">

**Just give me a folder.** No clone, no git. It needs [uv](https://docs.astral.sh/uv/) and Node 20+:

```bash
uvx --from "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.4.2" \
  presentation-sanity init my-talks --title "My talks" --first kickoff
```

```bash
cd my-talks
uv sync          # presentation-sanity, plus manim through the default `manim` group
npm install      # Slidev + VitePress; links shared/
uv run presentation-sanity dev kickoff:slides   # or kickoff:blog for the post
```

Commit the `uv.lock` that the first `uv sync` writes: the Pages workflow installs with `uv sync --locked`.

**Keep it in git.** On [presentation-sanity-template](https://github.com/yakaboskic/presentation-sanity-template), click **Use this template**, clone your copy and run `python init.py`. It is a thin shim over the same `init`, so both ways give you the same project, pinned to this release, with the [agent skill](#agent-skill) installed.

<details>
<summary><b>What <code>init</code> does, flag by flag</b></summary>

`init` copies the snapshot of [`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template) that ships inside this release, so a project made by vX.Y.Z is the template vX.Y.Z was released with, and its dependency line is pinned back to vX.Y.Z.

- **Answers** are prompted for, or given as flags: `--name` (default: the folder's name), `--title`, `--author` and `--email` (default: your git config), `--description`, `--first` (the first presentation's folder, default `kickoff`; `kickoff/v1` groups versions from the start) and `--deck-title`. `--yes` takes the defaults for anything unset. They rename the project in `pyproject.toml`, `package.json`, `package-lock.json`, `manifest.yaml` and `README.md`, and move `presentations/example/` to the first presentation.
- **The folder** can be new, empty, or an existing one to knit into (`init .`). Everything is assembled in memory first. If any file would be replaced, `init` lists them and writes nothing; `--force` overwrites them.
- **`--git`** adds `git init` and a first commit. Without it there's no `.git`.
- **`uv.lock`** is left out in every mode, so the first `uv sync` locks the project against its own pin.
- **`--from gh:owner/repo[@ref]`** starts from a GitHub tarball instead, e.g. your lab's fork of the template. No git binary needed; `GH_TOKEN` (or `GITHUB_TOKEN`) reaches a private fork. A fork's own pin is left alone.
- **The agent skill** goes into `.claude/skills/presentation-sanity/` and `.agents/skills/presentation-sanity/` unless `--no-skills`.

</details>

## What goes in, what comes out

<img src="https://sanitism.dev/figures/presentation-pipeline.svg" alt="What you write: manifest.yaml, presentations/kickoff/v2 with slides.md and blog.md, scenes/*.py for manim, and shared components. presentation-sanity build renders scenes and figures once. What your audience gets: a Slidev deck, a blog post, and PowerPoint with the manim videos still playing." width="100%">

Slides and a blog post are two printouts of the same material, not two projects. [Slidev](https://sli.dev) and [VitePress](https://vitepress.dev) sit on the same substrate (Vite, Vue 3, markdown-it, Shiki), so one set of components, one manifest and one `public/` folder back both. `<DataValue var="num_samples" />` in a `blog.md` reads the same YAML as the same tag in a `slides.md`, and a manim scene renders once and plays in both.

- **A Slidev deck** you present from the browser, or export to PDF.
- **A VitePress blog post** that cites the same numbers in prose, with math rendered to static SVG and citations from your `.bib`.
- **PowerPoint** with the manim videos embedded and still playing, for the conference laptop.

Click any number in either output and a provenance panel slides in: its inputs, the command that made it, and the date.

| Command | What runs | When |
|---|---|---|
| `presentation-sanity dev kickoff:slides` | `slidev` with hot reload | Write the deck (`kickoff:blog` for the post). |
| `presentation-sanity build [TARGET]` | figures, then manim scenes (both cached), then every output | Build everything, or one presentation or output. |
| `presentation-sanity check` | every `<DataValue>`, scene, figure and `\cite` resolved | Before you call it done. |
| `presentation-sanity new kickoff/v2 --from kickoff/v1` | a copied presentation, with its lineage recorded | The next version of a talk. |
| `presentation-sanity export-pptx kickoff` | PPTX with embedded, playable manim | PowerPoint that isn't just images. |
| `presentation-sanity pages init` | `.github/workflows/pages.yml` | Publish ([below](#deploy-to-github-pages)). |

<details>
<summary><b>Every command</b></summary>

Verbs take an optional **target**: a presentation id (its path under `presentations/`), optionally with an output, as in `kickoff/v2:blog`. A grouping folder selects every presentation in it.

| Command | What runs | When to use |
|---|---|---|
| `presentation-sanity init my-talks` | Copy the bundled template into a folder, name it, install the agent skill | Start a project, no git needed. |
| `presentation-sanity list` | List the presentations and their outputs (`outputs` is an alias) | Check what exists and what's built. |
| `presentation-sanity new kickoff/v2 --from kickoff/v1` | Copy a presentation into a new folder and record the lineage | Start a new version. |
| `presentation-sanity build` | Validate the manifest, export stale figures, render stale manim scenes, render every output | Build everything. |
| `presentation-sanity build kickoff/v2:blog` | Same, for one target | Build one printout. |
| `presentation-sanity dev kickoff:blog` | `vitepress dev` with hot reload | Write the post. |
| `presentation-sanity dev kickoff:slides` | `slidev` with hot reload | Iterate on slides. |
| `presentation-sanity scaffold` | Regenerate the VitePress config without building | Editor tooling, or reading what was generated. |
| `presentation-sanity build-manim` | Render only stale manim scenes | You edited a scene. |
| `presentation-sanity build-figures` | Export only stale Excalidraw figures | You edited an `.excalidraw` source. |
| `presentation-sanity preview` | `python http.server` on `site/` | Smoke-test the static build (browsers won't load `file://`). |
| `presentation-sanity export pdf` | `slidev export` | A PDF of the deck. |
| `presentation-sanity export-pptx` | PPTX with **embedded, playable** manim video | PowerPoint that isn't just images. |
| `presentation-sanity check` | Resolve every `<DataValue>`, scene, figure and `\cite`; warn about unrendered scenes and figures, and components that start a line | Before you call it done. |
| `presentation-sanity skills` | (Re)install the agent skill into `.claude/skills/` and `.agents/skills/` | After upgrading the tool. |
| `presentation-sanity pages init` | Write `.github/workflows/pages.yml` | Deploy to GitHub Pages. |

`build` degrades gracefully without manim: it logs a clear message and uses the pre-rendered videos already in `public/manim/`. The same goes for figures: export uses [`excalidraw-brute-export-cli`](https://github.com/realazthat/excalidraw-brute-export-cli) via `npx` (first run: `npx playwright install firefox`), and `build` skips it when it isn't installed. So a deploy never needs cairo, pango or a headless browser, as long as the rendered files are committed.

</details>

## Projects: every talk, one repo

A repo whose root holds `manifest.yaml` **and a `presentations/` folder** is a project. Every folder under `presentations/` with a `slides.md` and/or a `blog.md` is a presentation, and its path is its id. Folders without one just group presentations, and that is all a version is:

```
my-talks/
├── manifest.yaml                 # SHARED: variables, scenes, figures, bibliography, math,
│                                 #   and defaults for every presentation's outputs
├── public/  scenes/  refs.bib    # shared assets and sources
├── shared/                       # the shared Vue layer, a local Slidev addon
└── presentations/
    ├── kickoff/                  # a grouping folder
    │   ├── v1/slides.md          #   id kickoff/v1
    │   └── v2/                   #   id kickoff/v2
    │       ├── slides.md
    │       ├── blog.md
    │       ├── manifest.yaml     #   optional: metadata and output overrides
    │       └── components/X.vue  #   optional: replaces shared/components/X.vue here
    └── lab-meeting/slides.md     # id lab-meeting
```

- **Outputs** come from the files a presentation has: `slides` for `slides.md`, `blog` for `blog.md`. Each builds to `site/<id>/<output>/`, and `site/index.html`, refreshed on every build, lists them grouped by folder.
- **A presentation's `manifest.yaml`** may only hold `metadata` (title, date, venue, authors, `from`) and `outputs` overrides (`blog: false` opts out). Variables, scenes, figures, bibliography and math are project-wide, so they never fork: when a number changes, add a new key and point the new version at it.
- **`new <id> [--from <id>] [--title T]`** creates a presentation, or copies one (skipping exports and Slidev's scratch state), retitles it, and records `from:` in its manifest.
- **`--base`** is the deploy prefix for all of `site/`: decks build with a relative `./`, blogs with `<prefix><id>/<output>/`.
- A repo **without** `presentations/` is a single subject: one `slides.md` and/or `blog.md` at the root, building to `site/`.

<details>
<summary><b>Why the shared layer is a Slidev addon</b></summary>

Slidev takes components, layouts, global layers, styles and `vite.config.ts` from the folder of the deck it builds, so a deck at `presentations/<id>/` sees nothing at the project root. The shared files therefore live in `shared/`, packaged as a local addon and enabled once for every deck:

```jsonc
// package.json
"devDependencies": { "psanity-shared": "file:./shared" },
"slidev": { "addons": ["psanity-shared"] }
```

`shared/package.json` (just a `name`) is required. `shared/vite.config.ts` sets an **absolute** `publicDir` (the project's `public/`; a relative one would resolve against the deck's folder), registers the YAML plugin, defines `@project` / `@shared` aliases for depth-independent imports, and sets `slidev.components.allowOverrides` so a presentation's `components/X.vue` wins over the shared one. A package name is used rather than a relative path because Slidev resolves relative addon paths against the deck's *parent* folder.

For blogs, the generated VitePress config does the equivalent: `srcDir` stays the project root (VitePress copies `<srcDir>/public` verbatim), the site is narrowed to one presentation with `srcExclude` + `rewrites`, the same two aliases are defined, and the theme registers `shared/components` then the presentation's own `components`. Each blog's config is written to `.cache/vitepress/<id>/.vitepress/`, so two blogs can run `dev` at once.

`build` and `dev` stop early with "run `npm install`" when the addon isn't linked into `node_modules`, and warn when a project still has `components/` or `layouts/` at its root, where decks can't see them.

</details>

## The manifest

The template's, shortened, plus a `figures:` entry to show the shape of an Excalidraw source:

```yaml
metadata:
  title: "Presentation Sanity Demo"
  description: "A single source of truth for slides and writing."
  authors:
    - { name: "Your Name", email: "you@example.com" }

outputs:                    # defaults for every presentation's outputs
  blog: {}                  # nav, sidebar, socialLinks, themeConfig, … are forwarded to VitePress
  slides: {}                # a deck's look lives in its slides.md headmatter

variables:
  num_samples:
    value: 12453
    format: ","             # Python-style spec: , .2e .3f .1%
    description: "Participants after QC filtering"
    source: "data/results.csv"        # or `data:` for a list of inputs
    command: "python scripts/qc.py data/raw/ --out data/results.csv"
    updated: "2026-09-30"
  num_samples_2026q1:       # March's number keeps its own key, so March's talk keeps showing it
    value: 11982
    format: ","

scenes:
  one_source:
    source: "scenes/one_source.py"
    class: "OneSource"
    quality: "h"            # l | m | h | p | k
    format: "webm"

figures:
  pipeline:
    source: "excalidraw/pipeline.excalidraw"
    format: "svg"           # svg | png

bibliography:
  sources: ["refs.bib"]
  style: numeric            # numeric → [1] | author-year → (Smith et al., 2020)
```

Provenance fields (`description`, `source`, `data`, `command`, `updated`) are **informational**: they appear in the provenance panel but are never executed, which keeps the build hermetic.

## Writing

**A number with its provenance**, identical in both outputs:

```markdown
We analyzed <DataValue var="num_samples" /> participants after QC.
```

**A manim scene, two ways.** Full-screen in the deck:

```markdown
---
layout: manim
scene: one_source
---
```

Inline in the post, playing when scrolled into view and pausing when scrolled out:

```markdown
The idea in one picture: <ManimFigure scene="one_source" caption="One source, every printout." />
```

Both read `public/manim/one_source.webm` plus the last-frame poster `build-manim` extracts, so the finished frame shows wherever video can't play (first paint, PDF and PPTX export, print).

> [!TIP]
> Keep a component tag off the *start* of a line. markdown-it reads a line beginning with `<Tag` as an HTML block and closes the paragraph around it; `check` warns when it finds one.

**Figures** from Excalidraw: `<FigureImage figure="pipeline" />`. **Citations:** `\cite{key}` and `\bibliography`, [below](#citations).

<details>
<summary><b>Math</b></summary>

The blog renders LaTeX to **static SVG at build time** (MathJax via `markdown-it-mathjax3`, full package set): no client-side math runtime, no flash of unstyled TeX, and it prints correctly. `$…$` and `$$…$$` work as expected, and display environments can be written bare, the way you would in a `.tex` file:

```markdown
\begin{align}
h^2 &= \frac{\sigma^2_A}{\sigma^2_P} \\
    &= \frac{\sigma^2_A}{\sigma^2_A + \sigma^2_E}
\end{align}
```

`align`, `equation`, `gather`, `multline` and friends are recognised at block level, starred variants included. Environments not on the list stay literal, an unterminated `\begin{…}` falls back to a paragraph, and nested constructs like `cases` and `pmatrix` still need `$$` fencing.

```yaml
math:
  macros:
    Var: "\\operatorname{Var}"
    RR: "\\mathbb{R}"
    norm: ["\\left\\lVert #1 \\right\\rVert", 1]   # [expansion, arg count]
  tags: none            # none | ams | all
  environments: true    # or false, or an explicit list of env names
  packages: [...]       # optional; overrides MathJax's AllPackages
  tex: {}               # raw markdown-it-mathjax3 `tex` passthrough
  svg: {}               # raw `svg` output passthrough
```

**Define macros here, not with an in-document `\newcommand`.** The renderer keeps one TeX instance for the whole build, so an in-document definition leaks into every later block and page, and whether it resolves depends on source order. `tags: ams` numbers display equations and enables `\label`/`\eqref`; the counter is shared across the build, so with several pages prefer an explicit `\tag{…}` or reset with `\setcounter{equation}{0}`.

The deck renders math with **KaTeX** (Slidev's built-in), so `math.macros` reaches the blog only; configure the deck's macros in Slidev's `setup/katex.ts` if you need them in both.

</details>

### Citations

LaTeX-shaped citing without a LaTeX toolchain:

```yaml
bibliography:
  sources: ["refs.bib"]     # a path, a list of paths, or a full mapping
  style: numeric            # numeric → [1]  |  author-year → (Smith et al., 2020)
  sort: appearance          # appearance | author | year
  title: "References"
  heading: h2
  link: true                # render the DOI / URL as a link
```

| Command | numeric | author-year |
|---|---|---|
| `\cite{k}`, `\citep{k}` | `[1]` | `(Smith et al., 2020)` |
| `\citet{k}` | `Smith et al. [1]` | `Smith et al. (2020)` |
| `\cite{a,b}` | `[1, 2]` | `(Doe, 1996; Smith, 2020)` |
| `\cite[p. 12]{k}` | `[1, p. 12]` | `(Smith et al., 2020, p. 12)` |
| `\nocite{k}` | listed, not cited inline | |
| `\bibliography`, `\printbibliography` | the reference list | |

Parsing and formatting happen at build time, so the page ships plain anchors and no citation runtime. Every citation links to its entry and shows the full reference on hover, and numbering is resolved in a second pass, so `sort: author` renumbers the markers and the list together. The BibTeX parser is dependency-free and handles `@string` macros and `#` concatenation, brace-protected capitals, accents (`M{\"u}ller` → Müller), dashes, `and others`, and inline math in titles. An unknown key renders a visible `[?key]` and logs a warning. Citations inside code spans and math are left alone. Like `math.macros`, citations currently reach the blog only, and editing a `.bib` needs a `dev` restart.

<details>
<summary><b>The generated VitePress config, and theming the blog</b></summary>

`presentation-sanity` writes `.vitepress/config.mts` and `.vitepress/theme/index.ts` from the manifest before every `dev` and `build` (in a project, under `.cache/vitepress/<id>/`). It is generated, gitignored and never hand-edited. The theme glob-registers every component under its filename (the Slidev convention, so components work in Markdown with no imports), mounts `ProvenancePanel` in the `layout-bottom` slot, and imports `blog.css` when present.

The config sets **`vite.configFile: false`**, which is load-bearing: the project also carries a `vite.config.ts` for Slidev, and merging it in would apply `@modyfi/vite-plugin-yaml` a second time (handing every component a string instead of the manifest) as well as Slidev's `base: './'`, which VitePress's router can't use. Optional Node packages are detected at scaffold time: `markdown-it-mathjax3` enables math, `@modyfi/vite-plugin-yaml` lets `<DataValue>` read the manifest. `presentation-sanity scaffold` regenerates the directory without building.

| Lever | Where | Reaches |
|---|---|---|
| `outputs.<key>:` keys | `manifest.yaml` | `nav`, `sidebar`, `socialLinks`, `outline`, `footer`, `head`, `markdown`, `base`, `title`, `description`, `exclude`, `lastUpdated` |
| `themeConfig:` | `manifest.yaml` | any other default-theme option: `logo`, `aside`, `search`, `editLink`, `docFooter`, … |
| `vitepress:` | `manifest.yaml` | any other top-level VitePress option: `appearance`, `lang`, `titleTemplate`, `sitemap`, … (`outDir`, `rewrites` and `cacheDir` stay owned by the build) |
| `blog.css` | `shared/`, or a presentation's folder | imported **last**, so it overrides VitePress's CSS variables and the built-in citation styles |

**One VitePress site per presentation.** Extra Markdown files next to `blog.md` become extra pages of the same site, and every other output's entry is excluded automatically, so `slides.md` never becomes a page.

</details>

## Deploy to GitHub Pages

> [!WARNING]
> A GitHub Pages site is **public**, even when the repository is private.

```bash
uv run presentation-sanity pages init      # → .github/workflows/pages.yml
```

Then turn Pages on (Settings → Pages → Source: **GitHub Actions**, or `gh api -X POST repos/OWNER/REPO/pages -f build_type=workflow`) and push to `main`. On each push the workflow asks `actions/configure-pages` for the site's base path (`/<repo>` for a project site, empty for a custom domain), runs `uv sync --locked --no-default-groups` and `npm ci`, builds with `--skip-manim --skip-figures --base "<base path>/"`, and deploys `site/`. The [template's demo](https://presentation.sanitism.dev/) is built exactly this way.

- **The runner never renders manim.** Rendering needs cairo, pango, ffmpeg and LaTeX, which is slow and fragile on every push. So the workflow installs without the `manim` group and deploys the videos committed in `public/manim/`: the render you looked at, not a fresh one that might differ. Figures work the same way.
- **`pages init` checks first.** It refuses a project whose `[project]` dependencies still say `presentation-sanity[manim] @ …` (and prints the move into a `manim` group), and notes a missing `uv.lock` or `package-lock.json`, or scenes and figures that aren't rendered or that `.gitignore` would keep out.
- **Options:** `--branch` (default `main`), `--only-repo OWNER/NAME` (forks and template copies skip the job), `--force` to regenerate.
- **Any static host works.** Decks use hash routing and blogs build real `.html` routes, so `site/` works on S3, R2 or Netlify with no rewrite rules. Slidev takes a relative base and works under any prefix; VitePress needs an absolute one, which `--base` sets for every blog: `presentation-sanity build --base /my-talks/` puts kickoff/v2's post at `/my-talks/kickoff/v2/blog/`.

## Agent skill

`init` installs a skill for coding agents into `.claude/skills/presentation-sanity/` (Claude Code: `/presentation-sanity [mode]`) and `.agents/skills/presentation-sanity/` (other agents). Ask for the work instead of looking up flags:

| Ask | What happens |
|---|---|
| `/presentation-sanity new` | The next version of a talk, as a new folder. |
| `/presentation-sanity slides` or `blog` | Write the deck or the post, with numbers from the manifest. |
| `/presentation-sanity manim` | A scene, registered, rendered and placed. |
| `/presentation-sanity deploy` | GitHub Pages, after confirming the work is meant to be public. |

The other modes: `init`, `figures`, `variables`, `cite`, `export` and `check`.

- **It explains; the CLI does.** Every mode works through commands rather than having the agent write generated files.
- **It finds the project** from its sentinel files (`manifest.yaml` next to `presentations/`, or a `package.json` depending on `psanity-shared`).
- **It checks the version.** When `presentation-sanity --version` differs from the version it was written for, it trusts `--help` over its own text.

The wheel carries the skill; `presentation-sanity skills [--force]` refreshes it after an upgrade. The repo is also a Claude Code plugin (`.claude-plugin/plugin.json`).

## System dependencies

Only for **rendering manim scenes locally**:

- macOS: `brew install ffmpeg cairo pango`
- Linux: `apt install ffmpeg libcairo2-dev libpango1.0-dev`
- LaTeX for `MathTex`: [TeX Live](https://tug.org/texlive/) or BasicTeX.

To build against videos already committed in `public/manim/`, you need none of these: install with `uv sync --no-default-groups`, and `build` skips manim with a log line. `--skip-manim` does the same when manim *is* installed.

## House rules

```yaml
# sanitism.yaml
principles:
  one_manifest: everything else is generated, never hand-edited
  every_number_has_a_source: the file, command and date travel with the value
  versions_are_folders: not branches, and not final_v3_REAL.docx
  one_repo_per_obsession: papers, proposals and talks share figures and numbers
  same_input_same_output: a rebuild never surprises your co-authors
```

## Install the tool directly

For local development on the tool itself:

```bash
git clone https://github.com/yakaboskic/presentation-sanity
cd presentation-sanity
uv sync
uv run presentation-sanity --help
uv run pytest
```

To iterate on the tool against a real project, clone [`presentation-sanity-template`](https://github.com/yakaboskic/presentation-sanity-template) alongside this repo and point its dependency at the local checkout:

```toml
[tool.uv.sources]
presentation-sanity = { path = "../presentation-sanity", editable = true }
```

<details>
<summary><b>The project's dependencies, as the template writes them</b></summary>

**`pyproject.toml`:**

```toml
[project]
name = "my-talks"
version = "0.1.0"
requires-python = ">=3.10"
# Pin a release tag (https://github.com/yakaboskic/presentation-sanity/releases),
# not @main; to upgrade, change the tag and run `uv lock`.
dependencies = [
    "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.4.2",
]

# manim (the machine needs ffmpeg, cairo, pango and LaTeX). A default group:
# `uv sync` installs it; `uv sync --no-default-groups` leaves it out.
[dependency-groups]
manim = ["presentation-sanity[manim]"]

[tool.uv]
default-groups = ["manim"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.metadata]
allow-direct-references = true

[tool.hatch.build.targets.wheel]
bypass-selection = true        # the project has no importable Python
```

The group's `presentation-sanity[manim]` has no URL: uv takes it from the pinned line, so an upgrade is still one tag. Keeping manim out of the main dependency line is what lets a deploy runner, or a co-author without the native tools, install with `--no-default-groups`.

**`package.json`:** install only the engines you use; a blog-only project can drop the Slidev dependencies.

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
    "vitepress": "^1.6.3",
    "psanity-shared": "file:./shared"
  },
  "slidev": { "addons": ["psanity-shared"] }
}
```

</details>

### Releasing

Subject repos and the template pin release tags, so a change reaches them
only through a release. Each release also carries a snapshot of the template
(for `init`), so the two move together:

1. Bump the version in four places: `version` in `pyproject.toml`,
   `__version__` in `src/presentation_sanity/__init__.py`, `metadata.version`
   in `skills/presentation-sanity/SKILL.md`, and `version` in
   `.claude-plugin/plugin.json` (`tests/test_skill.py` fails until they
   agree). Update the tags in the snippets above.
2. In `presentation-sanity-template`, move the pin to the new tag (the
   `pyproject.toml` dependency line and the README's mentions), regenerate the
   demo workflow with `presentation-sanity pages init --force --only-repo
   yakaboskic/presentation-sanity-template`, and commit.
3. Back here, refresh the snapshot from that commit and commit it:
   ```bash
   uv run python scripts/sync_template.py      # tracked files only, via git archive
   uv run pytest
   ```
4. Push to `main`, then tag and publish:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z — summary" && git push origin vX.Y.Z
   gh release create vX.Y.Z --verify-tag --title "vX.Y.Z — summary" --notes-file notes.md
   ```
5. In the template, once the tag exists: `uv lock` (it resolves the new tag),
   build the example presentation (it renders its manim scene), commit
   `uv.lock` (and any re-rendered `public/manim/`), and push. The Pages
   workflow deploys the demo. The snapshot has no lock (`init` would skip
   it anyway): a new project's first `uv sync` writes its own.

## Lineage

presentation-sanity is the sibling of [document-sanity](https://github.com/yakaboskic/document-sanity), and both grew out of [meta-sanity](https://github.com/yakaboskic/meta-sanity): declare it once, generate the rest. It is a thin orchestration layer around [Slidev](https://sli.dev) (the deck), [VitePress](https://vitepress.dev) (the blog, chosen because it shares Slidev's substrate) and [manim](https://www.manim.community/) (the animations, pre-rendered and cached).

---

<sub>Part of <a href="https://sanitism.dev">Sanitism</a>. Also in the family: <a href="https://github.com/yakaboskic/document-sanity">document-sanity</a> for papers and proposals. MIT licensed.</sub>
