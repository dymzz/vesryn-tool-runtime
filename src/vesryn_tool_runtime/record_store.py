"""SQLite storage for the three records: one gateway per record type.

``open_record_store(path)`` opens (creating if needed) a database whose DDL
must equal the frozen package schema exactly — constraints included, not just
column names. The writable location is ALWAYS the caller's explicit choice
(``":memory:"`` or a filesystem path); there is deliberately no default that
could resolve into the Python installation directory. Each record type has
its own gateway — ``store.assets``, ``store.groups``, ``store.accesses`` —
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
from .record_schema import SCHEMA_VERSION, TABLE_COLUMNS, schema_matches, schema_sql


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


def insert_asset(db, asset):
    """Insert one asset and its releases on the caller's transaction."""
    db.execute(
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
    db.executemany(
        "INSERT INTO tool_release"
        " (tool_id, version, platform_os, platform_arch,"
        " platform_abi, platform_python, source, digest_type,"
        " digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                asset.tool_id,
                item.version,
                item.platform.os if item.platform else None,
                item.platform.arch if item.platform else None,
                item.platform.abi if item.platform else None,
                item.python,
                item.source,
                item.digest_type,
                item.digest,
            )
            for item in asset.versions
        ],
    )


class AssetTable:
    """Writes and reads ToolAsset rows and their release sub-rows."""

    def __init__(self, db):
        self._db = db

    def put(self, asset):
        if not isinstance(asset, ToolAsset):
            raise RecordError("invalid_record")
        try:
            with self._db:
                insert_asset(self._db, asset)
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_tool_id")

    def all(self):
        """Every asset, ordered by tool primary key (base traversal)."""
        return tuple(
            self.get(tool_id)
            for (tool_id,) in self._db.execute(
                "SELECT tool_id FROM tool_asset ORDER BY tool_id"
            )
        )

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
                Platform(os, arch, abi) if os is not None else None,
                python,
            )
            for version, os, arch, abi, python, source, digest_type, digest in (
                self._db.execute(
                    "SELECT version, platform_os, platform_arch, platform_abi,"
                    " platform_python, source, digest_type, digest"
                    " FROM tool_release WHERE tool_id = ? ORDER BY rowid",
                    (tool_id,),
                )
            )
        )
        return ToolAsset(row[0], row[1], row[2], versions, row[4], package=row[3])


def insert_group(db, group):
    """Insert one group, its members and their aliases."""
    db.execute(
        "INSERT INTO tool_group (group_id, summary) VALUES (?, ?)",
        (group.group_id, group.summary),
    )
    db.executemany(
        "INSERT INTO tool_group_member (group_id, tool_id, summary) VALUES (?, ?, ?)",
        [(group.group_id, member.tool_id, member.summary) for member in group.members],
    )
    db.executemany(
        "INSERT INTO tool_group_member_alias"
        " (group_id, tool_id, alias) VALUES (?, ?, ?)",
        [
            (group.group_id, member.tool_id, alias)
            for member in group.members
            for alias in member.aliases
        ],
    )


class GroupTable:
    """Writes and reads ToolGroup rows, member rows and member aliases."""

    def __init__(self, db):
        self._db = db

    def put(self, group):
        if not isinstance(group, ToolGroup):
            raise RecordError("invalid_record")
        try:
            with self._db:
                insert_group(self._db, group)
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_group_id")

    def all(self):
        """Every group, ordered by group primary key (base traversal)."""
        return tuple(
            self.get(group_id)
            for (group_id,) in self._db.execute(
                "SELECT group_id FROM tool_group ORDER BY group_id"
            )
        )

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


