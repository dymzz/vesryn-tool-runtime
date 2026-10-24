"""Issue #27 record foundation: six physical tables, constraints in the schema.

Three logical entities (ToolAsset / ToolGroup / ToolAccess) on six physical
tables — tool_release holds version/platform artifacts, tool_group_member and
tool_group_member_alias hold per-group member facts. PRAGMA foreign_keys = ON
enforces: no ToolAsset means no associated ToolAccess; one tool exposes
several distinct entries; every entry carries its own method/target/contract;
a missing required field fails on insert.
"""

import sqlite3
from pathlib import Path

import pytest

from vesryn_tool_runtime.discovery_records import (
    GroupMember,
    Platform,
    RecordError,
    ToolAccess,
    ToolAsset,
    ToolAssetVersion,
    ToolGroup,
)
from vesryn_tool_runtime.record_schema import (
    SCHEMA_RESOURCE,
    SEED_RESOURCE,
    TABLE_COLUMNS,
    schema_sql,
)
from vesryn_tool_runtime.record_store import open_record_store

TRIVY_LINUX = ToolAssetVersion(
    "0.76.1",
    "https://github.com/aquasecurity/trivy/releases/download/v0.76.1/"
    "trivy_0.76.1_Linux-64bit.tar.gz",
    "sha256",
    "c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0",
    Platform("linux", "x86_64"),
)
TRIVY_WINDOWS = ToolAssetVersion(
    "0.76.1",
    "https://github.com/aquasecurity/trivy/releases/download/v0.76.1/"
    "trivy_0.76.1_Windows-64bit.zip",
    "sha256",
    "3350f4fac96ed099590c4a353bddb226f86311a0a2e7a8c626c162790d947f10",
    Platform("windows", "x86_64"),
)
TRIVY_OLD = ToolAssetVersion(
    "0.74.0",
    "https://github.com/aquasecurity/trivy/releases/download/v0.74.0/"
    "trivy_0.74.0_Linux-64bit.tar.gz",
    "sha256",
    "0" * 64,
    Platform("linux", "x86_64"),
)
TRIVY = ToolAsset(
    "trivy",
    "trivy",
    "github-release",
    (TRIVY_LINUX, TRIVY_WINDOWS, TRIVY_OLD),
    "trivy",
)


def access(access_id, method, target, contract=None, **changes):
    value = {
        "access_id": access_id,
        "tool_id": "trivy",
        "method": method,
        "target": target,
        "contract": contract
        if contract is not None
        else {"input_schema": {"type": "object"}},
        "summary": f"Run {access_id}",
    }
    value.update(changes)
    return ToolAccess(**value)


@pytest.fixture
def store():
    handle = open_record_store(":memory:")
    handle.assets.put(TRIVY)
    yield handle
    handle.close()


def test_round_trip_with_the_issues_literal_examples(store):
    """trivy, ci-security, ci-release, trivy.scan, trivy.sbom, trivy.cli all
    survive a write/read round trip; one tool keeps one tool_id across
    groups, versions, platforms and entries."""
    store.groups.put(
        ToolGroup(
            "ci-security",
            "Security gates for CI",
            (
                GroupMember(
                    "trivy", "Vulnerability and configuration scanning", ("vuln",)
                ),
            ),
        )
    )
    store.groups.put(
        ToolGroup(
            "ci-release",
            "Release readiness checks",
            (GroupMember("trivy", "SBOM generation", ("sbom",)),),
        )
    )
    store.accesses.put(access("trivy.scan", "native", "trivy scan --exit-code 1"))
    store.accesses.put(
        access(
            "trivy.sbom",
            "dagger",
            "engineering_ci.security_sbom",
            contract={"dagger": "security_sbom", "args": {"format": "spdx"}},
        )
    )
    store.accesses.put(access("trivy.cli", "uv", "trivy"))

    asset = store.assets.get("trivy")
    assert (asset.tool_id, asset.name, asset.provider, asset.entrypoint) == (
        "trivy",
        "trivy",
        "github-release",
        "trivy",
    )
    assert asset.package is None
    assert [item.version for item in asset.versions] == [
        "0.76.1",
        "0.76.1",
        "0.74.0",
    ]
    assert {(i.platform.os, i.platform.arch) for i in asset.versions} == {
        ("linux", "x86_64"),
        ("windows", "x86_64"),
    }

    security = store.groups.get("ci-security")
    release = store.groups.get("ci-release")
    # The same tool keeps one tool_id; per-group purpose text and member-level
    # aliases stay in their own member records.
    assert security.members[0].summary == ("Vulnerability and configuration scanning")
    assert security.members[0].aliases == ("vuln",)
    assert release.members[0].summary == "SBOM generation"
    assert release.members[0].aliases == ("sbom",)
    assert security.members[0].tool_id == release.members[0].tool_id == "trivy"

    entries = store.accesses.for_tool("trivy")
    assert [item.access_id for item in entries] == [
        "trivy.cli",
        "trivy.sbom",
        "trivy.scan",
    ]
    scan = store.accesses.get("trivy.scan")
    assert (scan.method, scan.target) == ("native", "trivy scan --exit-code 1")
    sbom = store.accesses.get("trivy.sbom")
    assert sbom.contract == {"dagger": "security_sbom", "args": {"format": "spdx"}}
    assert all(item.tool_id == "trivy" for item in entries)


