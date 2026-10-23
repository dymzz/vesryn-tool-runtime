"""Native/workflow shared assets: verified declarations, targets and relations."""

import json
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    AssetError,
    AssetPolicy,
    AssetTarget,
    Catalog,
    SharedAssetDefinition,
    ToolResult,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)

LINUX = AssetTarget("linux", "x86_64", abi="gnu")
POLICY = AssetPolicy("native-shared-1")

# Publisher GitHub Release asset digests, verified 2026-10-24 (osv-scanner
# re-checked unchanged from the 2026-10-23 #8 verification; actionlint also
# cross-checked against the publisher's checksums.txt).
VERIFIED = {
    "osv-scanner": {
        "version": "2.6.0",
        "source": (
            "https://github.com/google/osv-scanner/releases/download/"
            "v2.6.0/osv-scanner_linux_amd64"
        ),
        "sha256": "ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108",
        "entrypoint": "osv-scanner",
        "abi": None,
        "tools": ("dependency.vulnerability-scan",),
        "revision": "official-2026-10-23",
    },
    "actionlint": {
        "version": "1.7.12",
        "source": (
            "https://github.com/rhysd/actionlint/releases/download/"
            "v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz"
        ),
        "sha256": "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8",
        "entrypoint": "actionlint",
        "abi": None,
        "tools": ("example.actionlint",),
        "revision": "official-2026-10-24",
    },
    "shellcheck": {
        "version": "0.11.0",
        "source": (
            "https://github.com/koalaman/shellcheck/releases/download/"
            "v0.11.0/shellcheck-v0.11.0.linux.x86_64.tar.xz"
        ),
        "sha256": "8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198",
        "entrypoint": "shellcheck",
        "abi": None,
        "tools": ("example.shellcheck",),
        "revision": "official-2026-10-24",
    },
    "zizmor": {
        "version": "1.31.1",
        "source": (
            "https://github.com/woodruffw/zizmor/releases/download/"
            "v1.31.1/zizmor-x86_64-unknown-linux-gnu.tar.gz"
        ),
        "sha256": "d185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99",
        "entrypoint": "zizmor",
        "abi": "gnu",
        "tools": ("example.zizmor",),
        "revision": "official-2026-10-24",
    },
}


class RecordingAdapter:
    """A consumer-supplied adapter; shared definitions never reach it here."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def native_records():
    assert "native.json" in shared_definition_documents()
    return {r.definition.asset_id: r for r in load_shared_definitions("native.json")}


def native_catalog(*tool_ids):
    tools = Catalog()
    tools.provider_name = "native-shared"
    for tool_id in tool_ids:
        tools.register(ToolSpec(tool_id, {}, {}, effect="check"), RecordingAdapter())
    return tools


def all_declared_tools():
    return sorted(
        {tool for record in native_records().values() for tool in record.tools}
    )


def test_four_definitions_carry_verified_publisher_digests():
    records = native_records()
    assert set(records) == set(VERIFIED)
    for asset_id, expected in VERIFIED.items():
        record = records[asset_id]
        assert isinstance(record, SharedAssetDefinition)
        assert record.tools == expected["tools"]
        assert record.definition.catalog_revision == expected["revision"]
        (release,) = record.definition.releases
        assert release.version == expected["version"]
        assert release.source == expected["source"]
        assert release.sha256 == expected["sha256"]
        assert release.entrypoint == expected["entrypoint"]
        assert (release.os, release.arch, release.abi) == (
            "linux",
            "x86_64",
            expected["abi"],
        )
        assert release.distribution == "native" and release.backend == "aria2"


def test_osv_relation_and_release_reuse_the_verified_delivery():
    record = native_records()["osv-scanner"]
    # The capability relation is the real one ECI #51 already consumed; the
    # release is the exact #8-verified declaration, not a second authority.
    assert record.tools == ("dependency.vulnerability-scan",)
    (release,) = record.definition.releases
    provenance = json.loads(
        (Path(__file__).parent.parent / "examples/native-assets.json").read_text(
            encoding="utf-8"
        )
    )["provenance"]
    osv = next(item for item in provenance if item["asset_id"] == "osv-scanner")
    assert release.sha256 == osv["sha256"] and osv["rechecked_on"] == "2026-10-24"


@pytest.mark.parametrize("asset_id", ["actionlint", "shellcheck", "zizmor"])
def test_new_tools_target_linux_only_and_stay_unassembled_examples(asset_id):
    record = native_records()[asset_id]
    # No formal ECI capability exists yet (ECI #58 owns the real check
    # entries); the example association cannot masquerade as one.
    assert record.tools[0].startswith("example.")
    tools = native_catalog(record.tools[0])
    register_shared_definitions(tools, record)
    selection = tools.select_asset(record.tools[0], target=LINUX, policy=POLICY)
    assert selection.asset_id == asset_id
    with pytest.raises(AssetError, match="unsupported_target"):
        tools.select_asset(
            record.tools[0],
            target=AssetTarget("windows", "x86_64", abi="msvc"),
            policy=POLICY,
        )
    if asset_id == "zizmor":
        # The glibc-targeted build requires an exact ABI match.
        with pytest.raises(AssetError, match="unsupported_target"):
            tools.select_asset(
                record.tools[0],
                target=AssetTarget("linux", "x86_64"),
                policy=POLICY,
            )


def test_assembly_selects_all_four_through_the_public_interface():
    tools = native_catalog(*all_declared_tools())
    register_shared_definitions(tools, native_records().values())
    for asset_id, record in native_records().items():
        for tool_id in record.tools:
            selection = tools.select_asset(tool_id, target=LINUX, policy=POLICY)
            assert selection.asset_id == asset_id
            assert selection.release.sha256 == VERIFIED[asset_id]["sha256"]
            assert selection.tool_contract_sha256 == tools.resolve(tool_id)[0].sha256
    osv = tools.select_asset(
        "dependency.vulnerability-scan", target=LINUX, policy=POLICY
    )
    assert osv.asset_id == "osv-scanner" and osv.release.version == "2.6.0"


def test_shared_registration_grants_nothing_without_real_capabilities():
    records = native_records()
    tools = native_catalog("example.actionlint", "example.shellcheck")
    # Assembling the whole document needs every declared capability to exist.
    with pytest.raises(AssetError, match="unregistered_tool"):
        register_shared_definitions(tools, records.values())
    # A capability without any asset keeps its existing explicit answer.
    bare = native_catalog("example.bare")
    with pytest.raises(AssetError, match="unregistered_asset"):
        bare.asset_for("example.bare")


def test_example_manifest_references_shared_definitions_once():
    manifest = json.loads(
        (Path(__file__).parent.parent / "examples/native-assets.json").read_text(
            encoding="utf-8"
        )
    )
    records = native_records()
    entries = {item["asset_id"]: item for item in manifest["definitions"]}
    # osv-scanner plus the three new tools reference the shared document and
    # keep no release declarations of their own; hyperfine stays the #8
    # example's own definition.
    for asset_id in VERIFIED:
        assert entries[asset_id]["shared_document"] == "native.json"
        assert "releases" not in entries[asset_id]
        assert asset_id in records
    assert "releases" in entries["hyperfine"]
