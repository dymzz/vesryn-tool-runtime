"""Discovery field contracts: identities, fact states, disclosure and rounds."""

import pytest

from vesryn_tool_runtime import (
    AccessEntrySummary,
    CandidateSummary,
    ContractDetail,
    DiscoveryContractError,
    DiscoveryDiagnostic,
    DiscoveryErrorDocument,
    DiscoveryPage,
    DiscoveryQuery,
    GroupMember,
    GroupSummary,
    ToolSpec,
    compose_access_id,
)
from vesryn_tool_runtime.discovery_contracts import (
    ASSEMBLY_STATES,
    BINDING_STATES,
    DIAGNOSTIC_CODES,
    EFFECTS,
    ERROR_CODES,
    ITEM_KINDS,
)
from vesryn_tool_runtime.documents import canonical

SPEC = ToolSpec(
    "python.dead-code",
    {"type": "object"},
    {"type": "object"},
    effect="check",
    domain="python",
    description="Reports unused code.",
)
ZERO = "0" * 64


def contract_error(code):
    return pytest.raises(DiscoveryContractError, match=code)


def entry(**changes):
    value = {
        "tool_id": "python.dead-code",
        "catalog_ref": "ci",
        "entry_key": "default",
        "provider": "engineering-ci",
        "environment": "dagger",
        "purpose": "Reports unused code.",
        "contract_version": SPEC.contract_version,
        "contract_sha256": SPEC.sha256,
        "discovery_scope": "matched",
    }
    value.update(changes)
    return AccessEntrySummary(**value)


def test_query_paging_and_filter_rules_reuse_existing_bounds():
    default = DiscoveryQuery()
    assert (default.offset, default.limit) == (0, 10)
    assert list(default.document()) == [
        "schema_version",
        "kind",
        "offset",
        "limit",
    ]
    full = DiscoveryQuery(
        query="dead code",
        operation="lint",
        domain="python",
        environment="dagger",
        effect="check",
        group_id="python.quality",
        catalog_ref="ci",
        offset=30,
        limit=50,
        discovery_id="caller-run-17",
    )
    again = DiscoveryQuery.from_document(full.document())
    assert again == full and full.limit == 50
    with contract_error("invalid_query"):
        DiscoveryQuery(limit=0)
    with contract_error("invalid_query"):
        DiscoveryQuery(limit=51)
    with contract_error("invalid_query"):
        DiscoveryQuery(offset=-1)
    with contract_error("invalid_query"):
        DiscoveryQuery(effect="destroy")
    with contract_error("invalid_query"):
        DiscoveryQuery(environment="Dagger")
    with contract_error("invalid_query"):
        DiscoveryQuery(query="x" * 257)


@pytest.mark.parametrize(
    "document",
    [
        {"schema_version": 2, "kind": "discovery-query", "offset": 0, "limit": 10},
        {"schema_version": 1, "kind": "other", "offset": 0, "limit": 10},
        {
            "schema_version": 1,
            "kind": "discovery-query",
            "offset": 0,
            "limit": 10,
            "extra": 1,
        },
    ],
)
def test_documents_reject_wrong_envelopes_and_unknown_fields(document):
    with contract_error("invalid_document"):
        DiscoveryQuery.from_document(document)


def test_candidate_summary_derives_from_the_existing_toolspec_summary():
    candidate = CandidateSummary.from_spec(
        SPEC, provider="engineering-ci", catalog_ref="ci"
    )
    summary = SPEC.summary()
    for name in (
        "tool_id",
        "description",
        "domain",
        "effect",
        "contract_version",
        "contract_sha256",
    ):
        assert getattr(candidate, name) == summary[name]
    assert candidate.environments == SPEC.environments
    document = candidate.document()
    assert document["provider"] == "engineering-ci"
    assert document["catalog_ref"] == "ci"
    # Optional match facts appear only when actually hit; summaries never
    # carry parameter schemas.
    assert not {"group_id", "matched_alias", "asset_id"} & document.keys()
    assert not {"input_schema", "output_schema", "source"} & document.keys()
    matched = CandidateSummary.from_spec(
        SPEC,
        provider="engineering-ci",
        catalog_ref="ci",
        group_id="python.quality",
        matched_alias="vulture",
        asset_id="vulture",
    )
    assert matched.document()["group_id"] == "python.quality"
    assert matched.document()["matched_alias"] == "vulture"
    assert matched.document()["asset_id"] == "vulture"
    assert CandidateSummary.from_document(matched.document()) == matched
    with contract_error("invalid_document"):
        CandidateSummary.from_spec(object(), provider="p", catalog_ref="c")


