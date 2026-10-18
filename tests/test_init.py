from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml

from presentation_sanity import __version__
from presentation_sanity import init_project as ip
from presentation_sanity.cli import main
from presentation_sanity.markdown_meta import read_headmatter
from presentation_sanity.project import load_project, pick_one

ANSWERS = [
    "--name", "demo-talks", "--title", "Demo", "--author", "Ada Lovelace",
    "--email", "ada@example.org", "--first", "kickoff", "--yes",
]


def answers(**overrides: str) -> ip.Answers:
    base = dict(
        slug="demo-talks", title="Demo", author="Ada Lovelace", email="ada@example.org",
        description="Talks about Demo", first="kickoff", deck_title="Kickoff",
    )
    return ip.Answers(**{**base, **overrides})


def test_bundled_template_is_a_clean_snapshot() -> None:
    files, label = ip.bundled_template()
    assert label.startswith("presentation-sanity-template@")
    for rel in ("manifest.yaml", "pyproject.toml", "package.json", "shared/package.json",
                "presentations/example/slides.md"):
        assert rel in files
    for rel in files:
        parts = rel.split("/")
        assert not {"node_modules", ".venv", ".cache", "site", "__pycache__"} & set(parts), rel
        assert rel not in ip.TEMPLATE_ONLY


# ── init into a new folder ───────────────────────────────────────────────────

def test_init_into_new_dir_applies_renames(tmp_path: Path, capsys) -> None:
    dest = tmp_path / "x"
    assert main(["init", str(dest), *ANSWERS]) == 0

    pyproject = (dest / "pyproject.toml").read_text()
    assert 'name = "demo-talks"' in pyproject
    assert 'description = "Presentations about Demo"' in pyproject
    if all(p.isdigit() for p in __version__.split(".")):
        assert f"presentation-sanity.git@v{__version__}" in pyproject

    assert json.loads((dest / "package.json").read_text())["name"] == "demo-talks"
    lock = json.loads((dest / "package-lock.json").read_text())
    assert lock["name"] == lock["packages"][""]["name"] == "demo-talks"

    manifest = yaml.safe_load((dest / "manifest.yaml").read_text())
    assert manifest["metadata"]["title"] == "Demo"
    assert manifest["metadata"]["authors"][0] == {"name": "Ada Lovelace", "email": "ada@example.org"}
    assert "variables" in manifest  # the rest of the manifest survives

    assert not (dest / "presentations" / "example").exists()
    assert read_headmatter(dest / "presentations/kickoff/slides.md")["title"] == "Demo"
    assert (dest / "presentations/kickoff/blog.md").is_file()
    assert not (dest / "uv.lock").exists()  # the first `uv sync` writes the project's own
    readme = (dest / "README.md").read_text()
    assert readme.startswith("# demo-talks") and "dev kickoff" in readme

    for rel in ip.TEMPLATE_ONLY:
        assert not (dest / rel).exists()
    assert not (dest / ".git").exists()
    for base in ip.SKILL_DIRS:
        assert (dest / base / "presentation-sanity" / "SKILL.md").is_file()
        assert (dest / base / "presentation-sanity" / "modes" / "_shared.md").is_file()

    out = capsys.readouterr().out
    assert "uv sync" in out and "npm install" in out and "commit it" in out


def test_init_dev_commands_name_an_output(tmp_path: Path, capsys) -> None:
    """The first presentation has a deck and a post, so a bare `dev kickoff` would refuse."""
    dest = tmp_path / "x"
    assert main(["init", str(dest), *ANSWERS]) == 0
    project = load_project(dest)
    for text in (capsys.readouterr().out, (dest / "README.md").read_text()):
        targets = re.findall(r"presentation-sanity dev (\S+)", text)
        assert targets
        for target in targets:
            pick_one(project, target, dest)  # raises "several outputs — name one"


def test_init_nested_first_and_quoting(tmp_path: Path) -> None:
    dest = tmp_path / "y"
    a = answers(first="kickoff/v1", title='The "Big" Talk', deck_title="Kickoff: v1")
    ip.create_project(dest, a)
    assert read_headmatter(dest / "presentations/kickoff/v1/slides.md")["title"] == "Kickoff: v1"
    assert yaml.safe_load((dest / "manifest.yaml").read_text())["metadata"]["title"] == 'The "Big" Talk'


