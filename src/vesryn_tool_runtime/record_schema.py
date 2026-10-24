"""The frozen record schema: six physical tables for three logical entities.

The DDL lives in ``data/record_schema.sql`` — that committed file alone is
the frozen authority for the storage layout (issue #27, reopened;
owner-directed structure). This module pins its version and column lists and
loads the SQL verbatim; the parity check in record_store then refuses any
database whose tables drift from it. ``data/`` holds committed artifacts
only — the frozen schema, the seed data and the built SQLite library;
runtime databases go to temp locations, never into ``data/``.
"""

from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "record_schema.sql"


def schema_sql():
    """The frozen DDL, read verbatim from data/record_schema.sql."""
    try:
        return SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError:
        raise RuntimeError(f"Frozen schema file is missing: {SCHEMA_PATH}") from None


TABLE_COLUMNS = {
    "tool_asset": ("tool_id", "name", "provider", "package", "entrypoint"),
    "tool_release": (
        "tool_id",
        "version",
        "platform_os",
        "platform_arch",
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
}
