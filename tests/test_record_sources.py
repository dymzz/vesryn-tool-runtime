"""Live-declaration loading, registration and composition (issue #32)."""

import sqlite3
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    ComposedCatalog,
    GroupMember,
    RecordError,
    ToolAccess,
    ToolAsset,
    ToolGroup,
    bundled_records,
    compose_catalog,
    legacy_preparation_definitions,
    open_record_store,
    record_document,
    record_from_document,
)
from vesryn_tool_runtime.record_schema import schema_sql, seed_sql

COMMITTED_LIBRARY = Path(__file__).resolve().parents[1] / "data" / "records.sqlite3"

# Verified publisher values the live declaration must carry (previously
# pinned per JSON document; the seed is now the single pinning place).
EXPECTED_TOOLS = {
    "trivy": ("github-release", 2),
    "vulture": ("uv", 2),
    "hyperfine": ("github-release", 4),
    "ripgrep": ("github-release", 2),
    "osv-scanner": ("github-release", 2),
    "actionlint": ("github-release", 2),
    "shellcheck": ("github-release", 2),
    "zizmor": ("github-release", 2),
    "semgrep": ("oci", 2),
    "lychee": ("oci", 2),
    "pyright": ("uv", 1),
    "deptry": ("uv", 2),
    "pylint": ("uv", 1),
    "import-linter": ("uv", 1),
    "hypothesis": ("uv", 2),
    "mutmut": ("uv", 1),
    "schemathesis": ("uv", 1),
    "pytest-timeout": ("uv", 1),
    "pytest-randomly": ("uv", 1),
    "pytest-xdist": ("uv", 1),
    "beartype": ("uv", 1),
    "typeguard": ("uv", 1),
    "pytest-cov": ("uv", 1),
    "memray": ("uv", 2),
    "py-spy": ("uv", 2),
    "tach": ("uv", 2),
}
VULTURE_214_URL = (
    "https://files.pythonhosted.org/packages/a0/56/0cc15b8ff2613c1d5c3"
    "dc1f3f576ede1c43868c1bc2e5ccaa2d4bcd7974d/"
    "vulture-2.14-py2.py3-none-any.whl"
)
DEPTRY_DIGEST = "14bfcc28b4326ed8c6abb30691b19077d4ef8613cfba6c37ef5b1f471775bf6f"
SEMGREP_AMD64 = "374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d"
HYPERFINE_LINUX_200 = "ae2beda2ac99c098427e4f755244552daf20e514422889cca6d44421e2d93c87"


def test_bundled_declaration_is_complete_and_reads_without_a_store():
    records = bundled_records()
    assets = [r for r in records if isinstance(r, ToolAsset)]
    providers = {r.tool_id: (r.provider, len(r.versions)) for r in assets}
    for tool_id, expected in EXPECTED_TOOLS.items():
        assert providers[tool_id] == expected, tool_id
    assert len(providers) == len(EXPECTED_TOOLS)
    # Pure read: every record round-trips through its document.
    for record in records:
        assert record_from_document(record_document(record)) == record


def test_migration_kept_the_real_preparation_facts():
    records = bundled_records()
    assets = {r.tool_id: r for r in records if isinstance(r, ToolAsset)}
    vulture = assets["vulture"].versions
    assert {(i.version, i.python) for i in vulture} == {
        ("2.16", ">=3.9"),
        ("2.14", ">=3.8"),
    }
    assert vulture[1].source == VULTURE_214_URL
    deptry = assets["deptry"].versions[0]
    assert (deptry.platform.os, deptry.platform.arch, deptry.platform.abi) == (
        "linux",
        "x86_64",
        "gnu",
    )
    assert deptry.python == ">=3.10" and deptry.digest == DEPTRY_DIGEST
    hyperfine = assets["hyperfine"].versions
    assert {(i.version, i.platform.os, i.platform.arch) for i in hyperfine} == {
        ("2.0.0", "windows", "x86_64"),
        ("2.0.0", "linux", "x86_64"),
        ("1.20.0", "windows", "x86_64"),
        ("1.20.0", "linux", "x86_64"),
    }
    assert any(i.digest == HYPERFINE_LINUX_200 for i in hyperfine)
    semgrep = assets["semgrep"].versions
    assert {(i.platform.os, i.platform.arch) for i in semgrep} == {
        ("linux", "x86_64"),
        ("linux", "aarch64"),
    }
    assert any(i.digest == SEMGREP_AMD64 for i in semgrep)
    assert all(i.source.endswith("@sha256:" + i.digest) for i in semgrep)