def test_group_summaries_reference_members_without_copying_contracts():
    group = GroupSummary(
        "python.quality",
        "ci",
        (
            GroupMember("python.dead-code", "ci"),
            GroupMember("python.typecheck", "ci"),
        ),
        2,
        display_name="Python quality",
        aliases=("vulture", "pyright"),
    )
    assert GroupSummary.from_document(group.document()) == group
    assert all(
        set(member) == {"tool_id", "catalog_ref"}
        for member in group.document()["members"]
    )
    with contract_error("invalid_document"):
        GroupSummary("python.quality", "ci", (), 0)
    with contract_error("conflicting_identity"):
        GroupSummary(
            "python.quality",
            "ci",
            (GroupMember("python.dead-code", "ci"),) * 2,
            2,
        )
    with contract_error("invalid_document"):
        GroupSummary("python.quality", "ci", (GroupMember("a.b", "ci"),), 2)
    with contract_error("invalid_document"):
        GroupSummary.from_document(
            {**group.document(), "aliases": ["vulture", "vulture"]}
        )


def test_access_identity_is_composed_from_stable_host_names_only():
    assert compose_access_id("ci", "python.dead-code", "default") == (
        "ci:python.dead-code@default"
    )
    assert entry().access_id == "ci:python.dead-code@default"
    # Version and contract-digest changes are separate facts, not identity.
    revised = entry(
        contract_version="2", contract_sha256=SPEC.sha256, binding="not_required"
    )
    assert revised.access_id == entry().access_id
    with contract_error("invalid_query"):
        compose_access_id("CI", "python.dead-code", "default")
    with contract_error("invalid_document"):
        entry(access_id="ci:python.dead-code@other")
    with contract_error("invalid_document"):
        entry(catalog_ref="not a name")


def test_fact_states_stay_separated_and_never_default_positive():
    document = entry().document()
    assert document["assembly"] == "unknown"
    assert document["binding"] == "not_provided"
    assert document["execution_admission"] == "not_evaluated"
    assert document["availability"] == "unknown"
    # No combined readiness flag exists at any disclosure level.
    assert not {"ready", "callable", "allowed"} & document.keys()
    assert set(ASSEMBLY_STATES) == {"assembled", "missing", "unknown"}
    assert "unknown" in BINDING_STATES or "not_provided" in BINDING_STATES
    # discovery_scope is a disclosure claim, so it has no default at all.
    with pytest.raises(TypeError):
        AccessEntrySummary(
            tool_id="python.dead-code",
            catalog_ref="ci",
            entry_key="default",
            provider="engineering-ci",
            environment="dagger",
            purpose="Reports unused code.",
            contract_version="1",
            contract_sha256=SPEC.sha256,
        )


def test_binding_identity_and_reason_conditionals():
    for state in ("pending_validation", "valid", "invalid"):
        with contract_error("invalid_document"):
            entry(binding=state)
    for state in ("not_provided", "known_absent", "not_required"):
        with contract_error("invalid_document"):
            entry(binding=state, binding_id="b-1")
    documented = entry(binding="valid", binding_id="b-1")
    assert documented.document()["binding_id"] == "b-1"
    assert AccessEntrySummary.from_document(documented.document()) == documented
    # Negative facts require a structured reason; positive states forbid one.
    with contract_error("invalid_document"):
        entry(discovery_scope="excluded")
    with contract_error("invalid_document"):
        entry(execution_admission="rejected")
    with contract_error("invalid_document"):
        entry(binding="valid", binding_id="b-1", reason_code="unavailable")
    explained = entry(discovery_scope="excluded", reason_code="scope_excluded")
    assert explained.document()["reason_code"] == "scope_excluded"


def test_entry_source_keeps_the_native_contract_shape():
    native = {
        "kind": "dagger",
        "identity": "mod@rev:Object.fn",
        "interface_sha256": SPEC.sha256,
    }
    with_source = entry(source=native)
    assert with_source.document()["source"] == native
    assert AccessEntrySummary.from_document(with_source.document()) == with_source
    with contract_error("invalid_document"):
        entry(source={"kind": "dagger"})
    with contract_error("invalid_document"):
        entry(source={"kind": "dagger", "identity": "i", "interface_sha256": "z"})


