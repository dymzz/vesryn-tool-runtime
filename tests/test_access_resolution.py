"""Access resolution: a real ECI contract, one Scope authority, bounded diagnostics."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    AccessEntrySummary,
    AssetDefinition,
    AssetRelease,
    Catalog,
    DiscoveryContractError,
    DiscoveryScope,
    ScopeDecision,
    ToolResult,
    ToolRuntimeError,
    resolve_access,
    resolve_tool_access,
)
from vesryn_tool_runtime.dagger_discovery import discover, load_exposures

FIXTURES = Path(__file__).parent / "fixtures" / "dagger"
with gzip.open(FIXTURES / "engineering-ci-9949e22.schema.json.gz", "rb") as _stream:
    SCHEMA = json.load(_stream)
EXPOSURES = load_exposures(FIXTURES / "engineering-ci-9949e22.exposures.toml")
(SPEC,) = discover(SCHEMA, EXPOSURES)
TOOL = SPEC.tool_id
SCOPE = DiscoveryScope(environment="container", permissions=frozenset({"check"}))


class RecordingAdapter:
    """Adapter scaffold only: resolution never invokes it."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("passed", 0) for call in calls}


def entry(access_id=None, entry_key="default", **changes):
    value = {
        "tool_id": TOOL,
        "catalog_ref": "ci",
        "entry_key": entry_key,
        "provider": "engineering-ci",
        "environment": "container",
        "purpose": "Collect a repository's pytest artifacts.",
        "contract_version": SPEC.contract_version,
        "contract_sha256": SPEC.sha256,
        "discovery_scope": "matched",
        "assembly": "assembled",
        "binding": "not_provided",
        "execution_admission": "not_evaluated",
        "availability": "unknown",
    }
    if access_id is not None:
        value["access_id"] = access_id
    value.update(changes)
    return AccessEntrySummary(**value)


def catalog_with(*entries):
    tools = Catalog()
    tools.register(SPEC, RecordingAdapter())
    for item in entries:
        tools.register_access(item)
    return tools


def test_two_registered_entries_resolve_with_the_real_eci_contract():
    first = entry(access_id="pytest.artifacts.default")
    second = entry(access_id="ci:pytest.artifacts@native", entry_key="native")
    result = resolve_tool_access(catalog_with(first, second), TOOL, scope=SCOPE)

    assert result.total == 2
    assert result.incomplete is False
    assert [item.access_id for item in result.entries] == [
        "ci:pytest.artifacts@native",
        "pytest.artifacts.default",
    ]
    assert len(result.contracts) == 2
    assert {item.tool_id for item in result.contracts} == {TOOL}
    assert {item.contract["contract_sha256"] for item in result.contracts} == {
        SPEC.sha256
    }
    # The contract is the mapped original: same module revision and function,
    # not a restated Schema or a renamed tool.
    assert SPEC.source["identity"].startswith(
        "github.com/dymzz/engineering-ci@9949e22dc03e4361bb46540ca5a4d51c1cefd3ae"
    )
    assert SPEC.source["identity"].endswith("#EngineeringCi.repositoryTestArtifacts")
    assert SPEC.environments == ("container",)


def test_each_entry_resolves_directly_by_access_id():
    tools = catalog_with(
        entry(access_id="pytest.artifacts.default"),
        entry(access_id="ci:pytest.artifacts@native", entry_key="native"),
    )
    for access_id in ("pytest.artifacts.default", "ci:pytest.artifacts@native"):
        result = resolve_access(tools, access_id, scope=SCOPE)
        assert result.access_id == access_id
        assert len(result.entries) == 1
        assert len(result.contracts) == 1
        assert result.contracts[0].contract["contract_sha256"] == SPEC.sha256
        assert result.entries[0].provider == "engineering-ci"
        assert result.entries[0].environment == "container"


def test_undisclosed_entries_are_not_named_or_counted():
    hidden = entry(
        access_id="pytest.artifacts.hidden",
        discovery_scope="excluded",
        reason_code="undisclosed",
    )
    tools = catalog_with(entry(access_id="pytest.artifacts.default"), hidden)
    result = resolve_tool_access(tools, TOOL, scope=SCOPE)
    assert result.total == 1
    assert [item.access_id for item in result.entries] == ["pytest.artifacts.default"]
    assert [item.code for item in result.diagnostics] == ["undisclosed"]
    assert "pytest.artifacts.hidden" not in json.dumps(result.document())

    direct = resolve_access(tools, "pytest.artifacts.hidden", scope=SCOPE)
    assert direct.entries == ()
    assert [item.code for item in direct.diagnostics] == ["undisclosed"]


