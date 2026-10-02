"""Projects: one repo, many presentations.

A *project* is a repo root holding `manifest.yaml` and a `presentations/`
directory. Every folder below `presentations/` that contains an output's entry
document (`slides.md`, `blog.md`, …) is a *presentation*, and its path relative
to `presentations/` is its id. Folders without one only group presentations —
which is all a "version" is:

    presentations/decode-pigean/cfde-2026/slides.md    → decode-pigean/cfde-2026
    presentations/decode-pigean/eurac-2026/slides.md   → decode-pigean/eurac-2026

Everything a presentation's subfolders hold belongs to it; presentations are
not discovered inside other presentations.

Shared inputs — variables, scenes, figures, bibliography, `public/` and the
`shared/` Vue layer — live at the project root and are built once. A
presentation's optional `manifest.yaml` only describes it (`metadata`) and
tunes its outputs (`outputs`), merged over the project's `outputs:` defaults.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .manifest import (
    PRESENTATIONS_DIR,
    Manifest,
    ManifestError,
    Output,
    check_single_vitepress,
    deep_merge,
    load_manifest,
    load_presentation_overrides,
)
from .markdown_meta import read_headmatter

SITE_DIR = "site"

# Folders that are never presentations (or groups of them).
_SKIP_DIRS = {"node_modules", "site", "exports", "public"}

# Project metadata a presentation does not inherit: it names the project, not
# the talk. Everything else (authors, …) carries over unless overridden.
_PROJECT_ONLY_METADATA = ("title", "description")


@dataclass
class Presentation:
    id: str
    dir: Path
    metadata: dict[str, Any]
    outputs: dict[str, Output]

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.id)

    @property
    def group(self) -> str:
        """Id of the grouping folder ('' at the top level)."""
        return self.id.rpartition("/")[0]


@dataclass
class Project:
    root: Path
    manifest: Manifest
    presentations: dict[str, Presentation] = field(default_factory=dict)

    @property
    def presentations_dir(self) -> Path:
        return self.root / PRESENTATIONS_DIR

    @property
    def site_dir(self) -> Path:
        return self.root / SITE_DIR

    @property
    def title(self) -> str:
        return self.manifest.title


def find_project_root(start: Path) -> Path | None:
    """Nearest directory at or above `start` holding manifest.yaml + presentations/."""
    start = start.resolve()
    for d in (start, *start.parents):
        if (d / "manifest.yaml").is_file() and (d / PRESENTATIONS_DIR).is_dir():
            return d
    return None


def load_project(root: Path) -> Project:
    manifest = load_manifest(root)
    if not manifest.project_mode:
        raise ManifestError(
            f"{root} is a single-deck repo (no {PRESENTATIONS_DIR}/ directory). "
            f"Create {PRESENTATIONS_DIR}/ and move each deck into its own folder "
            "to use projects."
        )
    project = Project(root=root, manifest=manifest)
    project.presentations = discover_presentations(manifest)
    return project


def _entry_names(manifest: Manifest) -> set[str]:
    return {Output.from_raw(k, v).entry for k, v in manifest.output_defaults.items()}


def discover_presentations(manifest: Manifest) -> dict[str, Presentation]:
    """Every presentation under `presentations/`, keyed by id, in path order."""
    base = manifest.root / PRESENTATIONS_DIR
    entries = _entry_names(manifest)
    found: dict[str, Presentation] = {}

    def walk(d: Path) -> None:
        for child in sorted(p for p in d.iterdir() if p.is_dir()):
            if child.name.startswith(".") or child.name in _SKIP_DIRS:
                continue
            is_presentation = (child / "manifest.yaml").is_file() or any(
                (child / e).is_file() for e in entries
            )
            if not is_presentation:
                walk(child)  # a grouping folder, e.g. the versions of one talk
                continue
            pid = child.relative_to(base).as_posix()
            if ":" in pid:
                raise ManifestError(
                    f"presentation folder {pid!r} contains ':' — that character "
                    "separates a presentation from an output on the command line"
                )
            found[pid] = resolve_presentation(manifest, child, pid)

    if base.is_dir():
        walk(base)
    return found


def resolve_presentation(manifest: Manifest, pres_dir: Path, pid: str) -> Presentation:
    """Merge project defaults with a presentation's overrides into its outputs."""
    overrides = load_presentation_overrides(pres_dir)
    root = manifest.root

    outputs: dict[str, Output] = {}
    keys = list(manifest.output_defaults) + [
        k for k in overrides["outputs"] if k not in manifest.output_defaults
    ]
    for key in keys:
        override = overrides["outputs"].get(key)
        if override is False:  # this presentation opts out of a project output
            continue
        if override is not None and not isinstance(override, dict):
            raise ManifestError(
                f"{pres_dir / 'manifest.yaml'}: output {key!r} must be a mapping or false"
            )
        raw = deep_merge(manifest.output_defaults.get(key, {}), override or {})
        out = raw.get("out")
        output = Output.from_raw(key, raw)
        entry = pres_dir / output.entry
        if not entry.is_file():
            continue  # e.g. a deck with no blog.md simply has no blog
        # Absolute paths: Slidev resolves --out against the deck folder, and the
        # orchestrator runs every engine from the project root.
        output.entry = str(entry)
        output.out = str(root / out) if out else str(root / SITE_DIR / pid / key)
        outputs[key] = output

    check_single_vitepress(outputs, f"presentation {pid!r}")

    metadata = {
        k: v for k, v in manifest.metadata.items() if k not in _PROJECT_ONLY_METADATA
    }
    title = _entry_title(outputs)
    if title:
        metadata["title"] = title
    metadata = deep_merge(metadata, overrides["metadata"])
    return Presentation(id=pid, dir=pres_dir, metadata=metadata, outputs=outputs)


