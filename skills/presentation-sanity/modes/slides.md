# slides: the Slidev deck

The deck is `presentations/<id>/slides.md`. Slidev's own docs
(https://sli.dev) cover the syntax. This is what's specific to a
presentation-sanity project.

## Structure

- The **first** frontmatter block (the headmatter) configures the whole deck:
  `theme`, `title`, `author`, `transition`, `fonts`. Keep `routerMode: hash`,
  because it lets the built deck run on any static host.
- Slides are separated by `---`. Per-slide frontmatter picks a `layout`.
- Click-by-click reveals: `v-click` / `<v-clicks>`. `export-pptx` turns each
  click into its own slide unless `--no-clicks` is passed.

## What the shared layer gives every deck

| Use | Write |
|---|---|
| a number from the manifest | `<DataValue var="num_samples" />`, clickable, opens the provenance panel |
| a full-screen manim scene | a slide with `layout: manim` and `scene: <key>` in its frontmatter |
| an Excalidraw figure | `<FigureImage figure="<key>" />` |
| an image or logo | `/figures/logo.svg`: paths into the project's `public/` |

`layout: manim` options: `scene` (required), `format` (webm), `autoplay`,
`controls`, `background`, `replayKey` (r), `pauseKey` (p).

## Rules that bite

- A number in a slide goes through `<DataValue>`, always (see `variables`).
- Keep component tags off the start of a line.
- Math in decks is **KaTeX** (Slidev's built-in): `math.macros` in the
  manifest reaches blogs only. `\cite{}` also works in blogs only. In a deck,
  write the short reference by hand and keep the full entry in `refs.bib`.
- Deck-only CSS for one presentation goes in `presentations/<id>/style.css`
  (loads after `shared/style.css`). Use a scoped `<style>` block for one slide.
- To change a shared component for this deck only, copy it to
  `presentations/<id>/components/` and edit the copy.

## Loop

```bash
uv run presentation-sanity dev <id>:slides   # http://localhost:3030, hot reload
uv run presentation-sanity check <id>
uv run presentation-sanity build <id>:slides
```

Adding or removing a global file like `shared/global-bottom.vue` while `dev` is
running needs a restart: press `r` in the Slidev terminal.
