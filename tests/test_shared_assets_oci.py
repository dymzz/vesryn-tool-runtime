"""Offline OCI declaration and selection tests; these do not execute Dagger."""

import pytest

from vesryn_tool_runtime import (
    AssetError,
    AssetIndex,
    AssetPolicy,
    AssetReceipt,
    AssetTarget,
    Catalog,
    ToolResult,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)

LINUX_AMD64 = AssetTarget("linux", "x86_64")
LINUX_ARM64 = AssetTarget("linux", "aarch64")
WINDOWS_X86 = AssetTarget("windows", "x86_64")
POLICY = AssetPolicy("oci-shared-1")

VERIFIED = {
    "semgrep": {
        "version": "1.99.0",
        "index_digest": "ae27024c16f7848cdbfd49c24ed0b78b13f13b85fcd7b87c679aaa8b0c0dce98",
        "entrypoint": "semgrep",
        "tools": ("code.pattern-scan",),
        "revision": "official-2026-10-24",
        "platforms": {
            ("linux", "x86_64"): {
                "digest": "374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d",
                "source": "docker.io/semgrep/semgrep@sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d",
            },
            ("linux", "aarch64"): {
                "digest": "08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc",
                "source": "docker.io/semgrep/semgrep@sha256:08f1c44024049d1a104f57203dab60b3579f17a12fe87bac7bb60130bbc46bfc",
            },
        },
    },
    "lychee": {
        "version": "0.18.0",
        "index_digest": "83d7644b4b633943c94baa15ddd274637b9ec49f746ab2ce1c77c33be1e680a5",
        "entrypoint": "lychee",
        "tools": ("docs.link-check",),
        "revision": "official-2026-10-24",
        "platforms": {
            ("linux", "x86_64"): {
                "digest": "606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8",
                "source": "docker.io/lycheeverse/lychee@sha256:606c60a7f61ab802297973d1bd9a429c88c4b99596a23bfe34e63a46b6d40fc8",
            },
            ("linux", "aarch64"): {
                "digest": "b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c",
                "source": "docker.io/lycheeverse/lychee@sha256:b1be296f112676caac52748c7f692eacde9a26fa23f8715b5662af9ad7dd451c",
            },
        },
    },
}


def test_oci_document_is_bundled_and_enumerated():
    assert "oci.json" in shared_definition_documents()


def test_definitions_carry_verified_publisher_digests_and_oci_contracts():
    records = {r.definition.asset_id: r for r in load_shared_definitions("oci.json")}
    assert set(records) == {"semgrep", "lychee"}

    for asset_id, expected in VERIFIED.items():
        record = records[asset_id]
        definition = record.definition
        assert definition.catalog_revision == expected["revision"]
        assert record.tools == expected["tools"]
        assert len(definition.releases) == len(expected["platforms"])

        for release in definition.releases:
            assert release.version == expected["version"]
            assert release.distribution == "oci"
            assert release.backend == "oci"
            assert release.entrypoint == expected["entrypoint"]
            assert (release.os, release.arch) in expected["platforms"]
            plat = expected["platforms"][(release.os, release.arch)]
            assert release.sha256 == plat["digest"]
            assert release.source == plat["source"]
            assert release.source.endswith("@sha256:" + release.sha256)