def _entry_title(outputs: dict[str, Output]) -> str | None:
    """The deck's headmatter `title`, else the post's frontmatter `title`."""
    ordered = sorted(outputs.values(), key=lambda o: o.engine != "slidev")
    for output in ordered:
        title = read_headmatter(Path(output.entry)).get("title")
        if title:
            return str(title)
    return None


# ── selecting presentations and outputs from the command line ───────────────

def presentation_for_path(project: Project, path: Path) -> Presentation | None:
    """The presentation whose folder is `path` or contains it."""
    path = path.resolve()
    for p in project.presentations.values():
        if path == p.dir or p.dir in path.parents:
            return p
    return None


def _ids(project: Project) -> str:
    return ", ".join(project.presentations) or "(none yet)"


def _current_or_only(project: Project, cwd: Path, *, required: bool = True) -> Presentation | None:
    here = presentation_for_path(project, cwd)
    if here is not None:
        return here
    if len(project.presentations) == 1:
        return next(iter(project.presentations.values()))
    if not required:
        return None
    if not project.presentations:
        raise ManifestError(
            "this project has no presentations yet — create one with "
            "`presentation-sanity new <name>`"
        )
    raise ManifestError(
        f"several presentations to choose from — name one: {_ids(project)}"
    )


def _lookup(project: Project, token: str, cwd: Path) -> list[Presentation]:
    """Resolve an id, a grouping folder (every presentation beneath it), or a path."""
    token = token.strip().rstrip("/")
    candidate = (cwd / token).resolve() if token else None
    if candidate is not None and candidate.is_dir():
        here = presentation_for_path(project, candidate)
        if here is not None:
            return [here]
        try:
            token = candidate.relative_to(project.presentations_dir).as_posix()
        except ValueError:
            pass
    prefix = PRESENTATIONS_DIR + "/"
    if token.startswith(prefix):
        token = token[len(prefix):]
    if token in project.presentations:
        return [project.presentations[token]]
    if token in ("", "."):
        return list(project.presentations.values())
    group = [p for pid, p in project.presentations.items() if pid.startswith(token + "/")]
    if group:
        return group
    raise ManifestError(f"no presentation {token!r}. This project has: {_ids(project)}")


