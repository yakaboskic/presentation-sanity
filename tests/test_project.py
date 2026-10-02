from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from presentation_sanity.manifest import ManifestError, load_manifest
from presentation_sanity.markdown_meta import read_headmatter
from presentation_sanity.project import (
    create_presentation,
    find_project_root,
    load_project,
    pick_one,
    select,
)

from .conftest import PROJECT_MANIFEST, deck


# ── discovery ────────────────────────────────────────────────────────────────

def test_discovers_presentations_by_path(project: Path) -> None:
    proj = load_project(project)
    assert list(proj.presentations) == ["solo", "talk/v1", "talk/v2"]
    assert proj.presentations["talk/v2"].group == "talk"
    assert proj.presentations["solo"].group == ""


def test_skips_build_and_hidden_dirs(project: Path, write) -> None:
    write(
        {
            "presentations/node_modules/x/slides.md": deck("no"),
            "presentations/.hidden/slides.md": deck("no"),
            "presentations/site/slides.md": deck("no"),
        }
    )
    assert "node_modules/x" not in load_project(project).presentations
    assert set(load_project(project).presentations) == {"solo", "talk/v1", "talk/v2"}


def test_presentations_do_not_nest(project: Path, write) -> None:
    # A deck's own subfolders belong to it — they are not discovered.
    write({"presentations/solo/archive/slides.md": deck("old section")})
    assert "solo/archive" not in load_project(project).presentations


def test_find_project_root_walks_up(project: Path) -> None:
    inner = project / "presentations" / "talk" / "v1"
    assert find_project_root(inner) == project
    assert find_project_root(project) == project


def test_single_subject_repo_is_not_a_project(write) -> None:
    root = write({"manifest.yaml": "metadata: {title: x}\n", "slides.md": deck("x")})
    assert find_project_root(root) is None
    manifest = load_manifest(root)
    assert not manifest.project_mode
    assert list(manifest.outputs) == ["slides"]
    assert manifest.outputs["slides"].out == "site"  # unchanged legacy default
    with pytest.raises(ManifestError, match="single-deck"):
        load_project(root)


# ── outputs ──────────────────────────────────────────────────────────────────

def test_outputs_follow_the_entry_files(project: Path) -> None:
    proj = load_project(project)
    assert set(proj.presentations["talk/v1"].outputs) == {"slides", "blog"}
    assert set(proj.presentations["talk/v2"].outputs) == {"slides"}


def test_outputs_are_absolute_and_land_under_site(project: Path) -> None:
    out = load_project(project).presentations["talk/v1"].outputs["blog"]
    assert out.entry == str(project / "presentations/talk/v1/blog.md")
    assert out.out == str(project / "site/talk/v1/blog")


def test_project_outputs_are_defaults(write, project: Path) -> None:
    write(
        {
            "manifest.yaml": PROJECT_MANIFEST
            + "outputs:\n  slides:\n    theme: seriph\n  blog:\n    nav: [{text: Home}]\n",
            "presentations/solo/manifest.yaml": (
                "outputs:\n  slides:\n    base: /custom/\n    out: site/elsewhere\n"
            ),
        }
    )
    proj = load_project(project)
    solo = proj.presentations["solo"].outputs["slides"]
    assert solo.extra == {"theme": "seriph", "base": "/custom/"}
    assert solo.out == str(project / "site/elsewhere")
    assert proj.presentations["talk/v1"].outputs["blog"].extra["nav"] == [{"text": "Home"}]


def test_project_level_out_is_rejected(write, project: Path) -> None:
    write({"manifest.yaml": PROJECT_MANIFEST + "outputs:\n  slides:\n    out: site/x\n"})
    with pytest.raises(ManifestError, match="out:"):
        load_manifest(project)


def test_outputs_can_be_switched_off(write, project: Path) -> None:
    write({"presentations/talk/v1/manifest.yaml": "outputs:\n  blog: false\n"})
    assert set(load_project(project).presentations["talk/v1"].outputs) == {"slides"}
    write({"manifest.yaml": PROJECT_MANIFEST + "outputs:\n  blog: false\n"})
    assert "blog" not in load_project(project).presentations["talk/v1"].outputs


def test_custom_project_output(write, project: Path) -> None:
    write(
        {
            "manifest.yaml": PROJECT_MANIFEST
            + "outputs:\n  handout:\n    engine: slidev\n    entry: handout.md\n",
            "presentations/solo/handout.md": deck("Handout"),
        }
    )
    proj = load_project(project)
    assert set(proj.presentations["solo"].outputs) == {"slides", "handout"}
    assert "handout" not in proj.presentations["talk/v2"].outputs


# ── per-presentation manifest ────────────────────────────────────────────────

def test_metadata_merge(project: Path) -> None:
    proj = load_project(project)
    solo = proj.presentations["solo"].metadata
    assert solo["title"] == "Solo"  # from the deck's headmatter, not the project
    assert solo["authors"] == [{"name": "Ada"}]  # inherited
    assert solo["venue"] == "ASHG"
    assert proj.title == "Pigean"


def test_presentation_metadata_overrides_headmatter(write, project: Path) -> None:
    write({"presentations/solo/manifest.yaml": "metadata:\n  title: Renamed\n"})
    assert load_project(project).presentations["solo"].title == "Renamed"


