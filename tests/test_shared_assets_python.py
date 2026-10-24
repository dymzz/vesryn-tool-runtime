"""Python CLI shared definitions: ECI identities, the deptry platform fix and old records."""

import copy

import pytest

from vesryn_tool_runtime import (
    AssetError,
    AssetPolicy,
    AssetSelection,
    AssetTarget,
    Catalog,
    ToolResult,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)

LINUX = AssetTarget("linux", "x86_64", abi="gnu", python="3.14")
WINDOWS = AssetTarget("windows", "x86_64", python="3.14")
POLICY = AssetPolicy("eci-tools-2026-10-23")
FILES = "https://files.pythonhosted.org/packages/"

# Definition digests recorded by engineering-ci #51's frozen asset_documents.
# pyright and pylint reproduce that record byte-for-byte; deptry's two
# platform corrections (os/arch in #17, glibc abi in #29) and vulture's
# migration of the still-used 2.14 release (#32) necessarily publish
# different digests.
DEFINITION_SHA256 = {
    "vulture": "6dbabb57bf200df6885d7a11780ccef1ba6d236467e95dceab865ebf69c97eac",
    "pyright": "4436d29deb3fa56c78e4ede01c48039ca4012a51f489e8d0bc8b5dc9b1f262c1",
    "deptry": "7cf1b54637d47b66d029d018d808843e6ea97af94a2864bea54e81ae6c1db5d6",
    "pylint": "b30fda820a20574e2db44e0c126b2782c4a9b22ed296ed3c80b2eb2c5802724b",
}
# The wheel each release actually points at: only deptry's is platform-built.
EXPECTED_ABI = {"vulture": None, "pyright": None, "deptry": "gnu", "pylint": None}
OLD_DEPTRY_DEFINITION_SHA256 = (
    "6ee56d9c4e3cfcc822564071d959a61b96972874c38b901e68a93305c7a66320"
)
DECLARATIONS = {
    "vulture": (
        "python.dead-code",
        "2.16",
        "vulture",
        ">=3.9",
        "any",
        "any",
        "6e0f1c312cef1c87856957e5c2ca9608834a7c794c2180477f30bf0e4cc58eee",
        FILES + "f5/be/f935130312330614811dae2ea9df3f395f6d63889eb6c2e68c14507152ee/"
        "vulture-2.16-py3-none-any.whl",
    ),
    "pyright": (
        "python.typecheck",
        "1.1.414",
        "pyright",
        ">=3.7",
        "any",
        "any",
        "2a6b4b3298c9eec174c5ed83bd338de6eee82df2992f3e1930e6199d381be36f",
        FILES + "d7/ba/18b6e682ead424ad24bcc134339ae5d1b931cd9ae260540592a058a91279/"
        "pyright-1.1.414-py3-none-any.whl",
    ),
    "deptry": (
        "python.dependency-hygiene",
        "0.25.1",
        "deptry",
        ">=3.10",
        "linux",
        "x86_64",
        "14bfcc28b4326ed8c6abb30691b19077d4ef8613cfba6c37ef5b1f471775bf6f",
        FILES + "72/9c/6f6f9125bac74b5d5d2af89536cbdb3fa159b6466aa097b74e7e85e8e030/"
        "deptry-0.25.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
    ),
    "pylint": (
        "python.duplicate-code",
        "4.1.3",
        "pylint",
        ">=3.10.0",
        "any",
        "any",
        "a85357cae24f33ad8d86c8f3daaa92c600ae4012b54a57299cee76000e9364cf",
        FILES + "3f/ba/62b18e2e157d05f976bd490b349b55d8850c2a454a5c313c91af9d2e0baf/"
        "pylint-4.1.3-py3-none-any.whl",
    ),
}

# engineering-ci #51's frozen deptry selection (asset_documents/deptry.selection.json,
# commit 22774da). It recorded the manylinux x86_64 wheel as os/arch "any".
OLD_DEPTRY_SELECTION = {
    "asset_id": "deptry",
    "catalog_revision": "eci-tools-2026-10-23",
    "definition_sha256": OLD_DEPTRY_DEFINITION_SHA256,
    "kind": "tool-asset-selection",
    "policy": {"enabled": True, "revision": "eci-tools-2026-10-23", "specifier": ""},
    "provider": None,
    "release": {
        "abi": None,
        "arch": "any",
        "backend": "uv",
        "distribution": "python",
        "entrypoint": "deptry",
        "lock_ref": None,
        "os": "any",
        "package": "deptry",
        "requires_python": ">=3.10",
        "sha256": "14bfcc28b4326ed8c6abb30691b19077d4ef8613cfba6c37ef5b1f471775bf6f",
        "source": FILES
        + "72/9c/6f6f9125bac74b5d5d2af89536cbdb3fa159b6466aa097b74e7e85e8e030/"
        "deptry-0.25.1-cp310-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
        "version": "0.25.1",
    },
    "schema_version": 1,
    "selection_id": "5e8f46e6487ea1836c09ccd471a7c144bfed44361588f47eedf35ca3b5b0d3fa",
    "specifier": "",
    "target": {"abi": None, "arch": "x86_64", "os": "linux", "python": "3.14"},
    "tool_contract_sha256": (
        "52cee0e95594a64043b0a655d4b5175a1a39a6bf23161e9b5db09813fb60663a"
    ),
    "tool_id": "python.dependency-hygiene",
    "version": "0.25.1",
}


