# manim: animated scenes

A scene renders **once** to `public/manim/<key>.webm` (plus a last-frame
`<key>.poster.png`) and every deck and post embeds that same file.

## Add or change a scene

1. Write the class in `scenes/<name>.py` (subclass `manim.Scene`). Keep it to
   what the slide needs to say. Ask the user what the animation should show
   before choreographing it.
2. Register it in ROOT `manifest.yaml`:
   ```yaml
   scenes:
     my_scene:
       source: "scenes/my_scene.py"
       class: "MyScene"
       quality: "l"      # l while iterating; h (1080p) for the real thing
       format: "webm"
   ```
3. Render: `uv run presentation-sanity build-manim`. It's cached by content
   hash, so only scenes whose `.py` or manifest entry changed re-render.
   `--force` re-renders all of them.
4. Use it. Deck: a slide with `layout: manim` and `scene: my_scene`. Blog:
   `<ManimFigure scene="my_scene" caption="…" />`.
5. Look at the result (`dev`) before calling it done. A scene that rendered
   isn't necessarily a scene that's right.

## Rendering needs native tools

ffmpeg, cairo, pango and LaTeX (for `MathTex`). On macOS that's
`brew install ffmpeg cairo pango` plus BasicTeX. If `build-manim` says manim
isn't installed, the project was synced with `--no-default-groups`. Run
`uv sync` to bring the `manim` group back.

## Committing the render

Deploys don't render: the GitHub Pages workflow ships what's in
`public/manim/`. After a scene changes, commit the new `.webm` and
`.poster.png` along with the `.py`. If `.gitignore` still lists
`public/manim/`, `pages init` points that out. Ask before changing it.
