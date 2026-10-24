"""Shared definition reads and explicit assembly keep existing identities stable."""

import hashlib

import pytest

from vesryn_tool_runtime import (
    AssetDefinition,
    AssetError,
    AssetPolicy,
    AssetTarget,
    Catalog,
    DiscoveryScope,
    SharedAssetDefinition,
    ToolResult,
    ToolRuntimeError,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)
from vesryn_tool_runtime.documents import write

TARGET = AssetTarget("windows", "x86_64", abi="gnu")
POLICY = AssetPolicy("approved-1")


class RecordingAdapter:
    """A consumer-supplied adapter; shared reads and assembly never reach it."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def release(version="2.0", **changes):
    value = {
        "version": version,
        "distribution": "native",
        "backend": "aria2",
        "source": f"https://example.invalid/tool-{version}.zip",
        "sha256": hashlib.sha256(version.encode()).hexdigest(),
        "entrypoint": "tool.exe",
        "os": "windows",
        "arch": "x86_64",
        "abi": "gnu",
    }
    value.update(changes)
    return value


def asset(
    asset_id="shared.cli", revision="published-1", tools=("shared.read",), releases=None
):
    return {
        "asset_id": asset_id,
        "catalog_revision": revision,
        "tools": list(tools),
        "releases": list(
            releases if releases is not None else (release(), release("1.0"))
        ),
    }


def document(*assets):
    return {
        "schema_version": 1,
        "kind": "shared-asset-definitions",
        "assets": list(assets),
    }


def catalog(*tool_ids, provider="sample-domain"):
    tools = Catalog()
    tools.provider_name = provider
    for tool_id in tool_ids:
        tools.register(ToolSpec(tool_id, {}, {}, effect="read"), RecordingAdapter())
    return tools


def store(tmp_path, value, name="shared.json"):
    path = tmp_path / name
    write(path, value)
    return path


def test_read_is_pure_and_needs_no_catalog_or_consumer_environment(tmp_path):
    path = store(tmp_path, document(asset(tools=("shared.read", "shared.scan"))))
    before = sorted(item.name for item in tmp_path.iterdir())
    records = load_shared_definitions(path)
    assert sorted(item.name for item in tmp_path.iterdir()) == before
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, SharedAssetDefinition)
    assert isinstance(record.definition, AssetDefinition)
    assert record.definition.asset_id == "shared.cli"
    assert record.tools == ("shared.read", "shared.scan")
    assert load_shared_definitions(str(path)) == records


def test_bundled_documents_load_and_bundled_names_take_precedence(
    tmp_path, monkeypatch
):
    names = shared_definition_documents()
    assert names and names == tuple(sorted(names)) and len(set(names)) == len(names)
    assert "examples.json" in names
    for name in names:
        records = load_shared_definitions(name)
        assert records and all(
            isinstance(item, SharedAssetDefinition) for item in records
        )
    bundled = load_shared_definitions("examples.json")
    monkeypatch.chdir(tmp_path)
    write(tmp_path / "examples.json", document(asset(tools=("other.read",))))
    # A bundled name resolves to the shipped document, never a neighbor file.
    assert load_shared_definitions("examples.json") == bundled


def test_assembly_reuses_existing_registration_and_conflict_reasons(tmp_path):
    records = load_shared_definitions(store(tmp_path, document(asset())))
    tools = catalog("shared.read")
    register_shared_definitions(tools, records)
    assert tools.asset_for("shared.read") is records[0].definition
    spec, _ = tools.resolve("shared.read")
    selection = tools.select_asset("shared.read", target=TARGET, policy=POLICY)
    assert selection.tool_contract_sha256 == spec.sha256
    assert tools.provider_for("shared.read") == "sample-domain"
    # Registration no longer needs a capability: an empty catalog takes the
    # same records directly, by tool primary key (#32).
    empty = catalog()
    register_shared_definitions(empty, records)
    assert empty.asset_for("shared.read") is records[0].definition
    with pytest.raises(AssetError, match="unregistered_tool"):
        empty.select_asset("shared.read", target=TARGET, policy=POLICY)
    with pytest.raises(AssetError, match="conflicting_asset"):
        register_shared_definitions(
            tools,
            load_shared_definitions(
                store(
                    tmp_path,
                    document(asset(revision="other", releases=(release("3.0"),))),
                    name="conflict.json",
                )
            ),
        )
    bare = catalog("shared.read", "bare.tool")
    with pytest.raises(AssetError, match="unregistered_asset"):
        bare.asset_for("bare.tool")
    with pytest.raises(ToolRuntimeError, match="Catalog"):
        register_shared_definitions(object(), records)
    with pytest.raises(AssetError, match="invalid_definition"):
        register_shared_definitions(tools, ("not-a-record",))


def test_one_asset_serves_many_capabilities_and_ids_survive_publication_changes(
    tmp_path,
):
    records = load_shared_definitions(
        store(tmp_path, document(asset(tools=("shared.read", "shared.scan"))))
    )
    tools = catalog("shared.read", "shared.scan")
    register_shared_definitions(tools, records)
    assert tools.asset_for("shared.read") is tools.asset_for("shared.scan")
    first = tools.select_asset("shared.read", target=TARGET, policy=POLICY)
    second = tools.select_asset("shared.scan", target=TARGET, policy=POLICY)
    assert first.asset_id == second.asset_id == "shared.cli"
    assert first.artifact_id == second.artifact_id
    assert first.tool_id != second.tool_id
    # Version, platform and install-location changes never reassign identities.
    revised = document(
        asset(
            revision="published-2",
            releases=(
                release("3.0"),
                release("3.0", os="linux"),
                release(),
                release("1.0"),
            ),
        )
    )
    later = catalog("shared.read", "shared.scan")
    register_shared_definitions(
        later, load_shared_definitions(store(tmp_path, revised, name="revised.json"))
    )
    assert later.asset_for("shared.read").asset_id == "shared.cli"
    current = later.select_asset("shared.read", target=TARGET, policy=POLICY)
    linux = later.select_asset(
        "shared.read", target=AssetTarget("linux", "x86_64", abi="gnu"), policy=POLICY
    )
    assert current.release.version == linux.release.version == "3.0"
    assert current.asset_id == linux.asset_id == "shared.cli"


def test_identical_redeclaration_is_idempotent_across_documents(tmp_path):
    first = load_shared_definitions(store(tmp_path, document(asset()), name="a.json"))
    second = load_shared_definitions(store(tmp_path, document(asset()), name="b.json"))
    tools = catalog("shared.read")
    register_shared_definitions(tools, first)
    register_shared_definitions(tools, second)
    assert tools.asset_for("shared.read") == first[0].definition


def test_assembly_does_not_change_provider_or_scope_semantics(tmp_path):
    records = load_shared_definitions(store(tmp_path, document(asset())))
    tools = catalog("shared.read")
    register_shared_definitions(tools, records)
    scoped = DiscoveryScope(environment="host", permissions=frozenset({"write"}))
    with pytest.raises(ToolRuntimeError, match="scope"):
        tools.asset_for("shared.read", scope=scoped)
    admitted = DiscoveryScope(environment="host", permissions=frozenset({"read"}))
    assert tools.asset_for("shared.read", scope=admitted).asset_id == "shared.cli"
    assert (
        tools.select_asset(
            "shared.read", target=TARGET, policy=POLICY, scope=admitted
        ).asset_id
        == "shared.cli"
    )


@pytest.mark.parametrize(
    "value,reason",
    [
        (document(), "invalid_definition"),
        (
            {"schema_version": 2, "kind": "shared-asset-definitions", "assets": []},
            "invalid_definition",
        ),
        (
            {"schema_version": 1, "kind": "other-kind", "assets": [asset()]},
            "invalid_definition",
        ),
        (
            {"schema_version": 1, "kind": "shared-asset-definitions"},
            "invalid_definition",
        ),
        (
            {
                "schema_version": True,
                "kind": "shared-asset-definitions",
                "assets": [asset()],
            },
            "invalid_definition",
        ),
        ({"extra": 1, **document(asset())}, "invalid_definition"),
        (document({**asset(), "provenance": "publisher"}), "invalid_definition"),
        (document({**asset(), "tools": []}), "invalid_definition"),
        (document({**asset(), "tools": {"shared.read": True}}), "invalid_definition"),
        (document(list(asset().items())), "invalid_definition"),
        (
            document({**asset(), "tools": ["shared.read", "shared.read"]}),
            "invalid_definition",
        ),
        (document({**asset(), "tools": ["not a tool id"]}), "invalid_definition"),
        (document({**asset(), "releases": []}), "invalid_definition"),
        (
            document(asset(), asset(revision="other", releases=(release("9.0"),))),
            "conflicting_asset",
        ),
        (
            document({**asset(), "releases": [{**release(), "version": "latest"}]}),
            "mutable_version",
        ),
    ],
)
def test_unknown_or_invalid_documents_keep_explicit_reasons(tmp_path, value, reason):
    with pytest.raises(AssetError, match=reason):
        load_shared_definitions(store(tmp_path, value))


def test_bounded_document_reading_rejects_duplicate_fields(tmp_path):
    path = tmp_path / "shared.json"
    path.write_bytes(
        b'{"schema_version": 1, "schema_version": 1,'
        b' "kind": "shared-asset-definitions", "assets": []}'
    )
    with pytest.raises(ToolRuntimeError):
        load_shared_definitions(path)
    with pytest.raises(ToolRuntimeError):
        load_shared_definitions(17)


def test_bundled_seed_registers_directly_without_placeholder_capabilities():
    records = {
        record.definition.asset_id: record
        for record in load_shared_definitions("examples.json")
    }
    assert set(records) == {"cli.ripgrep", "hyperfine"}
    # The seed tools are bare program primary keys; they register directly in
    # a catalog with no ToolSpec or placeholder capability, and acquisition
    # keeps failing explicitly until a real contract exists.
    tools = Catalog()
    register_shared_definitions(tools, records.values())
    for tool_id in ("ripgrep", "hyperfine"):
        assert tools.asset_for(tool_id).asset_id in records
        with pytest.raises(AssetError, match="unregistered_tool"):
            tools.select_asset(tool_id, target=TARGET, policy=POLICY)


def test_unified_registration_supports_groups_entries_and_key_conflicts():
    from vesryn_tool_runtime import AccessEntrySummary, ToolAsset, ToolGroup
    from vesryn_tool_runtime.discovery_contracts import compose_access_id

    trivy = next(
        record
        for record in load_shared_definitions("security.json")
        if record.definition.asset_id == "trivy"
    )
    tools = Catalog()
    # A real tool registers directly as a ToolAsset: no empty ToolSpec, no
    # example.* capability, and no fabricated executable entry.
    tools.register_tool(ToolAsset("trivy", trivy.definition))
    assert tools.asset_for("trivy") is trivy.definition
    with pytest.raises(AssetError, match="unregistered_tool"):
        tools.select_asset("trivy", target=TARGET, policy=POLICY)

    # The same tool primary key joins two groups with several entries.
    scanners = ToolGroup(
        "security.scanners",
        ("trivy",),
        display_name="Security scanners",
        aliases=("vuln",),
    )
    all_tools = ToolGroup("security.all-tools", ("trivy",))
    tools.register_group(scanners)
    tools.register_group(all_tools)
    assert tools.group_for("security.scanners") is scanners
    assert tools.group_for("security.all-tools").members == ("trivy",)
    with pytest.raises(ToolRuntimeError, match="unregistered tools"):
        tools.register_group(ToolGroup("broken.group", ("absent-tool",)))
    with pytest.raises(ToolRuntimeError, match="Duplicate tool group"):
        tools.register_group(
            ToolGroup("security.scanners", ("trivy",), description="Different")
        )

    def entry(key, environment):
        return AccessEntrySummary(
            tool_id="trivy",
            catalog_ref="ci",
            entry_key=key,
            provider="engineering-ci",
            environment=environment,
            purpose="Scan container images and filesystems",
            contract_version="1",
            contract_sha256=trivy.definition.releases[0].sha256,
            discovery_scope="matched",
        )

    first, second = entry("default", "dagger"), entry("fallback", "host")
    assert first.access_id == compose_access_id("ci", "trivy", "default")
    tools.register_access(first)
    tools.register_access(second)
    assert tools.access_for(first.access_id) is first
    assert tools.access_for(second.access_id).entry_key == "fallback"
    with pytest.raises(ToolRuntimeError, match="unregistered tool"):
        tools.register_access(
            AccessEntrySummary(
                tool_id="absent-tool",
                catalog_ref="ci",
                entry_key="default",
                provider="engineering-ci",
                environment="dagger",
                purpose="Never registered",
                contract_version="1",
                contract_sha256=trivy.definition.releases[0].sha256,
                discovery_scope="matched",
            )
        )
    with pytest.raises(ToolRuntimeError, match="Duplicate access entry"):
        tools.register_access(entry("default", "host"))

    # Explicit composition carries groups and entries and rejects duplicates.
    other = Catalog()
    other.register_tool(ToolAsset("trivy", trivy.definition))
    other.register_group(all_tools)
    with pytest.raises(ToolRuntimeError, match="Duplicate tool group"):
        tools.merge(other)


def test_composition_carries_groups_and_access_entries():
    from vesryn_tool_runtime import AccessEntrySummary, ToolAsset, ToolGroup
    from vesryn_tool_runtime.registry import scoped_catalog

    source = Catalog()
    source.register_tool(
        ToolAsset(
            "shellcheck",
            next(
                record.definition
                for record in load_shared_definitions("native.json")
                if record.definition.asset_id == "shellcheck"
            ),
        )
    )
    source.register_group(ToolGroup("shell.quality", ("shellcheck",), aliases=("sh",)))
    entry = AccessEntrySummary(
        tool_id="shellcheck",
        catalog_ref="ci",
        entry_key="default",
        provider="engineering-ci",
        environment="dagger",
        purpose="Shell script analysis",
        contract_version="1",
        contract_sha256="0" * 64,
        discovery_scope="matched",
    )
    source.register_access(entry)

    combined = Catalog()
    combined.merge(source)
    assert combined.group_for("shell.quality").aliases == ("sh",)
    assert combined.access_for(entry.access_id) is entry

    guarded = scoped_catalog(combined, DiscoveryScope(permissions=frozenset({"check"})))
    assert guarded.group_for("shell.quality") is combined.group_for("shell.quality")
    assert guarded.access_for(entry.access_id) is entry
    assert guarded.asset_for("shellcheck") is combined.asset_for("shellcheck")
