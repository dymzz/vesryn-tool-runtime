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

extensions = [
    "myst_parser",
    "sphinx_needs",
    "sphinx_codelinks",
    "sphinx_test_reports",
    "autoapi",
    "sphinx.ext.intersphinx",
]
# AutoAPI writes its own index page as `index.rst`, so reStructuredText has
# to be a source suffix even though every authored page is Markdown.
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "README"
myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 6
html_theme = "alabaster"

# The symbol-level API reference is generated from the package source, so a
# signature is never maintained twice. The manual keeps the behavioral
# contracts; the reference keeps the signatures and the types.
#
# The scan root is the package directory, not `src`: the reference covers
# what the package ships, and nothing else that happens to live beside it.
autoapi_dirs = ["../src/vesryn_tool_runtime"]
# Private and special members stay out, and every public member is listed
# even when it carries no docstring. The imported members are the package
# root's `__all__` re-exports: the public entry point of the package.
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
]
# The standard library types in the public signatures resolve against the
# Python inventory, which the build reads over the network.
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
# A type from a dependency that publishes no inventory is named exactly.
# No pattern is used, so an unresolved reference inside the package still
# fails the build.
nitpick_ignore = [("py:class", "vesryn_log.EventSink")]

needs_id_required = True
needs_build_json = True
needs_reproducible_json = True
needs_schema_validation_enabled = True
# A test case names the specification it verifies. The link type is declared
# here because the test cases are imported, not authored: the conversion maps
# the JUnit property onto this field (see ubproject.toml).
needs_links = {
    "verifies": {
        "incoming": "is verified by",
        "outgoing": "verifies",
        "target_types": ["spec"],
        "allow_dead_links": False,
    },
}
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


def _skip_private_module(_app, what, name, _obj, skip, _options):
    """Keep the package's private modules out of the generated reference.

    A single-underscore module is internal. It is still parsed, so the
    modules importing it resolve their imports; only the reference hides
    it. The package root's `__all__` names the public entry, and no
    exported name is defined in a private module (asserted by
    `test_exported_names_are_defined_in_public_modules` in
    tests/test_boundaries.py).
    """
    short = name.rsplit(".", 1)[-1]
    private = short.startswith("_") and not short.endswith("__")
    return skip or (what in {"module", "package"} and private)


def setup(app: Sphinx) -> None:
    # Preserve GitHub's Mermaid fences as plain text in this minimal HTML build.
    app.add_lexer("mermaid", TextLexer)
    app.connect("autoapi-skip-member", _skip_private_module)