def test_duplicate_primary_keys_conflict(store):
    with pytest.raises(RecordError, match="duplicate_tool_id"):
        store.assets.put(TRIVY)
    store.groups.put(ToolGroup("ci-security", "x", (GroupMember("trivy", "y"),)))
    with pytest.raises(RecordError, match="duplicate_group_id"):
        store.groups.put(ToolGroup("ci-security", "z", (GroupMember("trivy", "w"),)))
    store.accesses.put(access("trivy.scan", "native", "trivy scan"))
    with pytest.raises(RecordError, match="duplicate_access_id"):
        store.accesses.put(access("trivy.scan", "uv", "trivy"))


def test_foreign_key_rules_enforced_by_the_schema(store):
    # No ToolAsset → no associated ToolAccess, member or release row.
    with pytest.raises(RecordError, match="unknown_tool"):
        store.groups.put(ToolGroup("ci-x", "x", (GroupMember("absent", "why"),)))
    with pytest.raises(RecordError, match="unknown_tool"):
        store.accesses.put(access("absent.run", "native", "absent", tool_id="absent"))
    db = store._db
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tool_release VALUES"
            " ('absent','1','linux','x86_64',NULL,NULL,'https://e.invalid/a','sha256','"
            + "0" * 64
            + "')"
        )
    # One tool, several distinct entries — each with its own method, target
    # and contract; changing one entry's contract leaves the others alone.
    store.accesses.put(access("trivy.scan", "native", "trivy scan", contract={"a": 1}))
    store.accesses.put(access("trivy.image", "dagger", "scan_image", contract={"b": 2}))
    entries = {item.access_id: item for item in store.accesses.for_tool("trivy")}
    image, scan = entries["trivy.image"], entries["trivy.scan"]
    assert (image.method, image.target, image.contract) == (
        "dagger",
        "scan_image",
        {"b": 2},
    )
    assert (scan.method, scan.target, scan.contract) == (
        "native",
        "trivy scan",
        {"a": 1},
    )
    # A missing required field fails directly at insert.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tool_access VALUES ('t.x','trivy','native','t',NULL,'s')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO tool_asset VALUES ('t2','t2','uv',NULL,NULL)")


def test_record_level_validation_rejects_off_table_fields():
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAsset("trivy", "trivy", "npm", (TRIVY_LINUX,), "trivy")
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAssetVersion("1", "https://e.invalid/a", "md5", "0" * 64)
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAssetVersion("1", "https://e.invalid/a", "sha256", "short")
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAssetVersion("1", "https://e.invalid/a", "sha256", "g" * 64)
    with pytest.raises(RecordError, match="invalid_record"):
        Platform("linux", "")
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAsset("t", "t", "uv", (), "t")
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAccess("t.cli", "t", "shell", "t", {}, "s")
    with pytest.raises(RecordError, match="invalid_record"):
        ToolAccess("t.cli", "t", "native", "t", "not-a-mapping", "s")
    with pytest.raises(RecordError, match="duplicate_member"):
        ToolGroup("g", "s", (GroupMember("t", "a"), GroupMember("t", "b")))
    with pytest.raises(RecordError, match="duplicate_version"):
        ToolAsset("t", "t", "uv", (TRIVY_LINUX, TRIVY_LINUX), "t")


