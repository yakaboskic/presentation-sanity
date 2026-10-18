---
name: presentation-sanity
description: >-
  Write, build and ship talks with presentation-sanity: Slidev decks, VitePress
  blog posts, manim scenes, Excalidraw figures and numbers with provenance, all
  driven by one manifest.yaml. Use in a presentation-sanity project (a
  manifest.yaml next to presentations/, or a package.json that depends on
  psanity-shared) to start a project, add a talk or a new version, write slides
  or a post, add a variable, citation, figure or manim scene, export PDF/PPTX,
  check a build, or deploy to GitHub Pages.
argument-hint: "[init | new | slides | blog | manim | figures | variables | cite | export | check | deploy]"
user-invocable: true
license: MIT
metadata:
  version: "0.4.0"
  family: sanitism
---

# presentation-sanity, the router

One manifest is the source of truth, every output is generated, every number
carries its provenance, and a new version of a talk is a folder. That's the
whole Sanitism bit: built for autists to communicate their work, sanely.

**The skill explains; the CLI does.** When a command exists for a step, run
it. Don't hand-write what a command generates.

## 1. Find the project root

Walk up from the current directory to the nearest folder that has either

- `manifest.yaml` **and** a `presentations/` directory, or
- a `package.json` whose dependencies include `psanity-shared`.

Call that folder `ROOT`. Run every command from `ROOT` and resolve every path
in the mode files against it, never against the shell's starting directory.

- Neither found: there's no project yet. Use `init` mode.
- `manifest.yaml` with no `presentations/`: an older single-deck repo. `build`,
  `dev` and `export` still work, but `new` doesn't. Point the user at "Moving a
  single-deck repo into a project" in the template README before forking
  versions.

## 2. Check the tool against this skill

```bash
uv run presentation-sanity --version
```

This skill was written for the version in `metadata.version` above. If the
CLI reports a different version, **the CLI wins**: before you rely on a flag
or command named here, read `uv run presentation-sanity <command> --help`.
Then suggest `uv run presentation-sanity skills --force` to bring this skill
up to date with the installed tool.

If `uv run` can't find the tool, the project isn't installed yet: run
`uv sync` (and `npm install`) first, as in `init` mode.

## 3. Route

Always read `modes/_shared.md` first, then the mode's file. Mode files sit
next to this `SKILL.md`.

| `$mode` | Read | For |
|---|---|---|
| *(empty)* | the menu below | |
| `init` | `modes/init.md` | start a project, or name a fresh template copy |
| `new` | `modes/new.md` | a new presentation, or a new version of one |
| `slides` | `modes/slides.md` | write or restyle a Slidev deck |
| `blog` | `modes/blog.md` | write or theme a VitePress post |
| `manim` | `modes/manim.md` | add or change an animated scene |
| `figures` | `modes/figures.md` | Excalidraw diagrams |
| `variables` | `modes/variables.md` | a number, with its provenance |
| `cite` | `modes/cite.md` | citations and the bibliography |
| `export` | `modes/export.md` | PDF, PPTX, PNG |
| `check` | `modes/check.md` | is it actually right? (run before saying "done") |
| `deploy` | `modes/deploy.md` | GitHub Pages or another static host |

When `$mode` is free text rather than a mode name, pick the closest one: "add
a slide about X" is `slides`, "the sample size changed" is `variables`, "put
it online" is `deploy`, "make a v2 for the NIH review" is `new`. Say which mode
you picked.

## Menu

```
presentation-sanity, one manifest, many printouts

  /presentation-sanity init       start a project (or name a fresh template copy)
  /presentation-sanity new        new presentation, or fork a version (--from)
  /presentation-sanity slides     write the deck (Slidev)
  /presentation-sanity blog       write the post (VitePress)
  /presentation-sanity manim      animated scenes, rendered once, used everywhere
  /presentation-sanity figures    Excalidraw diagrams → public/figures/
  /presentation-sanity variables  numbers with provenance (<DataValue>)
  /presentation-sanity cite       \cite{} and the reference list
  /presentation-sanity export     PDF / PPTX with playable manim video
  /presentation-sanity check      references, renders, build: before "done"
  /presentation-sanity deploy     GitHub Pages (public!) or any static host
```
