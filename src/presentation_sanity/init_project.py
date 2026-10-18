"""`presentation-sanity init`: a new project from the template, no git required.

The template ships inside the wheel as a snapshot of
presentation-sanity-template (`template/`, refreshed by
`scripts/sync_template.py`), so a project made by vX.Y.Z of the tool is the
template that vX.Y.Z was released with, pinned back to vX.Y.Z.
`--from gh:owner/repo[@ref]` takes a GitHub tarball instead — a lab's own fork,
downloaded over HTTPS with no git binary.

Everything happens in memory first: read the source into {path: bytes}, apply
the answers (names, titles, authors, the first presentation's folder), add the
agent skill, and only then compare against the destination. Nothing is written
when a file would be overwritten, unless `force`.

The template's own `init.py` is a shim over `init --in-place`, which applies
the same answers to a "Use this template" copy where it stands.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__
from .manifest import ManifestError
from .markdown_meta import with_headmatter_title
from .project import normalize_presentation_id

Files = dict[str, bytes]  # posix path relative to the project root → content

TEMPLATE_REPO = "yakaboskic/presentation-sanity-template"
EXAMPLE_DIR = "presentations/example"
# Files that belong to the template repo itself, never to a project made from
# it: the bootstrap shim, and the workflow that deploys the template's demo
# (Pages is opt-in per project — `presentation-sanity pages init`).
TEMPLATE_ONLY = ("init.py", ".github/workflows/pages.yml")

SKILL_NAME = "presentation-sanity"
# Claude Code reads .claude/skills/; Codex, Pi, Cursor and other agents read
# .agents/skills/. Two plain copies rather than a symlink, which Windows and
# zip downloads don't keep.
SKILL_DIRS = (".claude/skills", ".agents/skills")

_PKG = Path(__file__).parent
_SKIP_NAMES = {"__pycache__", ".DS_Store"}

# The dependency line that pins this tool, e.g.
#   "presentation-sanity[manim] @ git+https://github.com/yakaboskic/presentation-sanity.git@v0.3.0"
_PIN_RE = re.compile(
    r"(presentation-sanity(?:\[[^\]]*\])?\s*@\s*git\+https://github\.com/"
    r"yakaboskic/presentation-sanity(?:\.git)?@)v\d[^\"'\s#]*"
)
_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


class InitError(Exception):
    """A project could not be created as asked; nothing was written."""


# ── sources ──────────────────────────────────────────────────────────────────

def read_tree(root: Path) -> Files:
    files: Files = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not _SKIP_NAMES.intersection(rel.parts):
            files[rel.as_posix()] = path.read_bytes()
    return files


def bundled_template() -> tuple[Files, str]:
    """The template snapshot shipped with this release, and where it came from."""
    root = _PKG / "template"
    if not (root / "manifest.yaml").is_file():
        raise InitError(
            f"no template snapshot at {root} — run scripts/sync_template.py "
            "(or reinstall presentation-sanity)"
        )
    label = "presentation-sanity-template"
    source = _PKG / "template-source.json"
    if source.is_file():
        commit = json.loads(source.read_text()).get("commit", "")
        if commit:
            label += f"@{commit[:7]}"
    return read_tree(root), label


def skill_dir() -> Path:
    """The agent skill: packaged in the wheel, or `skills/` in a source checkout."""
    for candidate in (
        _PKG / "skills" / SKILL_NAME,
        _PKG.parent.parent / "skills" / SKILL_NAME,  # editable install
    ):
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise InitError("the presentation-sanity agent skill is missing from this install")


def bundled_skill() -> Files:
    return read_tree(skill_dir())


def parse_gh_spec(spec: str) -> tuple[str, str, str | None]:
    """`gh:owner/repo[@ref]` → (owner, repo, ref or None for the default branch)."""
    m = re.fullmatch(r"gh:([\w.-]+)/([\w.-]+?)(?:\.git)?(?:@(.+))?", spec.strip())
    if m is None:
        raise InitError(f"--from expects gh:owner/repo[@ref], got {spec!r}")
    return m.group(1), m.group(2), m.group(3)


def files_from_tarball(data: bytes) -> tuple[Files, str]:
    """A GitHub tarball's files, without its `owner-repo-sha/` top directory.

    Only regular files come out; links, devices and anything that would land
    outside the project are dropped rather than trusted.
    """
    files: Files = {}
    top = ""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        for member in tar.getmembers():
            parts = member.name.split("/")
            if not top and (member.isdir() or len(parts) > 1):
                top = parts[0]
            rel = "/".join(parts[1:])
            if not member.isfile() or not rel or parts[0] != top:
                continue
            if rel.startswith("/") or ".." in rel.split("/") or "\\" in rel:
                continue
            if _SKIP_NAMES.intersection(rel.split("/")):
                continue
            extracted = tar.extractfile(member)
            if extracted is not None:
                files[rel] = extracted.read()
    if not files:
        raise InitError("the downloaded tarball is empty")
    return files, top


def fetch_github(owner: str, repo: str, ref: str | None) -> tuple[Files, str]:
    """Download a repo snapshot from GitHub. GH_TOKEN/GITHUB_TOKEN reach private forks."""
    url = f"https://api.github.com/repos/{owner}/{repo}/tarball" + (f"/{ref}" if ref else "")
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as e:
        hint = " (private repo? set GH_TOKEN)" if e.code == 404 and not token else ""
        raise InitError(f"GitHub returned {e.code} for {owner}/{repo}{'@' + ref if ref else ''}{hint}") from e
    except urllib.error.URLError as e:
        raise InitError(f"could not reach GitHub: {e.reason}") from e
    files, top = files_from_tarball(data)
    sha = top.rsplit("-", 1)[-1]
    return files, f"gh:{owner}/{repo}@{ref or 'default'} ({sha[:7]})"


# ── answers ──────────────────────────────────────────────────────────────────

@dataclass
class Answers:
    slug: str
    title: str
    author: str
    email: str
    description: str
    first: str
    deck_title: str

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.slug):
            raise InitError(
                f"project name {self.slug!r} must be letters, digits, '-', '_' or '.', "
                "e.g. my-talks"
            )
        try:
            self.first = normalize_presentation_id(self.first)
        except ManifestError as e:
            raise InitError(f"first presentation: {e}") from None


# (field, prompt) in the order they are asked.
QUESTIONS = (
    ("slug", "Project name (kebab-case)"),
    ("title", "Project title (e.g. the program or grant name)"),
    ("author", "Author name"),
    ("email", "Author email"),
    ("description", "Short description"),
    ("first", "First presentation folder (e.g. kickoff, or kickoff/v1)"),
    ("deck_title", "First presentation's title"),
)


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower()
    return slug or "my-presentations"


def _git_config(key: str) -> str | None:
    if shutil.which("git") is None:
        return None
    try:
        out = subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _default(name: str, dest: Path, a: dict[str, str]) -> str:
    if name == "slug":
        return slugify(dest.resolve().name)
    if name == "title":
        return a["slug"].replace("-", " ").replace("_", " ").title()
    if name == "author":
        return _git_config("user.name") or "Your Name"
    if name == "email":
        return _git_config("user.email") or "you@example.com"
    if name == "description":
        return f"Presentations about {a['title']}"
    if name == "first":
        return "kickoff"
    if name == "deck_title":
        return a["title"]
    raise KeyError(name)


def gather_answers(
    dest: Path,
    given: dict[str, str | None],
    *,
    ask: Callable[[str, str], str] | None = None,
) -> Answers:
    """Fill every answer: from `given`, else `ask(prompt, default)`, else the default."""
    a: dict[str, str] = {}
    for name, prompt in QUESTIONS:
        value = given.get(name)
        if value is None or not str(value).strip():
            default = _default(name, dest, a)
            value = ask(prompt, default) if ask else default
        a[name] = str(value).strip()
    return Answers(**a)


# ── rewrites ─────────────────────────────────────────────────────────────────

def _q(value: str) -> str:
    """A double-quoted scalar, valid in both YAML and TOML."""
    return json.dumps(value, ensure_ascii=False)


def _set_scalar(text: str, key: str, value: str, *, item: bool = False) -> str:
    """Replace the first `key: …` (YAML) value, keeping indentation and comments."""
    lead = r"^(\s*(?:-\s+)?)" if item else r"^(\s*)"
    pattern = lead + re.escape(key) + r":[ \t]*(?:\"[^\"\n]*\"|'[^'\n]*'|[^#\n]*?)([ \t]*(?:#.*)?)$"
    return re.sub(
        pattern, lambda m: f"{m.group(1)}{key}: {_q(value)}{m.group(2)}", text, count=1, flags=re.M
    )


def _rewrite_pyproject(text: str, a: Answers, pin: str | None) -> str:
    text = re.sub(r'^name\s*=\s*"[^"]*"', lambda _: f"name = {_q(a.slug)}", text, count=1, flags=re.M)
    text = re.sub(
        r'^description\s*=\s*"[^"]*"', lambda _: f"description = {_q(a.description)}",
        text, count=1, flags=re.M,
    )
    if pin:
        text = _PIN_RE.sub(lambda m: f"{m.group(1)}v{pin}", text)
    return text


def _rewrite_package_json(text: str, a: Answers) -> str:
    return re.sub(r'("name"\s*:\s*)"[^"]*"', lambda m: m.group(1) + _q(a.slug), text, count=1)


def _rewrite_package_lock(text: str, a: Answers) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    data["name"] = a.slug
    root = data.get("packages", {}).get("")
    if isinstance(root, dict):
        root["name"] = a.slug
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"  # npm's own layout


def _rewrite_manifest(text: str, a: Answers) -> str:
    text = _set_scalar(text, "title", a.title)
    text = _set_scalar(text, "description", a.description)
    text = _set_scalar(text, "name", a.author, item=True)
    return _set_scalar(text, "email", a.email)


def render_readme(a: Answers) -> str:
    return f"""# {a.slug}