def test_member_aliases_live_only_at_the_member_level():
    """No group-level alias column exists; member aliases are their own
    table keyed (group_id, tool_id, alias), and a duplicate alias under the
    same membership is a primary-key conflict."""
    handle = open_record_store(":memory:")
    handle.assets.put(TRIVY)
    db = handle._db
    group_columns = tuple(row[1] for row in db.execute("PRAGMA table_info(tool_group)"))
    assert "aliases" not in group_columns
    member_columns = tuple(
        row[1] for row in db.execute("PRAGMA table_info(tool_group_member)")
    )
    assert member_columns == ("group_id", "tool_id", "summary")
    handle.groups.put(
        ToolGroup("ci-security", "s", (GroupMember("trivy", "scan", ("vuln",)),))
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tool_group_member_alias VALUES ('ci-security','trivy','vuln')"
        )
    # The same alias under another membership of the same tool is distinct.
    handle.groups.put(
        ToolGroup("ci-release", "r", (GroupMember("trivy", "sbom", ("vuln",)),))
    )
    both = (
        handle.groups.get("ci-security").members[0].aliases,
        handle.groups.get("ci-release").members[0].aliases,
    )
    assert both == (("vuln",), ("vuln",))
    handle.close()


def test_no_asset_id_column_exists_anywhere():
    """asset_id must not become a second tool identity synonymous with
    tool_id: the schema simply has no such column on any table."""
    handle = open_record_store(":memory:")
    db = handle._db
    for table in TABLE_COLUMNS:
        columns = tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
        assert "asset_id" not in columns, table
    handle.close()


def test_the_tables_themselves_enforce_the_field_constraints():
    """Bypass the gateways: raw SQL violating a field rule is stopped by the
    schema — the constraint lives in the tables, not the helpers."""
    handle = open_record_store(":memory:")
    db = handle._db
    db.execute("PRAGMA foreign_keys = ON")
    db.execute(
        "INSERT INTO tool_asset VALUES ('trivy','trivy','github-release',NULL,'trivy')"
    )
    rejections = [
        "INSERT INTO tool_asset VALUES ('t2','t2','npm',NULL,'t2')",
        "INSERT INTO tool_asset VALUES ('t3','',NULL,NULL,'t3')",
        "INSERT INTO tool_asset VALUES ('trivy','other','uv',NULL,'other')",
        "INSERT INTO tool_asset VALUES ('t4','t4','uv',NULL,NULL)",
        "INSERT INTO tool_release VALUES"
        " ('trivy','0.1','linux',NULL,NULL,NULL,'https://e.invalid/a','sha256','"
        + "0" * 64
        + "')",
        "INSERT INTO tool_release VALUES"
        " ('trivy','0.1',NULL,'x86_64',NULL,NULL,'https://e.invalid/a','sha256','"
        + "0" * 64
        + "')",
        (
            "INSERT INTO tool_release VALUES"
            " ('trivy','0.1','linux','x86_64',NULL,NULL,'https://e.invalid/a','sha256','tiny')"
        ),
        "INSERT INTO tool_release VALUES"
        " ('trivy','0.1','linux','x86_64',NULL,NULL,'https://e.invalid/a','sha512','"
        + "0" * 64
        + "')",
        "INSERT INTO tool_release VALUES"
        " ('absent','0.1','linux','x86_64',NULL,NULL,'https://e.invalid/a','sha256','"
        + "0" * 64
        + "')",
        "INSERT INTO tool_group_member VALUES ('no-group','trivy','s')",
        "INSERT INTO tool_access VALUES ('t.run','trivy','shell','t','{}','s')",
        "INSERT INTO tool_access VALUES ('t.run2','trivy','native','t','[]','s')",
        "INSERT INTO tool_access VALUES ('t.run3','absent','native','t','{}','s')",
    ]
    for statement in rejections:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(statement)
    # The parity columns are exactly the six-table field layout.
    for table, columns in TABLE_COLUMNS.items():
        actual = tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
        assert actual == columns, table
    handle.close()


