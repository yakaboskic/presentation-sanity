"""Parse and validate the deck's manifest.yaml.

The manifest is the single source of configuration per deck. The Python
build orchestrator reads it; the Slidev side never touches it directly —
it only consumes the JSON files this package writes.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Variable:
    """One entry under `variables:` in the manifest."""

    key: str
    value: Any
    format: str | None = None
    description: str | None = None
    source: str | None = None
    data: list[str] | None = None  # multi-input list (overrides `source` in graph)
    command: str | None = None
    updated: str | None = None

    @classmethod
    def from_raw(cls, key: str, raw: Any) -> "Variable":
        if not isinstance(raw, dict):
            # Shorthand: `KEY: 1234` — bare value, no provenance.
            return cls(key=key, value=raw)
        data = raw.get("data")
        if data is not None and not isinstance(data, list):
            raise ManifestError(
                f"variable {key!r}: `data` must be a list of strings"
            )
        return cls(
            key=key,
            value=raw.get("value"),
            format=raw.get("format"),
            description=raw.get("description"),
            source=raw.get("source"),
            data=data,
            command=raw.get("command"),
            updated=raw.get("updated"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value}
        for k in ("format", "description", "source", "data", "command", "updated"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out


@dataclass
class Scene:
    """One entry under `scenes:` in the manifest."""

    key: str
    source: Path
    class_name: str
    quality: str = "h"
    format: str = "webm"

    @classmethod
    def from_raw(cls, key: str, raw: dict[str, Any], root: Path) -> "Scene":
        if "source" not in raw:
            raise ManifestError(f"scene {key!r} missing required 'source' field")
        if "class" not in raw:
            raise ManifestError(f"scene {key!r} missing required 'class' field")
        return cls(
            key=key,
            source=(root / raw["source"]).resolve(),
            class_name=raw["class"],
            quality=raw.get("quality", "h"),
            format=raw.get("format", "webm"),
        )


@dataclass
class Manifest:
    root: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Variable] = field(default_factory=dict)
    scenes: dict[str, Scene] = field(default_factory=dict)


class ManifestError(Exception):
    pass


def load_manifest(root: Path) -> Manifest:
    """Read manifest.yaml from `root` and validate.

    `root` is the deck directory — i.e., the dir containing manifest.yaml,
    slides.md, package.json. Typically the user's CWD when they run
    `presentation-sanity build`.
    """
    path = root / "manifest.yaml"
    if not path.is_file():
        raise ManifestError(f"manifest.yaml not found at {path}")

    raw = yaml.safe_load(path.read_text()) or {}

    variables = {
        key: Variable.from_raw(key, val)
        for key, val in (raw.get("variables") or {}).items()
    }

    scenes_raw = raw.get("scenes") or {}
    scenes = {
        key: Scene.from_raw(key, val, root) for key, val in scenes_raw.items()
    }
    for scene in scenes.values():
        if not scene.source.is_file():
            print(
                f"  warning: scene {scene.key!r} source {scene.source} not found",
                file=sys.stderr,
            )

    return Manifest(
        root=root,
        metadata=raw.get("metadata") or {},
        variables=variables,
        scenes=scenes,
    )
