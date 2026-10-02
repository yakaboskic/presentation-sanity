# Spike: step through manim scenes on Slidev clicks (issue #2)

**Date:** 2026-10-02 · **Branches:** `spike/manim-steps` in presentation-sanity
and presentation-sanity-template · **Recommendation: go** (opt-in, details below)

## Question

Today a scene renders to one video and `layout: manim` plays all of it when the
slide opens. The "community extension that drives a manim animation from HTML
with checkpoints" is **manim-slides** (5.7.0, released 2026-09-14, MIT). Can a
scene instead advance checkpoint by checkpoint on Slidev's own clicks —
forward, back, presenter view, exports — while staying static-hostable?

## Options looked at

| Option | Verdict |
|---|---|
| manim-slides' own HTML export (reveal.js) in an iframe | Rejected: two keyboard handlers fighting over arrows, focus trapping, no click-by-click export, going back replays from the start (upstream PR #646 open). |
| **manim-slides for authoring + our own Slidev layout** | **Built and tested — works.** |
| Manim CE native sections (`next_section()` + `--save_sections`) | Viable zero-dependency fallback: the same render writes a sections index too, but it has no loop/auto-advance/notes flags. Not needed. |
| In-browser manim renderers (manim-web etc.) | Not production-ready; scenes would have to be ported. |

## What was built

**Authoring.** A scene subclasses `manim_slides.Slide` and ends each segment
with `self.next_slide()` (`loop=True` repeats a segment until the next click,
`auto_next=True` advances by itself, `notes=` annotates it). The manifest opts
in per scene:

```yaml
scenes:
  intro_steps:
    source: "scenes/intro_steps.py"
    class: "IntroSteps"
    steps: true
```

**Render (`manim_render.py`).** The existing `python -m manim render` call is
unchanged except that it runs with `cwd=` the temp dir, because manim-slides
writes `./slides/<Class>.json`. With `steps: true` the segments are copied to
`public/manim/<key>/00.webm …`, each gets a *true* last-frame poster, and a
normalized `segments.json` (file, loop, auto_next, notes, poster) is written.
The full `public/manim/<key>.webm` is still produced, so `<ManimFigure>` and
`layout: manim` keep working with the same scene.

**Deck (`shared/layouts/manim-steps.vue` + a Vite virtual module).**

```markdown
---
layout: manim-steps
scene: intro_steps
---
```

- N segments register N−1 Slidev clicks in `onMounted` (the pattern Slidev's
  own `VSwitch` uses). The count has to be known synchronously at mount — the
  click-by-click export counts what is registered then — so
  `virtual:psanity-manim` (a ~25-line plugin in `shared/vite.config.ts`) reads
  every `public/manim/*/segments.json` from disk.
- Entering plays segment 0, each click plays the next, and after the last one
  Slidev moves to the next slide. Going back shows the checkpoint's last frame
  (no reverse playback); loop segments loop; `auto_next` calls `next()`.
- All segments are preloaded and stacked; the previous checkpoint's poster sits
  underneath, so a switch can't flash black.
- Print/export, overview and the presenter's "next" preview show the
  checkpoint's poster instead of playing.

**PPTX (`pptx_export.py`).** A stepped slide becomes one PowerPoint slide per
click step, each embedding that segment as MP4 (autoplay; `repeatCount=
"indefinite"` for loop segments).

## Findings

1. **One render produces everything.** Plain `python -m manim render … --format
   webm -o <key>` with a `Slide` subclass wrote the full movie, manim-slides'
   index + per-segment files, and (with `--save_sections`) Manim's own sections
   index. Segments are VP9 WebM; their durations sum to the full movie.
2. **Reversal breaks WebM.** With reversing on, the render fails:
   `ValueError: 'webm' format does not support 'libx264' codec`. Stepped scenes
   must set `skip_reversing = True`; the deck never needed reversed clips.
3. **The existing poster is not the last frame.** `_extract_poster`
   (`-sseof -1 … -frames:v 1`) grabs the frame one second before the end — for a
   1 s segment that is its *first* frame (SSIM 1.000 vs first, 0.973 vs last).
   Segments use a new `_extract_last_frame` (`-sseof -0.5 -update 1`, SSIM 1.000
   vs the true last frame). Whole-scene posters were left alone (see follow-ups).
4. **Clicks and playback behave.** Driven in headless Chromium with real
   playback: entering played segment 0 to its end; → played 1, 2 (still looping
   after 2.6 s), 3; → then went to the next slide; ← came back onto the last
   checkpoint as a still; ← through the checkpoints showed each poster (the
   loop segment played again); ← left the slide. The still shown on "back" is
   pixel-identical to the frame the segment ended on.
5. **Exports.** `slidev export --with-clicks` produced one PNG per checkpoint
   (`005-01 … 005-04`), each matching its poster (SSIM ≈ 0.988; the caption
   overlay is the difference). `export-pptx` produced slides 10–13 with four
   distinct embedded segments, autoplaying, slide 12 looping.
6. **Presenter view.** The presenter's current slide plays and steps normally;
   the "next" preview renders a still — but of the first checkpoint, not the
   upcoming one (see known issues).
7. **Footprint.** manim-slides adds pydantic, jinja2, lxml, rtoml, requests,
   python-pptx and `qtpy` (a shim — no Qt unless the presenter extra is
   installed) on top of manim. Python ≥3.11 in practice (manim 0.21).

## Not verified (needs eyes on a real screen)

- Visual seamlessness of segment switches in Chrome, Safari and Firefox on a
  visible display (the in-app browser pane was hidden, and Chrome pauses
  video-only media in background tabs).
- The PPTX in PowerPoint (Mac/Windows) and Keynote: autoplay and loop rely on
  timing XML that manim-slides itself labels experimental.
- `auto_next` (the demo scene has no auto-advancing segment).

## Known issues

- **Presenter "next" preview** shows checkpoint 0 for the upcoming state. The
  layout registers with the clicks context it got at setup; the preview likely
  swaps contexts without remounting. Cosmetic.
- `export-pptx`'s closing summary counts only whole-scene videos.

## Recommendation

**Go**, as an opt-in feature: keep `layout: manim` for whole-scene playback and
add stepped scenes behind `steps: true` + `layout: manim-steps`. Pin
`manim-slides==5.7.*` and `manim==0.21.*` (Manim's unreleased main branch
reworks output config and may break manim-slides), and always read segment
files from the JSON, never by name.

## Follow-up tasks

1. Productionize: tests for `_collect_segments` and the stepped PPTX path, the
   layout + virtual module in the template's `shared/`, docs, an optional
   `presentation-sanity[slides]` extra (`manim-slides[manim]`).
2. Decide whether one layout should handle both (`layout: manim` switching to
   stepped mode when `segments.json` exists).
3. Fix the presenter "next" preview checkpoint.
4. Surface segment `notes` in Slidev's presenter notes (Slidev's `[click]`
   markers line up with segments).
5. Decide whole-scene poster semantics: "1 s before the end" often *is* the best
   summary frame (scenes that fade out end on black), so make it explicit
   rather than calling it the last frame.
6. Correct the `export-pptx` summary count.
