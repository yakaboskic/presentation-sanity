# variables: numbers with provenance

Every number a talk claims is declared once in ROOT `manifest.yaml` and
rendered with `<DataValue var="key" />`. Clicking it opens a panel showing
`inputs → command → value`.

## Declare

```yaml
variables:
  num_samples:
    value: 12453
    format: ","                         # Python format spec: , .2e .3f .1%
    description: "Total samples after QC filtering"
    source: "data/results.csv"          # one input file, or…
    # data: ["data/results.csv", "data/cohort.tsv"]   # several (wins over source)
    command: "python scripts/qc.py"     # how the value was produced
    updated: "2026-04-29"
```

## Rules

- **Never invent provenance.** If the user gives a number without saying
  where it came from, ask for the file, the command, and when it was
  computed. If they don't know, leave those fields out rather than guessing.
  An empty field is honest; a plausible one isn't.
- `source`, `data` and `command` are **informational**. The build never runs
  them. Don't run `command:` yourself unless the user asks you to recompute.
- Set `updated:` to the date the value was produced, not the date you typed
  it, when the user knows it.
- **Changing a number:** if an older version of a talk showed the old value,
  don't edit it. Add a new key (`num_samples_2026q3`) and point the new
  version's `<DataValue>` at it. Edit in place only when the old value was
  simply wrong and the user says so.
- Keys are project-wide. Pick names that will still make sense next year.
- Never type the number into the prose next to the component, and never
  hard-code a number a variable already holds.

## Check

`uv run presentation-sanity check` flags every `<DataValue var="…">` whose key
isn't declared, and suggests the closest key. In the browser, a missing key
renders as `??key??` instead of a number.
