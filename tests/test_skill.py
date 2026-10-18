"""The agent skill ships with the tool and stays in step with it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from presentation_sanity.init_project import bundled_skill, skill_dir

REPO = Path(__file__).resolve().parent.parent


def frontmatter(text: str) -> dict:
    return yaml.safe_load(re.match(r"---\n(.*?)\n---", text, re.S).group(1))


def test_router_frontmatter_and_version() -> None:
    meta = frontmatter((skill_dir() / "SKILL.md").read_text())
    assert meta["name"] == "presentation-sanity"
    assert meta["user-invocable"] is True


def test_every_routed_mode_exists() -> None:
    router = (skill_dir() / "SKILL.md").read_text()
    routed = set(re.findall(r"`modes/([\w-]+)\.md`", router))
    files = {p.stem for p in (skill_dir() / "modes").glob("*.md")}
    assert routed == files, (routed ^ files)
    hint = frontmatter(router)["argument-hint"]
    assert set(hint.strip("[]").replace(" ", "").split("|")) == files - {"_shared"}


def test_modes_only_mention_real_commands() -> None:
    from presentation_sanity.cli import build_parser

    commands = set(build_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001
    skill = bundled_skill()
    text = "\n".join(skill[k].decode() for k in skill if k.endswith(".md"))
    used = set(re.findall(r"uv run (?:--with \S+ )?presentation-sanity ([a-z][a-z-]*)", text))
    assert used and used <= commands, used - commands


def test_plugin_manifest_matches_the_tool() -> None:
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "presentation-sanity"
    assert (REPO / "skills" / plugin["name"] / "SKILL.md").is_file()


def test_versions_match_the_tool() -> None:
    """Release step: the skill and plugin manifest are bumped with the tool."""
    from presentation_sanity import __version__

    meta = frontmatter((skill_dir() / "SKILL.md").read_text())
    assert meta["metadata"]["version"] == __version__, "bump skills/…/SKILL.md"
    plugin = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["version"] == __version__, "bump .claude-plugin/plugin.json"