def test_same_version_two_platforms_is_not_a_conflict(store):
    """tool_release uniqueness is (tool_id, version, platform): multi-platform
    assets share the version without becoming duplicates or new identities."""
    store.assets.put(
        ToolAsset(
            "osv-scanner",
            "osv-scanner",
            "github-release",
            (
                ToolAssetVersion(
                    "2.6.0",
                    "https://e.invalid/osv-linux",
                    "sha256",
                    "a" * 64,
                    Platform("linux", "x86_64"),
                ),
                ToolAssetVersion(
                    "2.6.0",
                    "https://e.invalid/osv-macos",
                    "sha256",
                    "b" * 64,
                    Platform("macos", "aarch64"),
                ),
            ),
            "osv-scanner",
        )
    )
    asset = store.assets.get("osv-scanner")
    assert [item.version for item in asset.versions] == ["2.6.0", "2.6.0"]
    db = store._db
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO tool_release VALUES"
            " ('osv-scanner','2.6.0','linux','x86_64',NULL,NULL,'https://other','sha256','"
            + "c" * 64
            + "')"
        )


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "records.sqlite3"
    handle = open_record_store(path)
    handle.assets.put(TRIVY)
    handle.groups.put(
        ToolGroup("ci-security", "s", (GroupMember("trivy", "scan", ("vuln",)),))
    )
    handle.close()
    again = open_record_store(path)
    assert again.assets.get("trivy").versions == TRIVY.versions
    assert again.groups.get("ci-security").members[0].aliases == ("vuln",)
    again.close()
    # A drifted schema (dropped column) is refused, not silently used.
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE tool_access DROP COLUMN summary")
    raw.commit()
    raw.close()
    with pytest.raises(RecordError, match="schema_drift"):
        open_record_store(path)


def test_platform_and_interpreter_constraints_are_real_fields():
    """deptry-shaped releases keep abi and interpreter constraints; same
    version and os/arch with a different ABI coexist instead of colliding."""
    handle = open_record_store(":memory:")
    gnu = ToolAssetVersion(
        "0.25.1",
        "https://e.invalid/deptry-gnu.whl",
        "sha256",
        "a" * 64,
        Platform("linux", "x86_64", "gnu"),
        ">=3.10",
    )
    musl = ToolAssetVersion(
        "0.25.1",
        "https://e.invalid/deptry-musl.whl",
        "sha256",
        "b" * 64,
        Platform("linux", "x86_64", "musl"),
        ">=3.10",
    )
    universal = ToolAssetVersion(
        "2.16",
        "https://e.invalid/vulture.whl",
        "sha256",
        "6e0f1c312cef1c87856957e5c2ca9608834a7c794c2180477f30bf0e4cc58eee",
        None,
        ">=3.9",
    )
    handle.assets.put(
        ToolAsset("deptry", "deptry", "uv", (gnu, musl), "deptry", package="deptry")
    )
    back = handle.assets.get("deptry")
    assert [(i.platform.abi, i.python) for i in back.versions] == [
        ("gnu", ">=3.10"),
        ("musl", ">=3.10"),
    ]
    handle.assets.put(ToolAsset("vulture", "vulture", "uv", (universal,), "vulture"))
    wheel = handle.assets.get("vulture").versions[0]
    assert wheel.platform is None and wheel.python == ">=3.9"
    assert record_document_of_universal(wheel)
    handle.close()


def record_document_of_universal(wheel):
    from vesryn_tool_runtime.discovery_records import (
        record_document,
        record_from_document,
    )

    document = record_document(
        ToolAsset("vulture", "vulture", "uv", (wheel,), "vulture")
    )
    return record_from_document(document).versions[0].python == ">=3.9"