def test_init_without_skills(tmp_path: Path) -> None:
    dest = tmp_path / "z"
    assert main(["init", str(dest), *ANSWERS, "--no-skills"]) == 0
    assert not (dest / ".claude").exists() and not (dest / ".agents").exists()


def test_defaults_come_from_the_folder_name(tmp_path: Path) -> None:
    a = ip.gather_answers(tmp_path / "Grant Renewal 2027", {"author": "A", "email": "a@b.c"})
    assert a.slug == "grant-renewal-2027"
    assert a.title == "Grant Renewal 2027"
    assert a.first == "kickoff" and a.deck_title == a.title


def test_prompts_fill_only_what_was_not_given(tmp_path: Path) -> None:
    asked: list[str] = []

    def ask(prompt: str, default: str) -> str:
        asked.append(prompt)
        return "My Title" if prompt.startswith("Project title") else default

    a = ip.gather_answers(tmp_path / "p", {"author": "A", "email": "a@b.c"}, ask=ask)
    assert a.title == "My Title" and a.deck_title == "My Title"
    assert not any(p.startswith(("Author", "Author email")) for p in asked)


def test_bad_answers_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ip.InitError):
        answers(slug="no spaces please")
    with pytest.raises(ip.InitError):
        answers(first="../escape")


@pytest.mark.skipif(not (shutil.which("uv") and shutil.which("git")), reason="needs uv and git")
def test_first_uv_lock_resolves_the_pinned_tag(tmp_path: Path) -> None:
    """What `pages init`'s `uv sync --locked` needs: a lock for this project's own pin."""
    dest = tmp_path / "x"
    assert main(["init", str(dest), *ANSWERS, "--no-skills"]) == 0
    pin = re.search(r"presentation-sanity\.git@(v[^\"]+)", (dest / "pyproject.toml").read_text()).group(1)
    tag = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--tags",
         "https://github.com/yakaboskic/presentation-sanity.git", f"refs/tags/{pin}"],
        capture_output=True, timeout=30,
    )
    if tag.returncode != 0:  # 2: not tagged yet (a release runs its tests first); else offline
        pytest.skip(f"{pin} isn't published" if tag.returncode == 2 else "GitHub unreachable")
    lock = subprocess.run(["uv", "lock"], cwd=dest, capture_output=True, text=True, timeout=600)
    assert lock.returncode == 0, lock.stderr
    assert f"presentation-sanity.git?rev={pin}#" in (dest / "uv.lock").read_text()


# ── knitting into an existing folder ─────────────────────────────────────────

