# init: start a project

Two situations. Work out which one you're in first.

## A. No project yet

Ask the user (one message, all at once, with defaults):

- the folder (new, or `.` for the current one)
- project title, author name and email
- the first presentation's folder (`kickoff`, or `kickoff/v1` to group versions
  from the start) and its title
- whether they want git (`--git`). Without it the folder has no `.git`, which
  is fine for people who don't want GitHub.

Then run the tool straight from its release, no install needed:

```bash
uvx --from "presentation-sanity @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.4.0" \
  presentation-sanity init DIR --yes \
  --title "Title" --author "Name" --email "me@lab.org" \
  --first kickoff --deck-title "Kickoff"
```

Use the newest release tag (https://github.com/yakaboskic/presentation-sanity/releases)
rather than the one written here, if it's newer. A lab that keeps its own fork
of the template adds `--from gh:owner/repo[@ref]`. `GH_TOKEN` must be set for a
private fork.

**Knitting into an existing folder** (`DIR` has files already): `init` never
overwrites. If it lists conflicts, show the user the list and ask. Then either
move those files aside, or rerun with `--force` if they say so.

## B. A fresh template copy

The folder has an `init.py` next to `manifest.yaml` and
`presentations/example/`. Someone used "Use this template" or cloned the
template. Ask the same questions, then:

```bash
python init.py --yes --title "Title" --author "Name" --email "me@lab.org" \
  --first kickoff --deck-title "Kickoff"
```

`init.py` is a thin shim. It runs `presentation-sanity init --in-place` with the
version pinned in `pyproject.toml`, renames `presentations/example/`, and
removes itself.

## Then (both cases)

```bash
cd DIR
uv sync          # presentation-sanity + manim
npm install      # Slidev + VitePress; links shared/
uv run presentation-sanity list
```

`uv sync` builds manim, which needs ffmpeg, cairo, pango and LaTeX on the
machine (`brew install ffmpeg cairo pango` plus BasicTeX on macOS). If those
are missing and the user doesn't need to render scenes yet, use
`uv sync --no-default-groups`. The committed videos still show up.

Finish by offering `uv run presentation-sanity dev <first>` (it runs until
stopped) and pointing at `/presentation-sanity slides`.