def test_package_is_optional_and_stored_as_registered():
    """package may be absent; whatever was registered is returned verbatim."""
    handle = open_record_store(":memory:")
    handle.assets.put(
        ToolAsset(
            "vulture",
            "vulture",
            "uv",
            (
                ToolAssetVersion(
                    "2.16",
                    "https://files.pythonhosted.org/whl/vulture-2.16.whl",
                    "sha256",
                    "6e0f1c312cef1c87856957e5c2ca9608834a7c794c2180477f30bf0e4cc58eee",
                    None,
                ),
            ),
            "vulture",
        )
    )
    assert handle.assets.get("vulture").package is None
    handle.close()


def test_frozen_sql_is_a_package_resource_and_the_live_ddl():
    """The frozen DDL ships inside the package (independent installs work)
    and executing it produces exactly the parity tables."""
    import sqlite3
    from importlib.resources import files as resource_files

    import vesryn_tool_runtime

    names = {
        item.name for item in resource_files(vesryn_tool_runtime.__package__).iterdir()
    }
    assert SCHEMA_RESOURCE in names and SEED_RESOURCE in names
    db = sqlite3.connect(":memory:")
    db.executescript(schema_sql())
    for table, columns in TABLE_COLUMNS.items():
        actual = tuple(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
        assert actual == columns, table
    db.close()


def test_constraint_stripped_databases_are_refused(tmp_path):
    """Same column names without the constraints must fail the drift check —
    column-name parity alone proves nothing."""
    import sqlite3

    stripped = tmp_path / "stripped.sqlite3"
    db = sqlite3.connect(stripped)
    db.executescript(
        "CREATE TABLE tool_asset (tool_id TEXT, name TEXT, provider TEXT,"
        " package TEXT, entrypoint TEXT);"
        "CREATE TABLE tool_release (tool_id TEXT, version TEXT, platform_os TEXT,"
        " platform_arch TEXT, platform_abi TEXT, platform_python TEXT,"
        " source TEXT, digest_type TEXT, digest TEXT);"
        "CREATE TABLE tool_group (group_id TEXT, summary TEXT);"
        "CREATE TABLE tool_group_member (group_id TEXT, tool_id TEXT, summary TEXT);"
        "CREATE TABLE tool_group_member_alias (group_id TEXT, tool_id TEXT,"
        " alias TEXT);"
        "CREATE TABLE tool_access (access_id TEXT, tool_id TEXT, method TEXT,"
        " target TEXT, contract TEXT, summary TEXT);"
    )
    db.execute("PRAGMA user_version = 2")
    db.commit()
    db.close()
    with pytest.raises(RecordError, match="schema_drift"):
        open_record_store(stripped)


def test_committed_library_round_trips_the_seeded_examples():
    """data/records.sqlite3 — built from the frozen schema and seed.sql —
    opens through the public gateways and returns the issue's literal
    examples exactly."""
    path = Path(__file__).resolve().parents[1] / "data" / "records.sqlite3"
    handle = open_record_store(path)
    asset = handle.assets.get("trivy")
    assert (asset.provider, asset.entrypoint) == ("github-release", "trivy")
    (release,) = asset.versions
    assert release.version == "0.76.1"
    assert (release.platform.os, release.platform.arch) == ("linux", "x86_64")
    assert release.digest == (
        "c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0"
    )

    security = handle.groups.get("ci-security")
    release_group = handle.groups.get("ci-release")
    assert security.members[0].summary == ("Vulnerability and configuration scanning")
    assert security.members[0].aliases == ("vuln",)
    assert release_group.members[0].summary == "SBOM generation"
    assert release_group.members[0].aliases == ("sbom",)

    entries = {item.access_id: item for item in handle.accesses.for_tool("trivy")}
    assert set(entries) == {"trivy.scan", "trivy.sbom", "trivy.cli"}
    assert entries["trivy.scan"].method == "native"
    assert entries["trivy.sbom"].method == "dagger"
    assert entries["trivy.sbom"].contract == {
        "dagger": "security_sbom",
        "args": {"format": "spdx"},
    }
    assert entries["trivy.cli"].method == "uv"
    handle.close()
