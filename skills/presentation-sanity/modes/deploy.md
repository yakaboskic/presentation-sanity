# deploy: GitHub Pages, or any static host

## First: say this, and wait for a yes

> A GitHub Pages site is **public**: anyone with the link can see it, even
> when the repository is private. Every presentation in `site/` gets
> published, including drafts, plus every number and its provenance (file
> paths and commands included). OK to publish?

Don't go on without an explicit yes. If some presentations shouldn't be
public, stop and work that out with the user first.

## GitHub Pages

```bash
uv run presentation-sanity pages init
```

This writes `.github/workflows/pages.yml`. On every push to `main` it installs
the project without manim (`uv sync --no-default-groups`), runs `npm ci`,
builds with `--skip-manim --skip-figures` and the right `--base`, and deploys
`site/`. The runner never renders. It ships the videos and figures committed
in `public/`.

Then work through what it printed:

- `!` notes: rendered videos or figures missing or gitignored, a missing
  `uv.lock` or `package-lock.json`. Render locally (`build`), and with the
  user's OK remove the `public/manim/` lines from `.gitignore`. Then commit
  `public/`.
- If it refuses because `[manim]` is in the main dependencies: show the user
  the migration it printed (move the extra into a `manim` dependency group),
  apply it with their OK, run `uv lock`.
- **Turning Pages on is a repository setting. Ask first.** Then either the
  user does it (Settings → Pages → Source: GitHub Actions), or with their OK:
  `gh api -X POST repos/OWNER/REPO/pages -f build_type=workflow` (`-X PUT` if
  Pages is already on with another source).
- **Pushing is the user's call too.** Commit the workflow, `public/`, and the
  lock files, then ask before `git push`.

The site appears at `https://OWNER.github.io/REPO/` (or the custom domain).
Each presentation is at `<id>/slides/` and `<id>/blog/`, with an index at the
root. Use `--branch` when the deploy branch isn't `main`, and `--only-repo
OWNER/NAME` to stop forks from deploying.

## Any other static host

```bash
uv run presentation-sanity build --base /prefix/     # the URL path site/ is served from
```

Then upload `site/` (`aws s3 sync site/ s3://…`, `rclone`, Netlify drop). Decks
use hash routing and blogs use real `.html` routes, so no rewrite rules are
needed. The same public-by-default warning applies. Ask before uploading.