def test_same_tool_id_across_groups_and_entries_without_placeholders():
    catalog = compose_catalog(bundled_records())
    groups = [
        group
        for group in catalog.groups()
        if any(member.tool_id == "trivy" for member in group.members)
    ]
    assert [group.group_id for group in groups] == [
        "ci-release",
        "ci-security",
    ]
    # Group-local purpose text and member-level aliases survive per group.
    by_group = {g.group_id: g for g in groups}
    assert by_group["ci-security"].members[0].summary == (
        "Vulnerability and configuration scanning"
    )
    assert by_group["ci-release"].members[0].aliases == ("sbom",)
    entries = catalog.accesses_for("trivy")
    assert [entry.access_id for entry in entries] == [
        "trivy.cli",
        "trivy.sbom",
        "trivy.scan",
    ]
    scan = catalog.access("trivy.scan")
    assert (scan.method, scan.target) == ("native", "trivy scan --exit-code 1")
    sbom = catalog.access("trivy.sbom")
    assert sbom.method == "dagger" and sbom.contract["args"] == {"format": "spdx"}


def test_composition_dedups_identical_and_conflicts_on_difference():
    records = bundled_records()
    trivy = catalog_record(records, "trivy")
    merged = compose_catalog(records, (trivy,), [trivy])
    assert len(merged.tools()) == len(compose_catalog(records).tools())
    other = ToolAsset(
        trivy.tool_id,
        trivy.name,
        trivy.provider,
        trivy.versions,
        trivy.entrypoint,
        package="different",
    )
    with pytest.raises(RecordError, match="duplicate_tool_id"):
        compose_catalog(records, (other,))


def catalog_record(records, tool_id):
    return next(
        record
        for record in records
        if isinstance(record, ToolAsset) and record.tool_id == tool_id
    )


def test_registration_needs_no_capability_and_distinguishes_missing():
    store = open_record_store(":memory:")
    store.put_records(bundled_records())
    assert store.assets.get("deptry").provider == "uv"
    # A registered tool without entries is not an error and not a failure.
    assert store.accesses.for_tool("deptry") == ()
    with pytest.raises(RecordError, match="unknown_tool"):
        store.accesses.for_tool("absent")
    store.close()


