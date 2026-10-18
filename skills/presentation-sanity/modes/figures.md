# figures: Excalidraw diagrams

An `.excalidraw` source exports to `public/figures/<key>.<format>`. Every deck
and post embeds the same image with `<FigureImage figure="<key>" />`.

## Add a figure

1. The user draws it in Excalidraw (excalidraw.com or the VS Code extension)
   and saves the `.excalidraw` file in the project, e.g. `figures/pipeline.excalidraw`.
   Don't generate Excalidraw JSON by hand unless they ask for a starting
   sketch.
2. Register it in ROOT `manifest.yaml`:
   ```yaml
   figures:
     pipeline:
       source: "figures/pipeline.excalidraw"
       format: "svg"        # svg | png
       # scale: 1, background: false, dark: false, embed_scene: false
   ```
3. Export: `uv run presentation-sanity build-figures`. It's cached by content
   hash. The exporter (`excalidraw-brute-export-cli`, Playwright + Firefox)
   installs on demand. The first run may need `npx playwright install firefox`.
4. Use it: `<FigureImage figure="pipeline" />`, in a slide or the post.

## Commit the export

`build` skips figure export when the exporter isn't installed, and the Pages
workflow never exports. Both use the images committed in `public/figures/`.
So commit the exported file whenever its source changes.

For a plain image (a photo, a logo), skip all this: drop it in `public/` and
reference it as `/figures/logo.svg`.