def _split(selector: str, project: Project, cwd: Path) -> tuple[list[Presentation], str]:
    """`id[:output]` → (presentations, output key or '')."""
    token, _, key = selector.partition(":")
    if not token:
        return [_current_or_only(project, cwd)], key
    try:
        return _lookup(project, token, cwd), key
    except ManifestError:
        # A bare output key — `build blog` inside a presentation, or in a
        # project with a single presentation — keeps the single-deck habit.
        current = _current_or_only(project, cwd, required=False)
        if not key and current is not None and token in current.outputs:
            return [current], token
        raise


def select(
    project: Project, selectors: list[str] | None, cwd: Path
) -> list[tuple[Presentation, Output]]:
    """Every (presentation, output) pair a `build` invocation names.

    No selector means the presentation the cwd is inside, or else all of them.
    """
    if not selectors:
        here = presentation_for_path(project, cwd)
        chosen = [here] if here is not None else list(project.presentations.values())
        return [(p, o) for p in chosen for o in p.outputs.values()]

    pairs: list[tuple[Presentation, Output]] = []
    for selector in selectors:
        presentations, key = _split(selector, project, cwd)
        matched = False
        for p in presentations:
            if not key:
                pairs.extend((p, o) for o in p.outputs.values())
                matched = matched or bool(p.outputs)
            elif key in p.outputs:
                pairs.append((p, p.outputs[key]))
                matched = True
        if key and not matched:
            names = ", ".join(p.id for p in presentations)
            raise ManifestError(f"no {key!r} output in: {names}")

    seen: set[tuple[str, str]] = set()
    unique = []
    for p, o in pairs:
        if (p.id, o.key) not in seen:
            seen.add((p.id, o.key))
            unique.append((p, o))
    return unique


def pick_one(
    project: Project, selector: str | None, cwd: Path, *, engine: str | None = None
) -> tuple[Presentation, Output]:
    """The single output a verb like `dev`, `preview` or `export` acts on.

    Lists the choices rather than guessing — silently developing the wrong
    deck is worse than one extra keystroke.
    """
    if selector is None:
        presentation, key = _current_or_only(project, cwd), ""
    else:
        presentations, key = _split(selector, project, cwd)
        if len(presentations) != 1:
            raise ManifestError(
                f"{selector!r} matches several presentations — name one: "
                + ", ".join(p.id for p in presentations)
            )
        presentation = presentations[0]
    assert presentation is not None

    if key:
        if key not in presentation.outputs:
            raise ManifestError(
                f"presentation {presentation.id!r} has no {key!r} output "
                f"(it has: {', '.join(presentation.outputs) or 'none'})"
            )
        output = presentation.outputs[key]
        if engine is not None and output.engine != engine:
            raise ManifestError(
                f"{presentation.id}:{key} uses engine {output.engine!r}, "
                f"but this command needs {engine!r}"
            )
        return presentation, output

    pool = {
        k: o for k, o in presentation.outputs.items() if engine is None or o.engine == engine
    }
    if len(pool) == 1:
        return presentation, next(iter(pool.values()))
    if not pool:
        need = f"a {engine}" if engine else "an"
        raise ManifestError(f"presentation {presentation.id!r} has no {need} output")
    first = next(iter(pool))
    raise ManifestError(
        f"{presentation.id!r} has several outputs ({', '.join(pool)}) — name one, "
        f"e.g. `{presentation.id}:{first}`"
    )


# ── creating presentations ──────────────────────────────────────────────────

# Never copied when forking a presentation: build products and Slidev's
# per-deck scratch state.
_COPY_SKIP_TOP = {"exports", ".slidev", "index.html", "dist"}
_COPY_SKIP_ANY = {"node_modules", ".DS_Store"}

STARTER_SLIDES = """\
---
title: {title}
# Hash routing works on any static host (no SPA fallback needed).
routerMode: hash
---

# {title}
"""