def insert_access(db, access):
    """Insert one access row."""
    db.execute(
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


class AccessTable:
    """Writes and reads ToolAccess rows, by entry key or by tool."""

    def __init__(self, db):
        self._db = db

    def put(self, access):
        if not isinstance(access, ToolAccess):
            raise RecordError("invalid_record")
        try:
            with self._db:
                insert_access(self._db, access)
        except sqlite3.IntegrityError as error:
            _translate(error, "duplicate_access_id")

    def all(self):
        """Every entry, ordered by access primary key (base traversal)."""
        return tuple(
            self.get(access_id)
            for (access_id,) in self._db.execute(
                "SELECT access_id FROM tool_access ORDER BY access_id"
            )
        )

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
        tool_exists = self._db.execute(
            "SELECT 1 FROM tool_asset WHERE tool_id = ?",
            (tool_id,),
        ).fetchone()
        if tool_exists is None:
            raise RecordError("unknown_tool")
        return tuple(
            ToolAccess(row[0], row[1], row[2], row[3], json.loads(row[4]), row[5])
            for row in self._db.execute(
                "SELECT access_id, tool_id, method, target, contract, summary"
                " FROM tool_access WHERE tool_id = ? ORDER BY access_id",
                (tool_id,),
            )
        )


class RecordStore:
    """A connection to the frozen schema with per-record gateways."""

    def __init__(self, db):
        self._db = db
        self.assets = AssetTable(db)
        self.groups = GroupTable(db)
        self.accesses = AccessTable(db)

    def put_records(self, records):
        """Register a batch atomically: assets, then groups, then accesses.

        In-batch references resolve in that order. A record identical to the
        stored one is skipped (idempotent re-registration); the same primary
        key with different content is an explicit conflict and the whole
        batch rolls back — a failed batch never leaves a partial catalog.
        """
        records = tuple(records)
        staged = {"asset": [], "group": [], "access": []}
        for record in records:
            if isinstance(record, ToolAsset):
                staged["asset"].append(record)
            elif isinstance(record, ToolGroup):
                staged["group"].append(record)
            elif isinstance(record, ToolAccess):
                staged["access"].append(record)
            else:
                raise RecordError("invalid_record")
        for kind, key_of in (
            ("asset", lambda record: record.tool_id),
            ("group", lambda record: record.group_id),
            ("access", lambda record: record.access_id),
        ):
            keys = [key_of(record) for record in staged[kind]]
            if len(set(keys)) != len(keys):
                raise RecordError(f"duplicate_{kind}")
        try:
            with self._db:
                for record in staged["asset"]:
                    self._put_one(
                        record,
                        insert_asset,
                        self.assets.get,
                        record.tool_id,
                        "duplicate_tool_id",
                    )
                for record in staged["group"]:
                    self._put_one(
                        record,
                        insert_group,
                        self.groups.get,
                        record.group_id,
                        "duplicate_group_id",
                    )
                for record in staged["access"]:
                    self._put_one(
                        record,
                        insert_access,
                        self.accesses.get,
                        record.access_id,
                        "duplicate_access_id",
                    )
        except sqlite3.IntegrityError as error:
            _translate(error, "invalid_record")

    def _put_one(self, record, insert, read, key, duplicate_code):
        try:
            insert(self._db, record)
        except sqlite3.IntegrityError as error:
            message = str(error).casefold()
            if "unique" not in message and "primary key" not in message:
                _translate(error, duplicate_code)
            try:
                existing = read(key)
            except RecordError:
                _translate(error, duplicate_code)
            if existing != record:
                raise RecordError(duplicate_code) from None
            # Identical re-registration: idempotent, no duplicate entry.

    def close(self):
        self._db.close()


def open_record_store(path):
    """Open a store at the caller's explicit path, or an in-memory one.

    ``path`` is ``":memory:"`` or a filesystem location chosen by the caller;
    a brand-new database is created from the frozen package schema, and any
    existing database must carry the exact frozen DDL (constraints included)
    and schema version — same-columns-but-no-constraints databases are
    refused as ``schema_drift``.
    """
    if isinstance(path, (str, Path)) and str(path) == ":memory:":
        location = ":memory:"
    elif isinstance(path, (str, Path)):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        location = str(target)
    else:
        raise RecordError("invalid_store")
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
        if not schema_matches(db):
            raise RecordError("schema_drift")
    except BaseException:
        db.close()
        raise
    return RecordStore(db)