@pytest.mark.parametrize(
    "scope,reason",
    [
        (DiscoveryScope(environment="host"), "environment"),
        (DiscoveryScope(permissions=frozenset({"read"})), "effect"),
        (DiscoveryScope(available=frozenset({"other.tool"})), "availability"),
        (DiscoveryScope(constraint=lambda spec, current: False), "constraint"),
    ],
)
def test_caller_scope_excludes_before_paging(scope, reason):
    result = resolve_tool_access(catalog_with(entry()), TOOL, scope=scope)
    assert result.total == 0
    assert result.entries == ()
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "scope_excluded"
    assert f"({reason})" in diagnostic.detail


def test_paging_states_limits_and_continuation():
    tools = catalog_with(
        entry(access_id="a.b"), entry(access_id="c.d"), entry(access_id="e.f")
    )
    first = resolve_tool_access(tools, TOOL, scope=SCOPE, limit=2)
    assert first.total == 3
    assert [item.access_id for item in first.entries] == ["a.b", "c.d"]
    assert first.next_offset == 2
    second = resolve_tool_access(tools, TOOL, scope=SCOPE, offset=2, limit=2)
    assert [item.access_id for item in second.entries] == ["e.f"]
    assert second.next_offset is None
    with pytest.raises(DiscoveryContractError, match="invalid_query"):
        resolve_tool_access(tools, TOOL, scope=SCOPE, limit=0)
    with pytest.raises(DiscoveryContractError, match="invalid_query"):
        resolve_tool_access(tools, TOOL, scope=SCOPE, offset=-1)


def test_resolution_never_runs_a_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("resolution must not execute or probe anything")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert resolve_tool_access(catalog_with(entry()), TOOL, scope=SCOPE).total == 1


def test_asset_only_tool_reports_no_entry_without_inventing_a_contract():
    tools = Catalog()
    release = AssetRelease(
        "0.60.0",
        "native",
        "aria2",
        "https://example.invalid/trivy.zip",
        hashlib.sha256(b"trivy").hexdigest(),
        "trivy.exe",
        os="windows",
        arch="x86_64",
        abi="msvc",
    )
    tools.register_asset(
        AssetDefinition("trivy", "fixture-1", (release,)), tools=("trivy",)
    )
    result = resolve_tool_access(tools, "trivy", scope=None)
    assert result.entries == ()
    assert result.contracts == ()
    assert [item.code for item in result.diagnostics] == ["unregistered"]


def test_stale_entry_contract_stays_unknown_and_never_becomes_a_contract():
    stale = entry(access_id="pytest.artifacts.stale", contract_sha256="a" * 64)
    result = resolve_tool_access(catalog_with(stale), TOOL, scope=SCOPE)
    assert len(result.entries) == 1
    assert result.contracts == ()
    assert result.incomplete is True
    (diagnostic,) = result.diagnostics
    assert diagnostic.code == "unknown"
    assert diagnostic.ref == "pytest.artifacts.stale"


def test_recorded_entry_facts_surface_as_structured_diagnostics():
    tools = catalog_with(entry(assembly="missing"))
    (diagnostic,) = resolve_tool_access(tools, TOOL, scope=SCOPE).diagnostics
    assert diagnostic.code == "unassembled"
    assert diagnostic.ref == "ci:pytest.artifacts@default"


def test_unknown_references_keep_explicit_errors():
    tools = catalog_with(entry())
    with pytest.raises(DiscoveryContractError, match="unknown_reference"):
        resolve_tool_access(tools, "nope.tool", scope=SCOPE)
    with pytest.raises(DiscoveryContractError, match="unknown_reference"):
        resolve_access(tools, "nope.entry", scope=SCOPE)


def test_scope_decision_is_the_single_authority():
    assert SCOPE.decision(SPEC).matched is True
    excluded = DiscoveryScope(permissions=frozenset({"read"}))
    decision = excluded.decision(SPEC)
    assert (decision.state, decision.reason) == ("excluded", "effect")
    assert excluded.matches(SPEC) is False
    with pytest.raises(ToolRuntimeError):
        ScopeDecision(True, "effect")
    with pytest.raises(ToolRuntimeError):
        ScopeDecision(False)