def _validate_new_id(project: Project, new_id: str) -> str:
    new_id = new_id.strip().strip("/")
    if new_id.startswith(PRESENTATIONS_DIR + "/"):
        new_id = new_id[len(PRESENTATIONS_DIR) + 1:]
    parts = new_id.split("/")
    if not new_id or ":" in new_id or any(p in ("", ".", "..") for p in parts):
        raise ManifestError(f"invalid presentation id {new_id!r}")
    if new_id in project.presentations:
        raise ManifestError(f"presentation {new_id!r} already exists")
    for pid in project.presentations:
        if new_id.startswith(pid + "/"):
            raise ManifestError(
                f"{new_id!r} would sit inside presentation {pid!r}; presentations "
                "can't nest — put versions side by side under a grouping folder"
            )
        if pid.startswith(new_id + "/"):
            raise ManifestError(
                f"{new_id!r} is already a grouping folder (it holds {pid!r})"
            )
    dest = project.presentations_dir / new_id
    if dest.exists() and any(dest.iterdir()):
        raise ManifestError(f"{dest} already exists and is not empty")
    return new_id


def _set_headmatter_title(path: Path, title: str) -> None:
    """Set `title:` in the first frontmatter block, keeping comments intact."""
    text = path.read_text()
    m = re.match(r"(\s*---\n)(.*?)(\n---)", text, re.S)
    line = f"title: {json.dumps(title, ensure_ascii=False)}"
    if m is None:
        path.write_text(f"---\n{line}\n---\n\n{text}")
        return
    body = m.group(2)
    if re.search(r"^title:.*$", body, re.M):
        body = re.sub(r"^title:.*$", lambda _: line, body, count=1, flags=re.M)
    else:
        body = f"{line}\n{body}"
    path.write_text(text[: m.start(2)] + body + text[m.end(2):])


def _record_lineage(pres_dir: Path, from_id: str, title: str | None) -> None:
    """Note in the copy's manifest.yaml which presentation it was forked from."""
    path = pres_dir / "manifest.yaml"
    text = path.read_text() if path.is_file() else ""
    data = (yaml.safe_load(text) or {}) if text else {}
    metadata = data.get("metadata") if isinstance(data, dict) else None

    def quoted(v: str) -> str:
        return json.dumps(v, ensure_ascii=False)  # a valid YAML scalar, always

    def replace(text: str, key: str, value: str) -> str:
        return re.sub(
            rf"^(\s+){key}:.*$", lambda m: f"{m.group(1)}{key}: {quoted(value)}",
            text, count=1, flags=re.M,
        )

    if not isinstance(metadata, dict):
        header = f"metadata:\n  from: {quoted(from_id)}\n"
        path.write_text(header + ("\n" + text if text else ""))
        return
    if "from" in metadata:
        text = replace(text, "from", from_id)
    else:
        text = re.sub(
            r"^metadata:\s*$", lambda m: f"{m.group(0)}\n  from: {quoted(from_id)}",
            text, count=1, flags=re.M,
        )
    # A copied title would shadow the new headmatter title on the index page.
    if title and "title" in metadata:
        text = replace(text, "title", title)
    path.write_text(text)


def create_presentation(
    project: Project, new_id: str, *, from_id: str | None = None, title: str | None = None
) -> Path:
    """Scaffold `presentations/<new_id>/`, optionally forked from another one."""
    new_id = _validate_new_id(project, new_id)
    dest = project.presentations_dir / new_id

    if from_id is None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "slides.md").write_text(STARTER_SLIDES.format(title=title or new_id))
        return dest

    sources = _lookup(project, from_id, project.root)
    if len(sources) != 1:
        raise ManifestError(f"--from {from_id!r} must name exactly one presentation")
    source = sources[0]

    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped = {n for n in names if n in _COPY_SKIP_ANY}
        if Path(directory) == source.dir:
            skipped |= {n for n in names if n in _COPY_SKIP_TOP}
        return skipped

    shutil.copytree(source.dir, dest, ignore=ignore, dirs_exist_ok=True)
    if title:
        for output in source.outputs.values():
            copied = dest / Path(output.entry).relative_to(source.dir)
            if copied.is_file():
                _set_headmatter_title(copied, title)
    _record_lineage(dest, source.id, title)
    return dest
