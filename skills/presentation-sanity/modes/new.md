# new: a presentation, or a new version of one

## Decide: new talk or new version?

- **New version** of an existing talk (another venue, a revised cut, the NIH
  review edition): fork it with `--from`, so it starts from the last one and
  remembers where it came from.
- **New talk** on the same project: start blank, without `--from`.

Run `uv run presentation-sanity list` first to see the ids that exist.

## Naming

Ids are paths under `presentations/`. Keep the versions of one talk side by
side in a grouping folder:

```
presentations/kickoff/v1/        id kickoff/v1
presentations/kickoff/nih/       id kickoff/nih
presentations/lab-meeting/       id lab-meeting
```

Presentations don't nest. If `kickoff` is itself a presentation (it has a
`slides.md`), a version can't go inside it. Ask whether to move it to
`kickoff/v1` first (a plain `git mv`), then fork beside it.

## Commands

```bash
uv run presentation-sanity new kickoff/nih --from kickoff/v1 --title "Kickoff (NIH review)"
uv run presentation-sanity new lab-meeting --title "Where the numbers come from"
```

`--from` copies the folder (skipping exports and Slidev scratch state), sets
the new title in the deck's headmatter, and records `from:` in the copy's
`manifest.yaml`. The landing page shows that lineage. Never copy a
presentation folder by hand.

## After

- Fill in `presentations/<id>/manifest.yaml` metadata if the user gave them:
  `date`, `venue`, and `authors` when they differ from the project's.
- Numbers that differ in this version get **new** variable keys (see
  `variables`). Don't edit the values the old version shows.
- `uv run presentation-sanity check <id>`, then offer `dev <id>:slides`.
