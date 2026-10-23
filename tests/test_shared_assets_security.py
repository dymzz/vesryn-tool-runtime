"""Security scanner shared assets: the verified trivy declaration and deferral."""

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
POLICY = AssetPolicy("security-shared-1")

# Publisher GitHub Release asset digest for trivy 0.76.1 Linux-64bit, read on
# 2026-10-24 and cross-checked against the publisher's checksums.txt.
VERIFIED = {
    "version": "0.76.1",
    "source": (
        "https://github.com/aquasecurity/trivy/releases/download/"
        "v0.76.1/trivy_0.76.1_Linux-64bit.tar.gz"
    ),
    "sha256": "c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0",
    "entrypoint": "trivy",
    "abi": None,
    "tools": ("example.trivy",),
    "revision": "official-2026-10-24",
}


class RecordingAdapter:
    """A consumer-supplied adapter; shared definitions never reach it here."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def security_records():
    assert "security.json" in shared_definition_documents()
    return {
        record.definition.asset_id: record
        for record in load_shared_definitions("security.json")
    }


def test_security_document_declares_only_the_verified_trivy_asset():
    records = security_records()
    # Gitleaks is deferred (no Profile selected the Git-history check), so it
    # must not appear as a delivered definition anywhere in this group's data.
    assert set(records) == {"trivy"}
    record = records["trivy"]
    assert isinstance(record, SharedAssetDefinition)
    assert record.tools == VERIFIED["tools"]
    assert record.definition.catalog_revision == VERIFIED["revision"]
    (release,) = record.definition.releases
    assert release.version == VERIFIED["version"]
    assert release.source == VERIFIED["source"]
    assert release.sha256 == VERIFIED["sha256"]
    assert release.entrypoint == VERIFIED["entrypoint"]
    assert (release.os, release.arch, release.abi) == (
        "linux",
        "x86_64",
        VERIFIED["abi"],
    )
    assert release.distribution == "native" and release.backend == "aria2"
    for name in shared_definition_documents():
        assert all(
            "gitleaks" not in item.definition.asset_id
            for item in load_shared_definitions(name)
        )


def test_trivy_stays_an_unassembled_example_capability():
    record = security_records()["trivy"]
    # No formal ECI capability contract exists yet (ECI #59 owns the scan/SBOM
    # check entries); the example association cannot masquerade as one.
    assert record.tools == ("example.trivy",)
    tools = Catalog()
    tools.provider_name = "security-shared"
    with pytest.raises(AssetError, match="unregistered_tool"):
        register_shared_definitions(tools, record)
    tools.register(
        ToolSpec("example.trivy", {}, {}, effect="check"), RecordingAdapter()
    )
    register_shared_definitions(tools, record)
    selection = tools.select_asset("example.trivy", target=LINUX, policy=POLICY)
    assert selection.asset_id == "trivy" and selection.release.version == "0.76.1"
    assert selection.tool_contract_sha256 == tools.resolve("example.trivy")[0].sha256
    # Only the declared Linux x86_64 target is supported; the static Go build
    # carries no ABI constraint.
    with pytest.raises(AssetError, match="unsupported_target"):
        tools.select_asset(
            "example.trivy",
            target=AssetTarget("windows", "x86_64", abi="msvc"),
            policy=POLICY,
        )


def test_trivy_selection_is_offline_and_stable():
    tools = Catalog()
    tools.provider_name = "security-shared"
    tools.register(
        ToolSpec("example.trivy", {}, {}, effect="check"), RecordingAdapter()
    )
    register_shared_definitions(tools, security_records().values())
    first = tools.select_asset("example.trivy", target=LINUX, policy=POLICY)
    second = tools.select_asset(
        "example.trivy", target=LINUX, policy=AssetPolicy("later-revision")
    )
    # Same artifact content across policy revisions; no install or network fact
    # is implied by selecting.
    assert first.artifact_id == second.artifact_id
    assert first.selection_id != second.selection_id
    assert first.release.sha256 == VERIFIED["sha256"]