@pytest.mark.parametrize("key", ["variables", "scenes", "figures", "bibliography", "math"])
def test_shared_inputs_belong_to_the_project(write, project: Path, key: str) -> None:
    write({"presentations/solo/manifest.yaml": f"{key}: {{}}\n"})
    with pytest.raises(ManifestError, match="project manifest"):
        load_project(project)


def test_one_vitepress_output_per_presentation(write, project: Path) -> None:
    write(
        {
            "presentations/solo/manifest.yaml": (
                "outputs:\n  post:\n    engine: vitepress\n    entry: slides.md\n"
            ),
            "presentations/solo/blog.md": "# post\n",
        }
    )
    with pytest.raises(ManifestError, match="one `vitepress` output"):
        load_project(project)


# ── selecting ────────────────────────────────────────────────────────────────

def ids(pairs) -> list[str]:
    return [f"{p.id}:{o.key}" for p, o in pairs]


def test_select_defaults(project: Path) -> None:
    proj = load_project(project)
    assert ids(select(proj, None, project)) == [
        "solo:slides", "talk/v1:slides", "talk/v1:blog", "talk/v2:slides",
    ]
    inside = project / "presentations" / "talk" / "v1"
    assert ids(select(proj, None, inside)) == ["talk/v1:slides", "talk/v1:blog"]


def test_select_by_id_group_path_and_output(project: Path) -> None:
    proj = load_project(project)
    assert ids(select(proj, ["talk/v2"], project)) == ["talk/v2:slides"]
    assert ids(select(proj, ["talk"], project)) == [
        "talk/v1:slides", "talk/v1:blog", "talk/v2:slides",
    ]
    assert ids(select(proj, ["talk:blog"], project)) == ["talk/v1:blog"]
    assert ids(select(proj, ["presentations/solo"], project)) == ["solo:slides"]
    group = project / "presentations" / "talk"
    assert ids(select(proj, ["v2"], group)) == ["talk/v2:slides"]  # relative path


def test_select_bare_output_key_inside_a_presentation(project: Path) -> None:
    proj = load_project(project)
    inside = project / "presentations" / "talk" / "v1"
    assert ids(select(proj, ["blog"], inside)) == ["talk/v1:blog"]
    assert ids(select(proj, [":blog"], inside)) == ["talk/v1:blog"]


def test_select_errors(project: Path) -> None:
    proj = load_project(project)
    with pytest.raises(ManifestError, match="no presentation 'nope'"):
        select(proj, ["nope"], project)
    with pytest.raises(ManifestError, match="no 'blog' output"):
        select(proj, ["talk/v2:blog"], project)


def test_pick_one(project: Path) -> None:
    proj = load_project(project)
    p, o = pick_one(proj, "solo", project)
    assert (p.id, o.key) == ("solo", "slides")
    with pytest.raises(ManifestError, match="several presentations"):
        pick_one(proj, None, project)
    with pytest.raises(ManifestError, match="several outputs"):
        pick_one(proj, "talk/v1", project)
    with pytest.raises(ManifestError, match="matches several"):
        pick_one(proj, "talk", project)
    p, o = pick_one(proj, "talk/v1", project, engine="vitepress")
    assert o.key == "blog"


# ── creating ─────────────────────────────────────────────────────────────────

def test_new_blank(project: Path) -> None:
    dest = create_presentation(load_project(project), "fresh", title="Fresh talk")
    assert read_headmatter(dest / "slides.md") == {"title": "Fresh talk", "routerMode": "hash"}
    assert "fresh" in load_project(project).presentations


def test_new_from_copies_and_records_lineage(write, project: Path) -> None:
    write(
        {
            "presentations/talk/v2/exports/old.pdf": "x",
            "presentations/talk/v2/.slidev/drawings/1.svg": "x",
            "presentations/talk/v2/index.html": "stray",
            "presentations/talk/v2/components/Local.vue": "<template/>",
        }
    )
    dest = create_presentation(
        load_project(project), "talk/v3", from_id="talk/v2", title="Talk: v3"
    )
    assert (dest / "components" / "Local.vue").is_file()
    for skipped in ("exports", ".slidev", "index.html"):
        assert not (dest / skipped).exists()
    text = (dest / "slides.md").read_text()
    assert "# deck config" in text  # comments survive the retitle
    assert read_headmatter(dest / "slides.md")["title"] == "Talk: v3"
    meta = yaml.safe_load((dest / "manifest.yaml").read_text())["metadata"]
    assert meta == {"from": "talk/v2"}
    assert load_project(project).presentations["talk/v3"].metadata["from"] == "talk/v2"


def test_new_from_updates_an_existing_manifest(write, project: Path) -> None:
    write(
        {
            "presentations/solo/manifest.yaml": (
                "# about this talk\nmetadata:\n  title: Solo\n  venue: ASHG\n"
            )
        }
    )
    dest = create_presentation(load_project(project), "solo-2", from_id="solo", title="Solo 2")
    text = (dest / "manifest.yaml").read_text()
    assert text.startswith("# about this talk")
    assert yaml.safe_load(text)["metadata"] == {
        "from": "solo", "title": "Solo 2", "venue": "ASHG",
    }


@pytest.mark.parametrize(
    "bad, match",
    [
        ("solo", "already exists"),
        ("solo/inner", "can't nest"),
        ("talk", "grouping folder"),
        ("a:b", "invalid"),
        ("../escape", "invalid"),
    ],
)
def test_new_rejects_bad_ids(project: Path, bad: str, match: str) -> None:
    with pytest.raises(ManifestError, match=match):
        create_presentation(load_project(project), bad)
