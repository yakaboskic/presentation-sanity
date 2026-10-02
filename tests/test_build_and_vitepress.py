from __future__ import annotations

from pathlib import Path

from presentation_sanity import vitepress
from presentation_sanity.build import project_base, write_project_index
from presentation_sanity.manifest import load_manifest
from presentation_sanity.project import load_project

from .conftest import deck


# ── VitePress, scoped to one presentation ───────────────────────────────────

def test_project_config_scopes_the_site(project: Path) -> None:
    proj = load_project(project)
    p = proj.presentations["talk/v1"]
    config = vitepress.build_config(proj.manifest, p.outputs["blog"], presentation=p)

    assert config["srcDir"] == str(project)
    assert config["outDir"] == str(project / "site/talk/v1/blog")
    assert config["title"] == "Talk v1"
    assert config["rewrites"] == {
        "presentations/talk/v1/blog.md": "index.md",
        "presentations/talk/v1/:slug*": ":slug*",
    }
    exclude = config["srcExclude"]
    for glob in (
        "*.md",                               # README.md at the root
        "shared/**", "scenes/**",             # other top-level dirs
        "presentations/solo/**",              # another presentation
        "presentations/talk/*.md",            # loose notes in the group folder
        "presentations/talk/v2/**",           # a sibling version
        "presentations/talk/v1/slides.md",    # this presentation's deck
    ):
        assert glob in exclude
    assert "presentations/talk/v1/**" not in exclude
    assert not any(g.startswith("presentations/talk/v1/notes") for g in exclude)


def test_single_subject_config_is_unchanged(write) -> None:
    root = write(
        {
            "manifest.yaml": "outputs:\n  blog: {}\n  slides: {}\n",
            "blog.md": "# post\n",
            "slides.md": deck("x"),
        }
    )
    manifest = load_manifest(root)
    config = vitepress.build_config(manifest, manifest.outputs["blog"])
    assert config["outDir"] == "site/blog"
    assert config["rewrites"] == {"blog.md": "index.md"}
    assert "slides.md" in config["srcExclude"]
    assert "srcDir" not in config


def test_scaffold_wires_shared_then_local_components(write, project: Path) -> None:
    write(
        {
            "shared/blog.css": "",
            "presentations/talk/v1/blog.css": "",
            "shared/components/ProvenancePanel.vue": "<template/>",
        }
    )
    proj = load_project(project)
    p = proj.presentations["talk/v1"]
    config_dir = vitepress.scaffold(proj.manifest, p.outputs["blog"], presentation=p)
    assert config_dir == project / ".cache/vitepress/talk/v1/.vitepress"

    theme = (config_dir / "theme" / "index.ts").read_text()
    shared = theme.index("'../../../../../../shared/components/*.vue'")
    local = theme.index("'../../../../../../presentations/talk/v1/components/*.vue'")
    assert shared < local  # later globs win
    assert "import '../../../../../../shared/blog.css'" in theme
    assert theme.index("shared/blog.css") < theme.index("presentations/talk/v1/blog.css")
    assert (config_dir / "config.mts").is_file()


# ── bases and the index ─────────────────────────────────────────────────────

def test_project_base(project: Path) -> None:
    proj = load_project(project)
    v1 = proj.presentations["talk/v1"].outputs
    assert project_base(proj, v1["slides"], "/talks/") == "./"
    assert project_base(proj, v1["blog"], None) == "/talk/v1/blog/"
    assert project_base(proj, v1["blog"], "/talks/") == "/talks/talk/v1/blog/"


def test_project_base_respects_an_explicit_base(write, project: Path) -> None:
    write({"presentations/solo/manifest.yaml": "outputs:\n  slides:\n    base: /fixed/\n"})
    proj = load_project(project)
    assert project_base(proj, proj.presentations["solo"].outputs["slides"], "/x/") is None


def test_index_lists_only_what_is_built(write, project: Path) -> None:
    proj = load_project(project)
    assert write_project_index(proj) is None
    write(
        {
            "site/talk/v1/slides/index.html": "",
            "site/talk/v2/slides/index.html": "",
            "site/solo/slides/index.html": "",
        }
    )
    html = write_project_index(proj).read_text()
    assert "<title>Pigean</title>" in html
    assert '<a href="./talk/v1/slides/">slides</a>' in html
    assert "talk/v1/blog" not in html  # not built
    assert "<h2>talk</h2>" in html
    assert "ASHG" in html and "2026-10-20" in html
