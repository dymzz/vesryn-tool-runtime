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
    "tools": ("trivy",),
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


def test_trivy_registers_directly_and_stays_without_a_fake_entry():
    record = security_records()["trivy"]
    # The bare program primary key registers directly with no ToolSpec or
    # placeholder (#32); until ECI #59 delivers a real scan/SBOM contract,
    # acquisition refuses explicitly and no callable entry is invented.
    assert record.tools == ("trivy",)
    tools = Catalog()
    tools.provider_name = "security-shared"
    register_shared_definitions(tools, record)
    assert tools.asset_for("trivy") is record.definition
    with pytest.raises(AssetError, match="unregistered_tool"):
        tools.select_asset("trivy", target=LINUX, policy=POLICY)
    linux = tools.asset_view("trivy", target=LINUX, policy=POLICY)
    assert len(linux["available"]) == 1
    assert linux["selection_status"] == "unregistered_tool"
    # Only the declared Linux x86_64 target is supported; the static Go build
    # carries no ABI constraint.
    windows = tools.asset_view(
        "trivy", target=AssetTarget("windows", "x86_64", abi="msvc"), policy=POLICY
    )
    assert windows["available"] == []


def test_trivy_selection_is_offline_and_stable():
    tools = Catalog()
    tools.provider_name = "security-shared"
    # Frozen selections need a real contract; a test capability id (not the
    # bare tool key) carries one, associated with the same definition.
    tools.register(
        ToolSpec("security.image-scan", {}, {}, effect="check"), RecordingAdapter()
    )
    register_shared_definitions(tools, security_records().values())
    tools.register_asset(
        security_records()["trivy"].definition, tools=("security.image-scan",)
    )
    first = tools.select_asset("security.image-scan", target=LINUX, policy=POLICY)
    second = tools.select_asset(
        "security.image-scan", target=LINUX, policy=AssetPolicy("later-revision")
    )
    # Same artifact content across policy revisions; no install or network fact
    # is implied by selecting.
    assert first.artifact_id == second.artifact_id
    assert first.selection_id != second.selection_id
    assert first.release.sha256 == VERIFIED["sha256"]