def test_knit_into_current_dir_keeps_other_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "notes.txt").write_text("mine\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "results.csv").write_text("a,b\n")
    monkeypatch.chdir(tmp_path)
    assert main(["init", ".", *ANSWERS]) == 0
    assert (tmp_path / "notes.txt").read_text() == "mine\n"
    assert (tmp_path / "data/results.csv").read_text() == "a,b\n"
    assert (tmp_path / "manifest.yaml").is_file()


def test_knit_refuses_conflicts_and_writes_nothing(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# my repo\n")
    (tmp_path / "package.json").write_text("{}\n")
    assert main(["init", str(tmp_path), *ANSWERS]) == 1
    err = capsys.readouterr().err
    assert "README.md" in err and "package.json" in err and "--force" in err
    assert (tmp_path / "README.md").read_text() == "# my repo\n"
    assert not (tmp_path / "manifest.yaml").exists()  # nothing at all was written


def test_force_overwrites_conflicts(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# my repo\n")
    assert main(["init", str(tmp_path), *ANSWERS, "--force"]) == 0
    assert (tmp_path / "README.md").read_text().startswith("# demo-talks")


def test_identical_files_are_not_conflicts(tmp_path: Path) -> None:
    ip.create_project(tmp_path, answers())
    again = ip.create_project(tmp_path, answers())  # same answers, same bytes
    assert again.written == [] and again.overwritten == []


def test_dest_that_is_a_file_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "file"
    target.write_text("x")
    with pytest.raises(ip.InitError):
        ip.create_project(target, answers())


# ── --git ────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_makes_a_first_commit(tmp_path: Path, monkeypatch) -> None:
    for var, value in {
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.org",
    }.items():
        monkeypatch.setenv(var, value)
    dest = tmp_path / "g"
    assert main(["init", str(dest), *ANSWERS, "--git"]) == 0
    log = subprocess.run(["git", "log", "--oneline"], cwd=dest, capture_output=True, text=True)
    assert log.stdout.count("\n") == 1 and "demo-talks" in log.stdout
    tracked = subprocess.run(["git", "ls-files"], cwd=dest, capture_output=True, text=True).stdout
    assert "manifest.yaml" in tracked and ".claude/skills/presentation-sanity/SKILL.md" in tracked
    ignored = subprocess.run(["git", "check-ignore", "-q", "uv.lock"], cwd=dest)
    assert ignored.returncode == 1  # the lock `uv sync` writes gets committed


# ── --in-place (the template's init.py) ─────────────────────────────────────

def template_copy(tmp_path: Path) -> Path:
    root = tmp_path / "copy"
    for rel, data in ip.bundled_template()[0].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    (root / "init.py").write_text("# shim\n")
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/pages.yml").write_text("# demo deploy\n")
    (root / "uv.lock").write_text("# the template's lock\n")
    return root


def test_in_place_renames_and_removes_template_files(tmp_path: Path) -> None:
    root = template_copy(tmp_path)
    assert main(["init", str(root), "--in-place", *ANSWERS]) == 0
    assert 'name = "demo-talks"' in (root / "pyproject.toml").read_text()
    assert (root / "presentations/kickoff/slides.md").is_file()
    assert not (root / "presentations/example").exists()
    assert not (root / "init.py").exists()
    assert not (root / "uv.lock").exists()  # it locks the template under its old name
    assert not (root / ".github").exists()  # no empty folders left behind
    assert (root / ".claude/skills/presentation-sanity/SKILL.md").is_file()
    # a second run finds nothing to initialize
    assert main(["init", str(root), "--in-place", *ANSWERS]) == 1


def test_in_place_into_a_subfolder_of_example(tmp_path: Path) -> None:
    root = template_copy(tmp_path)
    ip.init_in_place(root, answers(first="example/v1"))
    assert (root / "presentations/example/v1/slides.md").is_file()
    assert not (root / "presentations/example/slides.md").exists()


# ── --from gh:owner/repo ─────────────────────────────────────────────────────

def tarball(files: dict[str, bytes], top: str = "lab-talks-template-abc1234") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in {f"{top}/{k}": v for k, v in files.items()}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{top}/evil")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    return buf.getvalue()


def test_parse_gh_spec() -> None:
    assert ip.parse_gh_spec("gh:lab/talks-template") == ("lab", "talks-template", None)
    assert ip.parse_gh_spec("gh:lab/talks-template.git@v2") == ("lab", "talks-template", "v2")
    with pytest.raises(ip.InitError):
        ip.parse_gh_spec("https://github.com/lab/t")


def test_tarball_strips_top_dir_and_drops_links() -> None:
    files, top = ip.files_from_tarball(tarball({"manifest.yaml": b"x", "a/b.md": b"y"}))
    assert files == {"manifest.yaml": b"x", "a/b.md": b"y"}
    assert top.endswith("abc1234")


def test_init_from_github_fork(tmp_path: Path, monkeypatch) -> None:
    template, _ = ip.bundled_template()
    fork = {**template, "init.py": b"# shim\n", "uv.lock": b"# fork's lock\n", "LAB.md": b"lab house rules\n"}
    seen: list[str] = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=0):
        seen.append(request.full_url)
        return Response(tarball(fork))

    monkeypatch.setattr(ip.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "f"
    assert main(["init", str(dest), "--from", "gh:lab/talks-template@v2", *ANSWERS]) == 0
    assert seen == ["https://api.github.com/repos/lab/talks-template/tarball/v2"]
    assert (dest / "LAB.md").read_text() == "lab house rules\n"
    assert not (dest / "init.py").exists() and not (dest / "uv.lock").exists()
    # a fork's pin is the fork's business: left as the fork wrote it
    pin = re.search(r"presentation-sanity\.git@(v[^\"]+)", template["pyproject.toml"].decode()).group(1)
    assert f"presentation-sanity.git@{pin}" in (dest / "pyproject.toml").read_text()


# ── skills on an existing project ────────────────────────────────────────────

def test_skills_command_installs_and_refreshes(project: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(project)
    assert main(["skills"]) == 0
    skill = project / ".agents/skills/presentation-sanity/SKILL.md"
    assert skill.is_file()
    skill.write_text("edited\n")
    assert main(["skills"]) == 1  # won't clobber an edit…
    assert main(["skills", "--force"]) == 0  # …unless asked
    assert skill.read_text() != "edited\n"