def test_batch_registration_is_atomic_with_explicit_outcomes(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = open_record_store(path)
    records = bundled_records()
    # Idempotent identical batch.
    store.put_records(records)
    store.put_records(records[:5])
    assert len(store.assets.all()) == len(compose_catalog(records).tools())
    # Conflicting content rolls the whole batch back.
    trivy = catalog_record(records, "trivy")
    conflicting = ToolAsset(
        trivy.tool_id, trivy.name, trivy.provider, trivy.versions, "other-binary"
    )
    with pytest.raises(RecordError, match="duplicate_tool_id"):
        store.put_records([conflicting, catalog_record(records, "vulture")])
    assert store.assets.get("trivy").entrypoint == "trivy"
    # Invalid foreign key: nothing partial survives.
    with pytest.raises(RecordError, match="unknown_tool"):
        store.put_records([ToolAccess("x.run", "absent", "native", "x", {"i": 1}, "s")])
    left = store._db.execute(
        "SELECT count(*) FROM tool_access WHERE access_id='x.run'"
    ).fetchone()[0]
    assert left == 0
    store.close()


def test_reads_never_touch_persistent_state(tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    catalog = compose_catalog(bundled_records())
    catalog.asset("trivy")
    catalog.accesses_for("trivy")
    legacy_preparation_definitions()
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not (Path.cwd() / "records.sqlite3").exists()


def test_committed_library_matches_the_bundled_declaration():
    store = open_record_store(COMMITTED_LIBRARY)
    try:
        seed = sqlite3.connect(":memory:")
        seed.executescript(schema_sql())
        seed.executescript(seed_sql())
        for table in (
            "tool_asset",
            "tool_release",
            "tool_group",
            "tool_group_member",
            "tool_group_member_alias",
            "tool_access",
        ):
            expected = seed.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            actual = store._db.execute(
                f"SELECT * FROM {table} ORDER BY 1, 2"
            ).fetchall()
            assert actual == expected, table
        seed.close()
    finally:
        store.close()


def test_legacy_view_serves_the_old_preparation_callers():
    definitions = {d.asset_id: d for d in legacy_preparation_definitions()}
    assert set(definitions) == {
        r.tool_id for r in bundled_records() if isinstance(r, ToolAsset)
    }
    vulture = definitions["vulture"]
    assert [r.version for r in vulture.releases] == ["2.16", "2.14"]
    assert all(r.backend == "uv" for r in vulture.releases)
    hyperfine = definitions["hyperfine"]
    assert len(hyperfine.releases) == 4
    assert all(r.backend == "aria2" for r in hyperfine.releases)
    semgrep = definitions["semgrep"]
    assert all(r.backend == "oci" for r in semgrep.releases)


def test_composed_catalog_type_and_missing_errors():
    catalog = compose_catalog(bundled_records())
    assert isinstance(catalog, ComposedCatalog)
    for getter, key, code in (
        (catalog.asset, "absent", "unknown_tool"),
        (catalog.group, "absent", "unknown_group"),
        (catalog.access, "absent.run", "unknown_access"),
    ):
        with pytest.raises(RecordError, match=code):
            getter(key)


def test_composition_rejects_dangling_references_after_merge():
    """A member or entry whose tool is absent from every named source is
    refused over the merged catalog; a cross-source reference (tool from one
    source, group from another) resolves fine."""
    records = bundled_records()
    trivy_asset = catalog_record(records, "trivy")
    ghost_group = ToolGroup(
        "ghost-group", "dangling", (GroupMember("ghost", "no such tool", ()),)
    )
    ghost_access = ToolAccess("ghost.cli", "ghost", "native", "ghost", {"i": 1}, "s")
    with pytest.raises(RecordError, match="unknown_tool"):
        compose_catalog(records, (ghost_group,))
    with pytest.raises(RecordError, match="unknown_tool"):
        compose_catalog(records, (ghost_access,))
    # Cross-source reference: the tool comes from one source, the group
    # referencing it from another — valid because the MERGED catalog has both.
    group = ToolGroup(
        "ci-extra", "extra", (GroupMember("trivy", "from another source", ()),)
    )
    merged = compose_catalog((trivy_asset,), (group,))
    assert merged.group("ci-extra").members[0].tool_id == "trivy"


def test_alias_registration_is_order_insensitive_and_idempotent():
    """The same member registered with aliases in any input order is one
    canonical record: storage, documents, equality and re-registration all
    agree; a genuinely different alias set still conflicts."""
    member = GroupMember("trivy", "scan", ("z", "a"))
    assert member.aliases == ("a", "z")
    group = ToolGroup("ci-order", "s", (member,))
    store = open_record_store(":memory:")
    store.put_records(bundled_records())
    store.put_records((group,))
    # Re-submit the ORIGINAL input order: same canonical record, idempotent.
    original = ToolGroup("ci-order", "s", (GroupMember("trivy", "scan", ("z", "a")),))
    store.put_records((original,))
    assert store.groups.get("ci-order").members[0].aliases == ("a", "z")
    assert record_from_document(
        record_document(store.groups.get("ci-order"))
    ) == store.groups.get("ci-order")
    different = ToolGroup(
        "ci-order", "s", (GroupMember("trivy", "scan", ("a", "z", "m")),)
    )
    with pytest.raises(RecordError, match="duplicate_group_id"):
        store.put_records((different,))
    store.close()


def test_native_delivery_entry_passes_source_artifact_to_backend(monkeypatch, tmp_path):
    """Regression for the args.source_art typo: with valid CLI choices the
    run reaches the backend, and the declared --source-artifact value is
    the one handed to prepare(). Restoring the old typo must fail this —
    the AttributeError fires before any backend call."""
    import importlib.util
    import sys
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "native_delivery_entry",
        Path(__file__).resolve().parents[1] / "examples" / "native_asset_delivery.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured = {}

    def stub_prepare(
        self, selection, *, policy, allow_network=False, source_artifact=None
    ):
        captured["selection"] = selection
        captured["source_artifact"] = source_artifact
        return SimpleNamespace(
            document=lambda: {"stub": True},
            outcome=SimpleNamespace(status="failed", exit_code=3, reason="stub"),
        )

    monkeypatch.setattr(module.Aria2NativeBackend, "prepare", stub_prepare)
    stub = tmp_path / "aria2c.exe"
    stub.write_bytes(b"stub")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "native_asset_delivery.py",
            "--asset",
            "hyperfine",
            "--version",
            "2.0.0",
            "--os",
            "linux",
            "--arch",
            "x86_64",
            "--abi",
            "gnu",
            "--root",
            str(tmp_path / "root"),
            "--aria2",
            str(stub),
            "--aria2-version",
            "1.37.0",
            "--aria2-sha256",
            "0" * 64,
            "--policy-revision",
            "regression",
            "--source-artifact",
            str(stub),
        ],
    )
    assert module.main() == 3
    assert captured["selection"].asset_id == "hyperfine"
    from pathlib import Path as _Path

    assert _Path(captured["source_artifact"]) == stub
