"""Progressive group discovery: bounded summaries, Scope filtering and matching."""

import gzip
import json
import subprocess
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    AccessEntrySummary,
    Catalog,
    DiscoveryContractError,
    DiscoveryScope,
    ToolGroup,
    ToolResult,
    ToolSpec,
    discover_group_members,
    discover_groups,
    group_summary,
    load_shared_definitions,
    resolve_tool_access,
)
from vesryn_tool_runtime.dagger_discovery import discover, load_exposures

FIXTURES = Path(__file__).parent / "fixtures" / "dagger"
with gzip.open(FIXTURES / "engineering-ci-9949e22.schema.json.gz", "rb") as _stream:
    SCHEMA = json.load(_stream)
(SPEC,) = discover(
    SCHEMA, load_exposures(FIXTURES / "engineering-ci-9949e22.exposures.toml")
)
SCOPE = DiscoveryScope(environment="container", permissions=frozenset({"check"}))
GROUPS = (
    ToolGroup(
        "ci.security",
        ("trivy",),
        description="Vulnerability scanning and security review for a repository.",
        aliases=("ci-security", "security", "vulnerability"),
    ),
    ToolGroup(
        "ci.release",
        ("trivy", "pytest.artifacts"),
        description="Release evidence: SBOM and test artifacts.",
        aliases=("ci-release", "sbom", "evidence"),
    ),
    ToolGroup(
        "ci.quality",
        ("pytest.artifacts",),
        description="Test and quality evidence for repository changes.",
        aliases=("ci-quality", "tests", "evidence"),
    ),
)