@pytest.mark.parametrize("asset_id", ["semgrep", "lychee"])
def test_oci_tools_target_linux_and_reject_windows(asset_id):
    records = {r.definition.asset_id: r for r in load_shared_definitions("oci.json")}
    definition = records[asset_id].definition
    tool_id = records[asset_id].tools[0]

    catalog = Catalog()
    catalog.register(ToolSpec(tool_id, {}, {}, effect="check"), None)
    catalog.register_asset(definition, tools=(tool_id,))

    # Linux x86_64 resolves to amd64 manifest
    sel_amd64 = catalog.select_asset(tool_id, target=LINUX_AMD64, policy=POLICY)
    assert sel_amd64.release.arch == "x86_64"
    assert (
        sel_amd64.release.sha256
        == VERIFIED[asset_id]["platforms"][("linux", "x86_64")]["digest"]
    )

    # Linux aarch64 resolves to arm64 manifest
    sel_arm64 = catalog.select_asset(tool_id, target=LINUX_ARM64, policy=POLICY)
    assert sel_arm64.release.arch == "aarch64"
    assert (
        sel_arm64.release.sha256
        == VERIFIED[asset_id]["platforms"][("linux", "aarch64")]["digest"]
    )

    # Windows target is rejected with unsupported_target
    with pytest.raises(AssetError) as exc_info:
        catalog.select_asset(tool_id, target=WINDOWS_X86, policy=POLICY)
    assert exc_info.value.code == "unsupported_target"


def test_assembly_and_views_through_public_catalog():
    records = load_shared_definitions("oci.json")
    catalog = Catalog()
    for record in records:
        for tool_id in record.tools:
            catalog.register(ToolSpec(tool_id, {}, {}, effect="check"), None)
    register_shared_definitions(catalog, records)

    view_semgrep = catalog.asset_view(
        "code.pattern-scan", target=LINUX_AMD64, policy=POLICY
    )
    assert view_semgrep["selection_status"] == "selectable"
    assert len(view_semgrep["available"]) == 1
    assert view_semgrep["available"][0]["entrypoint"] == "semgrep"
    assert view_semgrep["installed"]["status"] == "not_configured"

    view_lychee = catalog.asset_view(
        "docs.link-check", target=LINUX_AMD64, policy=POLICY
    )
    assert view_lychee["selection_status"] == "selectable"
    assert len(view_lychee["available"]) == 1
    assert view_lychee["available"][0]["entrypoint"] == "lychee"


def test_oci_releases_preserve_index_boundary_without_inventing_installation(tmp_path):
    records = {r.definition.asset_id: r for r in load_shared_definitions("oci.json")}
    definition = records["semgrep"].definition
    tool_id = records["semgrep"].tools[0]

    catalog = Catalog()
    catalog.register(ToolSpec(tool_id, {}, {}, effect="check"), None)
    catalog.register_asset(definition, tools=(tool_id,))
    selection = catalog.select_asset(tool_id, target=LINUX_AMD64, policy=POLICY)

    index = AssetIndex(tmp_path)
    # Unknown outcome records cleanly as unknown
    index.record(AssetReceipt(selection, ToolResult("unknown", None)))
    installed = index.installed(selection)
    assert installed["status"] == "unknown"
    assert installed["reason"] == "backend_unknown"

    # Index._verify rejects OCI backend for passed status because OCI is executed in Dagger,
    # not installed onto host filesystem
    with pytest.raises(AssetError) as exc_info:
        index.record(
            AssetReceipt(
                selection,
                ToolResult("passed", 0, executed=True, complete=True, current=True),
                locator=str(tmp_path),
                files=(),
                verified_source_sha256=selection.release.sha256,
            )
        )
    assert exc_info.value.code == "backend_unknown"


def test_semgrep_selection_retains_pinned_oci_source_and_entrypoint():
    """Check selected metadata only; live Dagger evidence is stored separately."""
    records = {r.definition.asset_id: r for r in load_shared_definitions("oci.json")}
    definition = records["semgrep"].definition
    catalog = Catalog()
    catalog.register(ToolSpec("code.pattern-scan", {}, {}, effect="check"), None)
    catalog.register_asset(definition, tools=("code.pattern-scan",))
    selection = catalog.select_asset(
        "code.pattern-scan", target=LINUX_AMD64, policy=POLICY
    )

    assert selection.release.source == (
        "docker.io/semgrep/semgrep@sha256:374d5a678b58e9ba3ef291ce37ffa836f69150a2360c78f02dca7a07bc42fb7d"
    )
    assert selection.release.entrypoint == "semgrep"