def test_contract_detail_expands_only_here_and_reuses_toolspec_authority():
    contract = {**SPEC.document(), "contract_sha256": SPEC.sha256}
    detail = ContractDetail("python.dead-code", "ci", "default", contract)
    document = detail.document()
    assert document["contract"]["input_schema"] == {"type": "object"}
    assert document["contract"]["contract_sha256"] == SPEC.sha256
    assert ContractDetail.from_document(document) == detail
    with contract_error("invalid_document"):
        ContractDetail(
            "python.dead-code", "ci", "default", {**contract, "contract_sha256": ZERO}
        )
    with contract_error("invalid_document"):
        ContractDetail("python.typecheck", "ci", "default", contract)
    with contract_error("invalid_document"):
        ContractDetail("python.dead-code", "ci", "default", {**contract, "extra": 1})
    with contract_error("invalid_document"):
        ContractDetail(
            "python.dead-code",
            "ci",
            "default",
            {k: v for k, v in contract.items() if k != "effect"},
        )


def test_page_envelope_orders_and_separates_identity_namespaces():
    query = DiscoveryQuery(catalog_ref="ci", effect="check")
    first = CandidateSummary.from_spec(SPEC, provider="p", catalog_ref="ci")
    other_catalog = CandidateSummary.from_spec(
        SPEC, provider="host", catalog_ref="runtime"
    )
    page = DiscoveryPage("candidate-summary", 0, 10, 2, query, (first, other_catalog))
    assert DiscoveryPage.from_document(page.document()) == page
    assert "next_offset" not in page.document()
    paged = DiscoveryPage("candidate-summary", 0, 1, 2, query, (first,), next_offset=1)
    assert paged.document()["next_offset"] == 1
    with contract_error("conflicting_identity"):
        DiscoveryPage(
            "candidate-summary",
            0,
            10,
            2,
            query,
            (first, CandidateSummary.from_spec(SPEC, provider="x", catalog_ref="ci")),
        )
    with contract_error("invalid_document"):
        DiscoveryPage("candidate-summary", 0, 10, 2, query, ())
    empty = DiscoveryPage("candidate-summary", 0, 10, 0, query, ())
    assert DiscoveryPage.from_document(empty.document()) == empty


def test_pages_are_homogeneous_and_round_trip_every_item_kind():
    query = DiscoveryQuery()
    group = GroupSummary(
        "python.quality", "ci", (GroupMember("python.dead-code", "ci"),), 1
    )
    access = entry()
    for item_kind, items in (
        ("group-summary", (group,)),
        ("access-entry-summary", (access,)),
    ):
        page = DiscoveryPage(item_kind, 0, 10, len(items), query, items)
        assert DiscoveryPage.from_document(page.document()) == page
    with contract_error("invalid_document"):
        DiscoveryPage("group-summary", 0, 10, 2, query, (group, access))


def test_diagnostics_and_errors_are_not_business_results():
    diagnostic = DiscoveryDiagnostic(
        "unassembled",
        detail="entry lacks an adapter",
        ref="ci:python.dead-code@default",
    )
    assert DiscoveryDiagnostic.from_document(diagnostic.document()) == diagnostic
    failure = DiscoveryErrorDocument("unknown_reference", "no such catalog_ref")
    assert DiscoveryErrorDocument.from_document(failure.document()) == failure
    with contract_error("invalid_document"):
        DiscoveryDiagnostic("not-a-code")
    with contract_error("invalid_document"):
        DiscoveryErrorDocument("passed")
    assert set(DIAGNOSTIC_CODES) >= {"unknown", "unknown_input", "undisclosed"}
    assert set(ERROR_CODES) >= {"invalid_query", "conflicting_identity"}
    assert set(EFFECTS) == {"read", "check", "write"}
    assert set(ITEM_KINDS) == {
        "candidate-summary",
        "group-summary",
        "access-entry-summary",
    }


def test_documents_are_canonical_and_repeatable():
    documents = [
        DiscoveryQuery(query="x").document(),
        CandidateSummary.from_spec(SPEC, provider="p", catalog_ref="ci").document(),
        GroupSummary(
            "python.quality", "ci", (GroupMember("python.dead-code", "ci"),), 1
        ).document(),
        entry().document(),
        ContractDetail(
            "python.dead-code",
            "ci",
            "default",
            {**SPEC.document(), "contract_sha256": SPEC.sha256},
        ).document(),
        DiscoveryPage(
            "candidate-summary",
            0,
            10,
            1,
            DiscoveryQuery(),
            (CandidateSummary.from_spec(SPEC, provider="p", catalog_ref="ci"),),
        ).document(),
    ]
    for document in documents:
        assert canonical(document)
        assert document == dict(document)
