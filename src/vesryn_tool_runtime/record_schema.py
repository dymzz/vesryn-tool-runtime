"""The frozen record schema and seed, shipped and read as package resources.

``record_schema.sql`` beside this module is the single frozen authority for
the six-table layout (issue #27 reopened; owner-directed structure) and ships
inside the wheel — it is read through ``importlib.resources`` and works from
an independent installation, with no source checkout and no absolute paths.
``record_seed.sql`` carries the issue's literal example records the same way.
Writable databases are NOT package data: their location is always supplied
explicitly by the caller (the repository keeps its demo library under
``data/``); nothing here resolves a default writable path from the install
location.

The parity contract goes beyond column names: ``expected_schema()`` is the
full DDL text (tables and the release-identity index) the frozen file
creates, and a database is accepted only if its own ``sqlite_master`` DDL
matches it — a same-columns/no-constraints database is refused as drift.
"""

import sqlite3
from importlib.resources import files as resource_files

SCHEMA_VERSION = 3

SCHEMA_RESOURCE = "record_schema.sql"
SEED_RESOURCE = "record_seed.sql"

TABLE_COLUMNS = {
    "tool_asset": ("tool_id", "name", "provider", "package", "entrypoint"),
    "tool_release": (
        "tool_id",
        "version",
        "platform_os",
        "platform_arch",
        "platform_abi",
        "platform_python",
        "source",
        "digest_type",
        "digest",
    ),
    "tool_group": ("group_id", "summary"),
    "tool_group_member": ("group_id", "tool_id", "summary"),
    "tool_group_member_alias": ("group_id", "tool_id", "alias"),
    "tool_access": (
        "access_id",
        "tool_id",
        "method",
        "target",
        "contract",
        "summary",
    ),
    "tool_install": (
        "tool_id",
        "command",
        "version",
        "entry",
        "description",
        "prepared_via",
        "reused",
        "source_verified",
        "registered_at",
    ),
}


def _resource(name):
    return resource_files(__package__).joinpath(name).read_text(encoding="utf-8")


def schema_sql():
    """The frozen DDL, read from the package resource."""
    return _resource(SCHEMA_RESOURCE)


def seed_sql():
    """The example records, read from the package resource."""
    return _resource(SEED_RESOURCE)


def _normalized(sql):
    return " ".join(sql.split())


def expected_schema():
    """name → normalized DDL for every table and index the frozen file makes."""
    db = sqlite3.connect(":memory:")
    try:
        db.executescript(schema_sql())
        rows = db.execute(
            "SELECT name, sql FROM sqlite_master"
            " WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {name: _normalized(sql) for name, sql in rows}
    finally:
        db.close()


def schema_matches(db):
    """True when the database's own DDL equals the frozen schema's DDL."""
    expected = expected_schema()
    rows = db.execute(
        "SELECT name, sql FROM sqlite_master"
        " WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual = {name: _normalized(sql) for name, sql in rows}
    return actual == expected