class RecordingAdapter:
    """Association-only scaffold: this repository ships no ECI check adapter.

    The definition teaches the Catalog which existing capability the program
    serves. It neither implements nor proves callable check capabilities.
    """

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def catalog(*tool_ids):
    tools = Catalog()
    for tool_id in tool_ids:
        tools.register(ToolSpec(tool_id, {}, {}, effect="check"), RecordingAdapter())
    return tools


def records():
    return load_shared_definitions("python.json")


def assembled():
    tools = catalog(*(tool_id for tool_id, *_ in DECLARATIONS.values()))
    register_shared_definitions(tools, records())
    return tools


def test_bundled_python_document_matches_the_eci_identities():
    assert "python.json" in shared_definition_documents()
    loaded = records()
    assert tuple(item.definition.asset_id for item in loaded) == tuple(DECLARATIONS)
    for item in loaded:
        asset_id = item.definition.asset_id
        tool_id, version, package, requires_python, os_name, arch, sha, source = (
            DECLARATIONS[asset_id]
        )
        assert item.tools == (tool_id,)
        assert item.definition.catalog_revision == "eci-tools-2026-10-23"
        assert item.definition.sha256 == DEFINITION_SHA256[asset_id]
        if len(item.definition.releases) == 1:
            (release,) = item.definition.releases
        else:
            release = item.definition.releases[0]
        assert (
            release.version,
            release.distribution,
            release.backend,
            release.source,
            release.sha256,
            release.entrypoint,
            release.os,
            release.arch,
            release.abi,
            release.package,
            release.requires_python,
        ) == (
            version,
            "python",
            "uv",
            source,
            sha,
            package,
            os_name,
            arch,
            EXPECTED_ABI[asset_id],
            package,
            requires_python,
        )


def test_assembly_reuses_registered_capabilities_for_linux_selections():
    tools = assembled()
    for asset_id, (tool_id, version, *_rest) in DECLARATIONS.items():
        assert tools.asset_for(tool_id) is not None
        assert tools.asset_for(tool_id).asset_id == asset_id
        selection = tools.select_asset(tool_id, target=LINUX, policy=POLICY)
        assert selection.asset_id == asset_id
        assert selection.release.version == version
        assert selection.definition_sha256 == DEFINITION_SHA256[asset_id]
        assert selection.tool_contract_sha256 == tools.resolve(tool_id)[0].sha256


def test_deptry_platform_correction_blocks_incompatible_targets():
    tools = assembled()
    # The manylinux (glibc) wheel serves neither Windows, nor an explicit musl
    # target, nor a target whose C library is unknown (#29).
    for target in (
        WINDOWS,
        AssetTarget("linux", "x86_64", abi="musl", python="3.14"),
        AssetTarget("linux", "x86_64", python="3.14"),
    ):
        with pytest.raises(AssetError, match="unsupported_target"):
            tools.select_asset(
                "python.dependency-hygiene", target=target, policy=POLICY
            )
    # The three universal wheels are genuinely platform-independent and keep
    # serving either host and either C library.
    for tool_id in ("python.dead-code", "python.typecheck", "python.duplicate-code"):
        for target in (
            WINDOWS,
            AssetTarget("linux", "x86_64", abi="musl", python="3.14"),
        ):
            assert (
                tools.select_asset(tool_id, target=target, policy=POLICY).release.os
                == "any"
            )


def test_old_deptry_selection_stays_readable_and_unchanged():
    old = AssetSelection.from_document(copy.deepcopy(OLD_DEPTRY_SELECTION))
    assert old.document() == OLD_DEPTRY_SELECTION
    assert old.definition_sha256 == OLD_DEPTRY_DEFINITION_SHA256
    assert (old.release.os, old.release.arch) == ("any", "any")
    assert old.artifact_id == (
        "3886c0ddbc7636d89f0a4a251e19ffb255ef3c4317379c563d3069eec9737434"
    )

    current = assembled().select_asset(
        "python.dependency-hygiene", target=LINUX, policy=POLICY
    )
    # The correction changes declaration identity only; it re-points the same
    # publisher artifact, so a regenerated lock keeps the same requirement set.
    assert current.release.version == old.release.version
    assert current.release.source == old.release.source
    assert current.release.sha256 == old.release.sha256
    assert (current.release.os, current.release.arch) == ("linux", "x86_64")
    assert current.definition_sha256 == DEFINITION_SHA256["deptry"]
    assert current.definition_sha256 != old.definition_sha256
    assert current.artifact_id != old.artifact_id
    assert current.selection_id != old.selection_id


def test_vulture_migrates_the_still_used_214_release_with_real_metadata():
    record = next(item for item in records() if item.definition.asset_id == "vulture")
    # #32 migrates the release the old uv_tool_prepare path still uses into
    # the single active source, with PyPI-verified per-release Requires-Python
    # (the old path flattened both versions to ">=3.8").
    assert [item.version for item in record.definition.releases] == ["2.16", "2.14"]
    by_version = {item.version: item for item in record.definition.releases}
    assert by_version["2.16"].requires_python == ">=3.9"
    assert by_version["2.14"].requires_python == ">=3.8"
    assert by_version["2.14"].source.endswith("vulture-2.14-py2.py3-none-any.whl")
    assert by_version["2.14"].sha256 == (
        "d9a90dba89607489548a49d557f8bac8112bd25d3cbc8aeef23e860811bd9ed9"
    )
    # Publisher order keeps 2.16 as the unresolved default.
    selection = assembled().select_asset(
        "python.dead-code", target=LINUX, policy=POLICY
    )
    assert selection.release.version == "2.16"