class RecordingAdapter:
    """Adapter scaffold only: discovery never invokes it."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def entry():
    return AccessEntrySummary(
        tool_id=SPEC.tool_id,
        catalog_ref="ci",
        entry_key="default",
        provider="engineering-ci",
        environment="container",
        purpose="Collect a repository's pytest artifacts.",
        contract_version=SPEC.contract_version,
        contract_sha256=SPEC.sha256,
        discovery_scope="matched",
        assembly="assembled",
        binding="not_provided",
        execution_admission="not_evaluated",
        availability="unknown",
    )


def catalog(groups=GROUPS, spec=SPEC):
    tools = Catalog()
    tools.provider_name = "engineering-ci"
    tools.register(spec, RecordingAdapter())
    (trivy,) = (
        record
        for record in load_shared_definitions("security.json")
        if record.definition.asset_id == "trivy"
    )
    tools.register_asset(trivy.definition, tools=("trivy",))
    tools.register_access(entry())
    for group in groups:
        tools.register_group(group)
    return tools


def test_real_groups_preserve_records_and_share_one_tool_asset():
    tools = catalog()
    page = discover_groups(tools, catalog_ref="ci", scope=SCOPE)
    assert page.item_kind == "group-summary"
    assert page.total == 3
    assert [item.group_id for item in page.items] == [
        "ci.quality",
        "ci.release",
        "ci.security",
    ]
    release = page.items[1]
    assert release.aliases == ("ci-release", "sbom", "evidence")
    assert release.description.startswith("Release evidence")
    assert release.member_count == 2
    assert [member.tool_id for member in release.members] == [
        "trivy",
        "pytest.artifacts",
    ]
    assert page.items[2].members[0].tool_id == "trivy"
    assert tools.asset_for("trivy").asset_id == "trivy"
    document = json.dumps(page.document())
    assert "input_schema" not in document
    assert "output_schema" not in document


@pytest.mark.parametrize(
    "query,expected",
    [
        ("sbom", ["ci.release"]),
        ("ci-security", ["ci.security"]),
        ("evidence", ["ci.quality", "ci.release"]),
    ],
)
def test_purpose_and_alias_queries_select_matching_groups(query, expected):
    page = discover_groups(catalog(), catalog_ref="ci", scope=SCOPE, query=query)
    assert [item.group_id for item in page.items] == expected


def test_unrelated_query_returns_nothing_without_global_claims():
    page = discover_groups(
        catalog(), catalog_ref="ci", scope=SCOPE, query="nonexistent-topic"
    )
    assert page.total == 0
    assert page.items == ()
    assert page.diagnostics == ()
    assert "unregistered" not in json.dumps(page.document())


def test_scope_filters_members_before_order_and_page():
    only_artifacts = DiscoveryScope(available=frozenset({"pytest.artifacts"}))
    page = discover_groups(catalog(), catalog_ref="ci", scope=only_artifacts)
    assert [item.group_id for item in page.items] == ["ci.quality", "ci.release"]
    release = page.items[1]
    assert release.member_count == 1
    assert [member.tool_id for member in release.members] == ["pytest.artifacts"]
    assert "trivy" not in json.dumps(release.document())

    # A host/effect mismatch for the contract-backed member leaves the
    # asset-only reference visible and hides the group that lost every member.
    host = DiscoveryScope(environment="host")
    page = discover_groups(catalog(), catalog_ref="ci", scope=host)
    assert [item.group_id for item in page.items] == ["ci.release", "ci.security"]


def test_bounded_member_lists_state_the_boundary():
    page = discover_groups(catalog(), catalog_ref="ci", scope=SCOPE, members_limit=1)
    release = {item.group_id: item for item in page.items}["ci.release"]
    assert release.member_count == 1
    assert len(release.members) == 1
    (diagnostic,) = page.diagnostics
    assert diagnostic.code == "undisclosed"
    assert diagnostic.ref == "ci.release"


def test_group_member_matching_uses_group_purpose_and_alias():
    tools = catalog()
    release = discover_group_members(tools, "ci.release", catalog_ref="ci", scope=SCOPE)
    assert release.total == 1
    assert [item.tool_id for item in release.items] == ["pytest.artifacts"]
    assert release.items[0].group_id == "ci.release"

    quality = discover_group_members(tools, "ci.quality", catalog_ref="ci", scope=SCOPE)
    assert quality.items[0].tool_id == "pytest.artifacts"
    assert quality.items[0].group_id == "ci.quality"

    via_alias = discover_group_members(
        tools, "ci.release", catalog_ref="ci", scope=SCOPE, query="sbom"
    )
    assert via_alias.items[0].matched_alias == "sbom"

    none = discover_group_members(
        tools, "ci.release", catalog_ref="ci", scope=SCOPE, query="nothing-relevant"
    )
    assert none.total == 0
    assert none.items == ()


def test_member_pages_are_bounded_and_continue_stably():
    tools = Catalog()
    tools.provider_name = "demo"
    for tool_id in ("python.alpha", "python.beta", "python.gamma"):
        tools.register(
            ToolSpec(
                tool_id,
                {"type": "object"},
                {"type": "object"},
                effect="check",
                domain="python",
                description=f"{tool_id} fixture",
            ),
            RecordingAdapter(),
        )
    tools.register_group(
        ToolGroup(
            "ci.large",
            ("python.alpha", "python.beta", "python.gamma"),
            description="Large fixture group.",
        )
    )
    first = discover_group_members(
        tools, "ci.large", catalog_ref="ci", scope=None, limit=2
    )
    assert first.total == 3
    assert [item.tool_id for item in first.items] == ["python.alpha", "python.beta"]
    assert first.next_offset == 2
    second = discover_group_members(
        tools, "ci.large", catalog_ref="ci", scope=None, offset=2, limit=2
    )
    assert [item.tool_id for item in second.items] == ["python.gamma"]
    assert second.next_offset is None


def test_members_without_a_contract_are_reported_not_invented():
    tools = catalog()
    page = discover_group_members(tools, "ci.security", catalog_ref="ci", scope=SCOPE)
    assert page.total == 0
    assert page.items == ()
    (diagnostic,) = page.diagnostics
    assert diagnostic.code == "unregistered"
    assert "trivy" not in json.dumps(page.document())
    summary = group_summary(tools, "ci.security", catalog_ref="ci", scope=SCOPE)
    assert [member.tool_id for member in summary.members] == ["trivy"]


def test_unknown_group_and_bad_bounds_are_explicit():
    tools = catalog()
    with pytest.raises(DiscoveryContractError, match="unknown_reference"):
        discover_group_members(tools, "nope.group", catalog_ref="ci", scope=SCOPE)
    with pytest.raises(DiscoveryContractError, match="unknown_reference"):
        group_summary(tools, "nope.group", catalog_ref="ci", scope=SCOPE)
    with pytest.raises(DiscoveryContractError, match="invalid_query"):
        discover_groups(tools, catalog_ref="ci", scope=SCOPE, limit=0)
    with pytest.raises(DiscoveryContractError, match="invalid_query"):
        discover_groups(tools, catalog_ref="ci", scope=SCOPE, members_limit=0)


def test_discovery_never_runs_a_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("group discovery must not execute or probe anything")

    monkeypatch.setattr(subprocess, "run", forbidden)
    tools = catalog()
    assert discover_groups(tools, catalog_ref="ci", scope=SCOPE).total == 3
    assert (
        discover_group_members(tools, "ci.release", catalog_ref="ci", scope=SCOPE).total
        == 1
    )


def test_a_selected_member_resolves_its_contract_without_another_lookup():
    tools = catalog()
    member = discover_group_members(
        tools, "ci.release", catalog_ref="ci", scope=SCOPE
    ).items[0]
    resolution = resolve_tool_access(tools, member.tool_id, scope=SCOPE)
    assert len(resolution.entries) == 1
    assert len(resolution.contracts) == 1
    assert resolution.contracts[0].contract["contract_sha256"] == (
        member.contract_sha256
    )
    assert member.contract_sha256 == SPEC.sha256
