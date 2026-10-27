"""The public Markdown manual, built by the Runtime-prepared Sphinx CLI."""

import tomllib
from pathlib import Path

from pygments.lexers import TextLexer
from sphinx.application import Sphinx

_root = Path(__file__).resolve().parent.parent
_project = tomllib.loads((_root / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]
project = _project["name"]
release = _project["version"]
version = release

extensions = ["myst_parser", "sphinx_needs", "sphinx_codelinks"]
source_suffix = {".md": "markdown"}
root_doc = "README"
exclude_patterns = ["superpowers/**"]
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 6
html_theme = "alabaster"

needs_id_required = True
needs_build_json = True
needs_reproducible_json = True
needs_schema_validation_enabled = True
needs_types = [
    {
        "directive": "spec",
        "title": "Specification",
        "prefix": "SPEC_",
        "color": "#FEDCD2",
        "style": "node",
    },
    {
        "directive": "adr",
        "title": "Architecture decision",
        "prefix": "ADR_",
        "color": "#BFD8D2",
        "style": "node",
        "fields": {
            "status": {
                "schema": {
                    "enum": [
                        "proposed",
                        "accepted",
                        "rejected",
                        "superseded",
                        "deprecated",
                    ],
                },
                "nullable": False,
            },
        },
        "links": {
            "decides": {
                "incoming": "is decided by",
                "outgoing": "decides",
                "copy": False,
                "allow_dead_links": False,
                "target_types": ["spec"],
            },
            "supersedes": {
                "incoming": "is superseded by",
                "outgoing": "supersedes",
                "copy": False,
                "allow_dead_links": False,
                "target_types": ["adr"],
            },
        },
    },
]


def setup(app: Sphinx) -> None:
    # Preserve GitHub's Mermaid fences as plain text in this minimal HTML build.
    app.add_lexer("mermaid", TextLexer)
