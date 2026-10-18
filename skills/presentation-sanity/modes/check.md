# check: is it actually right?

Run this before telling the user something is done, and report what each step
said, including warnings.

## 1. References

```bash
uv run presentation-sanity check [<id>…]
```

It reads every presentation's documents and confirms that each
`<DataValue var>`, manim `scene` (`layout: manim` or `<ManimFigure>`),
`<FigureImage figure>` and `\cite` key is declared, and that each scene and
figure has been rendered into `public/`. It exits non-zero on a missing
reference. It also warns when a `<DataValue>` or `<FigureImage>` starts a line
inside a paragraph (ground rule 6). Fix what it reports. Don't silence it.

## 2. Build what you touched

```bash
uv run presentation-sanity build <id>                 # or <id>:slides / <id>:blog
uv run presentation-sanity build                      # everything, before a deploy
```

Read the output. Lines to act on: `warning:` (unknown citation keys, missing
bib sources), `manim not installed — skipping render` (the scene in `site/` is
the old render), and anything from Slidev or VitePress.

## 3. Look at it

```bash
uv run presentation-sanity preview <id>     # serves site/ at :8000, runs until stopped
```

Opening `site/index.html` as a file shows a blank page, because browsers
won't load ES modules over `file://`. If you can drive a browser, open the
preview, check the slide or section you changed, click a `<DataValue>` to see
its provenance panel, and play a manim slide. If you can't, say so and ask
the user to look.

## What "done" means

`check` is clean, the build has no new warnings, and someone has looked at the
change. Say which of those you did.