{a.description}

Built on [presentation-sanity](https://github.com/yakaboskic/presentation-sanity).
See [presentation-sanity-template](https://github.com/{TEMPLATE_REPO})
for documentation on presentations and versions, the manifest schema, layouts,
manim scenes and the provenance panel.

Every folder under `presentations/` with a `slides.md` (Slidev) and/or a
`blog.md` (VitePress) is a presentation. They all share `manifest.yaml`
(variables, scenes, figures, bibliography), `public/` and the `shared/`
components and layouts.

## Develop

```bash
uv sync                                       # Python deps (presentation-sanity + manim)
npm install                                   # Slidev + VitePress (+ links shared/)
uv run presentation-sanity list               # presentations in this project
uv run presentation-sanity dev {a.first}:slides  # Slidev hot-reload at :3030
uv run presentation-sanity dev {a.first}:blog    # VitePress hot-reload at :5173
uv run presentation-sanity new {a.first}-v2 --from {a.first}   # fork a new version
uv run presentation-sanity build              # everything → site/ (+ site/index.html)
uv run presentation-sanity preview            # serve site/ at :8000
```

Rendering manim scenes needs `ffmpeg`, `cairo`, `pango` and a LaTeX install.
Without them, `uv sync --no-default-groups` skips manim and `build` uses the
videos already committed in `public/manim/`.

An agent skill lives in `.claude/skills/presentation-sanity/` (Claude Code:
`/presentation-sanity`) and `.agents/skills/presentation-sanity/` (other
agents). `uv run presentation-sanity skills --force` refreshes it after an
upgrade.

presentation-sanity is pinned to a release tag in `pyproject.toml`. To upgrade,
change the tag to a newer [release](https://github.com/yakaboskic/presentation-sanity/releases)
and run `uv lock && uv sync`.
"""


def apply_answers(files: Files, a: Answers, *, pin: str | None = None) -> Files:
    """The template with this project's names, authors and first presentation.

    `pin` rewrites the presentation-sanity dependency to that release, so a
    project starts on the tool that created it.
    """
    out: Files = {}
    first_dir = f"presentations/{a.first}"
    for rel, data in files.items():
        if rel in TEMPLATE_ONLY:
            continue
        if rel.startswith(EXAMPLE_DIR + "/") and a.first != "example":
            rel = first_dir + rel[len(EXAMPLE_DIR):]
        out[rel] = data

    def edit(rel: str, fn: Callable[[str], str]) -> None:
        if rel in out:
            out[rel] = fn(out[rel].decode("utf-8")).encode("utf-8")

    edit("pyproject.toml", lambda t: _rewrite_pyproject(t, a, pin))
    edit("package.json", lambda t: _rewrite_package_json(t, a))
    edit("package-lock.json", lambda t: _rewrite_package_lock(t, a))
    edit("manifest.yaml", lambda t: _rewrite_manifest(t, a))
    edit(f"{first_dir}/slides.md", lambda t: with_headmatter_title(t, a.deck_title))
    out["README.md"] = render_readme(a).encode("utf-8")
    return out


def with_skill(files: Files, skill: Files | None = None) -> Files:
    """`files` plus the agent skill in every agent's skills folder."""
    skill = bundled_skill() if skill is None else skill
    out = dict(files)
    for base in SKILL_DIRS:
        for rel, data in skill.items():
            out[f"{base}/{SKILL_NAME}/{rel}"] = data
    return out


# ── writing ──────────────────────────────────────────────────────────────────

@dataclass
class Plan:
    dest: Path
    create: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def plan(files: Files, dest: Path) -> Plan:
    """Sort every file into: new, already identical, or would overwrite."""
    p = Plan(dest)
    for rel, data in sorted(files.items()):
        target = dest / rel
        if not target.exists():
            p.create.append(rel)
        elif target.is_file() and target.read_bytes() == data:
            p.unchanged.append(rel)
        else:
            p.conflicts.append(rel)
    return p


def conflict_error(p: Plan, *, limit: int = 20) -> InitError:
    shown = "\n".join(f"    {rel}" for rel in p.conflicts[:limit])
    more = f"\n    … and {len(p.conflicts) - limit} more" if len(p.conflicts) > limit else ""
    return InitError(
        f"{len(p.conflicts)} file(s) already exist in {p.dest} and differ:\n{shown}{more}\n"
        "  nothing was written. Move them aside, or pass --force to overwrite them."
    )


def write(files: Files, dest: Path, rels: list[str]) -> None:
    for rel in rels:
        target = dest / rel
        if target.is_dir():
            raise InitError(f"{target} is a directory; expected a file")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[rel])


def git_init(dest: Path, message: str) -> str:
    """`git init` + first commit. Returns a line for the report."""
    if shutil.which("git") is None:
        raise InitError("--git needs git on PATH")
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=dest, capture_output=True, text=True
    )
    if inside.returncode == 0 and inside.stdout.strip() == "true":
        return "already inside a git repository — left it alone (commit when ready)"
    run = lambda *cmd: subprocess.run(["git", *cmd], cwd=dest, capture_output=True, text=True)  # noqa: E731
    result = run("init", "-b", "main")
    if result.returncode != 0:
        result = run("init")  # git < 2.28 has no -b
    if result.returncode != 0:
        raise InitError(f"git init failed: {result.stderr.strip()}")
    run("add", "-A")
    commit = run("commit", "-q", "-m", message)
    if commit.returncode != 0:
        return f"git repository created; the first commit failed: {commit.stderr.strip()}"
    return "git repository created with a first commit"


@dataclass
class Result:
    dest: Path
    source: str
    answers: Answers
    written: list[str]
    overwritten: list[str]
    removed: list[str] = field(default_factory=list)
    git: str | None = None


def create_project(
    dest: Path,
    answers: Answers,
    *,
    source: tuple[Files, str] | None = None,
    skills: bool = True,
    force: bool = False,
    git: bool = False,
) -> Result:
    """Copy the template (or `source`) into `dest` with `answers` applied.

    `dest` may be missing, empty, or an existing folder to knit into: files
    already there are kept, and any the project would replace are listed and
    refused unless `force`.
    """
    bundled = source is None
    files, label = bundled_template() if bundled else source
    release = re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None
    files = apply_answers(files, answers, pin=__version__ if bundled and release else None)
    if skills:
        files = with_skill(files)

    if dest.exists() and not dest.is_dir():
        raise InitError(f"{dest} exists and is not a directory")
    p = plan(files, dest)
    if p.conflicts and not force:
        raise conflict_error(p)
    dest.mkdir(parents=True, exist_ok=True)
    write(files, dest, p.create + p.conflicts)
    result = Result(dest, label, answers, written=p.create, overwritten=p.conflicts)
    if git:
        result.git = git_init(dest, f"Start {answers.slug} from {label}")
    return result


def init_in_place(root: Path, answers: Answers, *, skills: bool = True, force: bool = False) -> Result:
    """Apply `answers` to a template copy where it stands ("Use this template").

    The same rewrites as `create_project`; the example presentation moves to
    the first presentation's folder and the template-only files are removed.
    """
    if not (root / "init.py").is_file() or not (root / "manifest.yaml").is_file():
        raise InitError(
            f"{root} doesn't look like a fresh template copy (no init.py next to "
            "manifest.yaml) — it may already be initialized"
        )
    names = ["pyproject.toml", "package.json", "package-lock.json", "manifest.yaml", "README.md"]
    current: Files = {n: (root / n).read_bytes() for n in names if (root / n).is_file()}
    example = root / EXAMPLE_DIR
    if example.is_dir():
        current.update({f"{EXAMPLE_DIR}/{k}": v for k, v in read_tree(example).items()})
    if answers.first != "example" and (root / "presentations" / answers.first).exists():
        raise InitError(f"presentations/{answers.first} already exists")

    files = apply_answers(current, answers)
    if skills:
        files = with_skill(files)
    p = plan(files, root)
    # Rewriting the template's own files is the point; only skill files a user
    # already has (and changed) count as conflicts here.
    conflicts = [rel for rel in p.conflicts if rel.startswith(SKILL_DIRS)]
    if conflicts and not force:
        p.conflicts = conflicts
        raise conflict_error(p)
    write(files, root, p.create + p.conflicts)

    removed = [rel for rel in TEMPLATE_ONLY if (root / rel).is_file()]
    stale = [rel for rel in current if rel.startswith(EXAMPLE_DIR + "/") and rel not in files]
    if stale:
        removed.append(EXAMPLE_DIR + "/")
    for rel in [*TEMPLATE_ONLY, *stale]:
        (root / rel).unlink(missing_ok=True)
        _prune_empty_parents(root / rel, root)
    return Result(
        root, "this template copy", answers,
        written=p.create, overwritten=p.conflicts, removed=removed,
    )


def _prune_empty_parents(path: Path, root: Path) -> None:
    """Remove the folders above a deleted file that it leaves empty, up to `root`."""
    d = path.parent
    while d != root and d.is_dir() and not any(d.iterdir()):
        d.rmdir()
        d = d.parent


def install_skill(root: Path, *, force: bool = False) -> Plan:
    """(Re)install the agent skill into an existing project."""
    files = with_skill({})
    p = plan(files, root)
    if p.conflicts and not force:
        raise conflict_error(p)
    write(files, root, p.create + p.conflicts)
    return p
