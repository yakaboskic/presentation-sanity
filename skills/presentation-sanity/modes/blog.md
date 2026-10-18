# blog: the VitePress post

The post is `presentations/<id>/blog.md`. It and `slides.md` are two printouts
of the same material, with the same components, numbers and scenes. Other
`.md` files next to `blog.md` become extra pages of the same site.

## Writing

- Frontmatter: `title`, `outline: [2, 3]`, `layout: doc|page|home`,
  `aside: false`, `pageClass: …`.
- `<DataValue var="key" />` for every number, the same component as the deck.
- `<ManimFigure scene="key" caption="…" />` embeds a scene inline. It plays
  when scrolled into view.
- `<FigureImage figure="key" />` for Excalidraw figures.
- Math is MathJax rendered to SVG at build time: `$…$`, `$$…$$`, and bare
  `\begin{align}…\end{align}` blocks. Macros go in `manifest.yaml` under
  `math.macros`, never as `\newcommand` in the document.
- Citations: `\cite{key}` and a `\bibliography` line where the list goes (see
  `cite`).
- Keep component tags off the start of a line.

## Theming, lightest lever first

1. `manifest.yaml` → `outputs.blog:` (all blogs) or the presentation's own
   manifest (this blog): `nav`, `sidebar`, `socialLinks`, `outline`, `footer`,
   `head`, plus `themeConfig:` and `vitepress:` escape hatches.
2. `shared/blog.css` (all blogs), then `presentations/<id>/blog.css` (this
   one). Both load last, so they override VitePress's CSS variables.
3. Per-page frontmatter.
4. Components in `shared/components/` or `presentations/<id>/components/`.

There is no `.vitepress/` to edit. The tool generates it into `.cache/` from
the manifest on every build. `uv run presentation-sanity scaffold <id>`
writes it without building, if you need to read what was produced.

## Loop

```bash
uv run presentation-sanity dev <id>:blog     # http://localhost:5173
uv run presentation-sanity check <id>
uv run presentation-sanity build <id>:blog
```

Editing `refs.bib` needs a dev-server restart. Editing the post doesn't.
