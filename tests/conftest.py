from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

PROJECT_MANIFEST = """\
metadata:
  title: "Pigean"
  authors:
    - name: "Ada"
variables:
  n:
    value: 3
"""


def deck(title: str) -> str:
    return f"---\n# deck config\ntheme: seriph\ntitle: {title}\n---\n\n# {title}\n"


@pytest.fixture
def write(tmp_path: Path) -> Callable[[dict[str, str]], Path]:
    """Write {relative path: content} under tmp_path and return tmp_path."""

    def _write(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return tmp_path

    return _write


@pytest.fixture
def project(write: Callable[[dict[str, str]], Path]) -> Path:
    """A project with a grouped talk (two versions) and a standalone deck."""
    return write(
        {
            "manifest.yaml": PROJECT_MANIFEST,
            "README.md": "# repo\n",
            "shared/components/DataValue.vue": "<template><span/></template>\n",
            "scenes/intro.py": "",
            "presentations/talk/v1/slides.md": deck("Talk v1"),
            "presentations/talk/v1/blog.md": "---\ntitle: Talk post\n---\n\n# Post\n",
            "presentations/talk/v1/notes.md": "# extra page\n",
            "presentations/talk/v2/slides.md": deck("Talk v2"),
            "presentations/talk/README.md": "group notes\n",
            "presentations/solo/slides.md": deck("Solo"),
            "presentations/solo/manifest.yaml": (
                "metadata:\n  venue: ASHG\n  date: 2026-10-20\n"
            ),
        }
    )
