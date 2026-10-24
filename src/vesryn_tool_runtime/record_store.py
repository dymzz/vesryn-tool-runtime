"""SQLite storage for the three records: one gateway per record type.

``open_record_store(path)`` owns the connection, creates the constrained
schema from discovery_records.SCHEMA and refuses any column drift away from
the issue's field tables. Each record type then has its own gateway over the
shared connection — ``store.assets``, ``store.groups``, ``store.accesses`` —
with nothing in common but the foreign keys the schema itself enforces.
"""

import json
import sqlite3
from pathlib import Path

from .discovery_records import (
    GroupMember,
    Platform,
    RecordError,
    ToolAccess,
    ToolAsset,
    ToolAssetVersion,
    ToolGroup,
    _name,
)
from .documents import canonical
from .record_schema import SCHEMA_VERSION, TABLE_COLUMNS, schema_sql


def _translate(error, duplicate_code):
    """Map a schema constraint violation onto its record reason."""
    if isinstance(error, sqlite3.IntegrityError):
        message = str(error).casefold()
        if "foreign key" in message:
            raise RecordError("unknown_tool") from None
        if "unique" in message or "primary key" in message:
            raise RecordError(duplicate_code) from None
        if "check" in message:
            raise RecordError("invalid_record") from None
    raise error


class AssetTable:
    """Writes and reads ToolAsset rows and their version sub-rows."""

    def __init__(self, db):
        self._db = db

    def put(self, asset):
        if not isinstance(asset, ToolAsset):
            raise RecordError("invalid_record")
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO tool_asset"
                    " (tool_id, name, provider, package, entrypoint)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        asset.tool_id,
                        asset.name,
                        asset.provider,
                        asset.package,
                        asset.entrypoint,
                    ),
                )
                self._db.executemany(
                    "INSERT INTO tool_release"
                    " (tool_id, version, platform_os, platform_arch, source,"
                    " digest_type, digest) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            asset.tool_id,
                            item.version,
                            item.platform.os if item.platform else None,
                            item.platform.arch if item.platform else None,
                            item.source,
                            item.digest_type,
                            item.digest,
                        )
                        for item in asset.versions
                    ],
                )
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_tool_id")

    def get(self, tool_id):
        _name(tool_id, "unknown_tool", 256)
        row = self._db.execute(
            "SELECT tool_id, name, provider, package, entrypoint"
            " FROM tool_asset WHERE tool_id = ?",
            (tool_id,),
        ).fetchone()
        if row is None:
            raise RecordError("unknown_tool")
        versions = tuple(
            ToolAssetVersion(
                version,
                source,
                digest_type,
                digest,
                Platform(os, arch) if os is not None else None,
            )
            for version, os, arch, source, digest_type, digest in self._db.execute(
                "SELECT version, platform_os, platform_arch, source,"
                " digest_type, digest FROM tool_release WHERE tool_id = ?"
                " ORDER BY rowid",
                (tool_id,),
            )
        )
        return ToolAsset(row[0], row[1], row[2], versions, row[4], package=row[3])


class GroupTable:
    """Writes and reads ToolGroup rows and their member sub-rows."""

    def __init__(self, db):
        self._db = db

    def put(self, group):
        if not isinstance(group, ToolGroup):
            raise RecordError("invalid_record")
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO tool_group (group_id, summary) VALUES (?, ?)",
                    (group.group_id, group.summary),
                )
                self._db.executemany(
                    "INSERT INTO tool_group_member"
                    " (group_id, tool_id, summary) VALUES (?, ?, ?)",
                    [
                        (group.group_id, member.tool_id, member.summary)
                        for member in group.members
                    ],
                )
                self._db.executemany(
                    "INSERT INTO tool_group_member_alias"
                    " (group_id, tool_id, alias) VALUES (?, ?, ?)",
                    [
                        (group.group_id, member.tool_id, alias)
                        for member in group.members
                        for alias in member.aliases
                    ],
                )
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_group_id")

    def get(self, group_id):
        _name(group_id, "unknown_group", 256)
        row = self._db.execute(
            "SELECT group_id, summary FROM tool_group WHERE group_id = ?",
            (group_id,),
        ).fetchone()
        if row is None:
            raise RecordError("unknown_group")
        members = tuple(
            GroupMember(
                tool_id,
                summary,
                tuple(
                    alias
                    for (alias,) in self._db.execute(
                        "SELECT alias FROM tool_group_member_alias"
                        " WHERE group_id = ? AND tool_id = ? ORDER BY alias",
                        (group_id, tool_id),
                    )
                ),
            )
            for tool_id, summary in self._db.execute(
                "SELECT tool_id, summary FROM tool_group_member"
                " WHERE group_id = ? ORDER BY rowid",
                (group_id,),
            )
        )
        return ToolGroup(row[0], row[1], members)


class AccessTable:
    """Writes and reads ToolAccess rows, by entry key or by tool."""

    def __init__(self, db):
        self._db = db

    def put(self, access):
        if not isinstance(access, ToolAccess):
            raise RecordError("invalid_record")
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO tool_access"
                    " (access_id, tool_id, method, target, contract, summary)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        access.access_id,
                        access.tool_id,
                        access.method,
                        access.target,
                        canonical(dict(access.contract)).decode(),
                        access.summary,
                    ),
                )
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_access_id")

    def get(self, access_id):
        _name(access_id, "unknown_access", 256)
        row = self._db.execute(
            "SELECT access_id, tool_id, method, target, contract, summary"
            " FROM tool_access WHERE access_id = ?",
            (access_id,),
        ).fetchone()
        if row is None:
            raise RecordError("unknown_access")
        return ToolAccess(row[0], row[1], row[2], row[3], json.loads(row[4]), row[5])

    def for_tool(self, tool_id):
        """Every entry of one tool; a tool may expose several."""
        _name(tool_id, "unknown_tool", 256)
        return tuple(
            ToolAccess(row[0], row[1], row[2], row[3], json.loads(row[4]), row[5])
            for row in self._db.execute(
                "SELECT access_id, tool_id, method, target, contract, summary"
                " FROM tool_access WHERE tool_id = ? ORDER BY access_id",
                (tool_id,),
            )
        )


class RecordStore:
    """A connection to the constrained schema with per-record gateways."""

    def __init__(self, db):
        self._db = db
        self.assets = AssetTable(db)
        self.groups = GroupTable(db)
        self.accesses = AccessTable(db)

    def close(self):
        self._db.close()


RECORDS_DATABASE = "records.sqlite3"


def default_database():
    """Databases live in data/: the default is the committed library there."""
    return Path(__file__).resolve().parents[2] / "data" / RECORDS_DATABASE


def open_record_store(path=None):
    """Open a store whose tables match the field tables.

    Without a path this opens ``data/records.sqlite3`` — databases are stored
    under ``data/``; temporary scratch work belongs in temp directories, not
    the database home.
    """
    if path is None:
        target = default_database()
    elif isinstance(path, (str, Path)) and str(path) == ":memory:":
        target = None
        location = ":memory:"
    elif isinstance(path, (str, Path)):
        target = Path(path)
    else:
        raise RecordError("invalid_store")
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        location = str(target)
    db = sqlite3.connect(location)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        current = db.execute("PRAGMA user_version").fetchone()[0]
        if current == 0:
            db.executescript(schema_sql())
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif current != SCHEMA_VERSION:
            raise RecordError("unsupported_schema")
        for table, columns in TABLE_COLUMNS.items():
            actual = tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
            if actual != columns:
                raise RecordError("schema_drift")
    except BaseException:
        db.close()
        raise
    return RecordStore(db)
