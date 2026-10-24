"""Query documents over the three records: paging, grammar, round trips."""

import pytest

from vesryn_tool_runtime import (
    DiscoveryContractError,
    DiscoveryDiagnostic,
    DiscoveryErrorDocument,
    DiscoveryPage,
    DiscoveryQuery,
    RecordError,
    open_record_store,
    record_document,
    record_from_document,
)


def contract_error(code):
    return pytest.raises(DiscoveryContractError, match=code)


@pytest.fixture
def library():
    handle = open_record_store()
    yield handle
    handle.close()


def test_query_filters_and_paging_reuse_the_existing_bounds():
    default = DiscoveryQuery()
    assert (default.offset, default.limit) == (0, 10)
    assert list(default.document()) == [
        "schema_version",
        "kind",
        "offset",
        "limit",
    ]
    full = DiscoveryQuery(
        query="vulnerability",
        operation="scan",
        domain="security",
        environment="dagger",
        effect="check",
        group_id="ci-security",
        catalog_ref="ci",
        offset=30,
        limit=50,
        discovery_id="caller-run-17",
    )
    again = DiscoveryQuery.from_document(full.document())
    assert again.document() == full.document()
    # The old capability grammar is gone: bare identities are tool keys.
    assert DiscoveryQuery(group_id="trivy").document()["group_id"] == "trivy"
    for bad in (
        lambda: DiscoveryQuery(limit=0),
        lambda: DiscoveryQuery(limit=51),
        lambda: DiscoveryQuery(offset=-1),
        lambda: DiscoveryQuery(effect="destroy"),
    ):
        with contract_error("invalid_query"):
            bad()


@pytest.mark.parametrize(
    "document",
    [
        {
            "schema_version": 2,
            "kind": "discovery-query",
            "offset": 0,
            "limit": 10,
        },
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


def test_pages_carry_the_records_themselves(library):
    """A page's items are the three records' own documents — read straight
    from the store, no parallel summary types."""
    asset = record_document(library.assets.get("trivy"))
    group = record_document(library.groups.get("ci-security"))

    query = DiscoveryQuery(group_id="ci-security")
    page = DiscoveryPage("tool-group", 0, 10, 1, query, (group,))
    assert DiscoveryPage.from_document(page.document()).document() == (page.document())

    mixed = DiscoveryPage("tool-asset", 0, 10, 1, query, (asset,))
    assert DiscoveryPage.from_document(mixed.document()).document() == (
        mixed.document()
    )

    records = tuple(
        record_document(item) for item in library.accesses.for_tool("trivy")
    )
    entries = DiscoveryPage("tool-access", 0, 10, 3, query, records)
    assert [item["access_id"] for item in entries.records] == [
        "trivy.cli",
        "trivy.sbom",
        "trivy.scan",
    ]

    # Off-page facts: next_offset appears only when more records exist.
    paged = DiscoveryPage("tool-access", 0, 1, 3, query, records[:1], next_offset=1)
    assert paged.document()["next_offset"] == 1
    with contract_error("invalid_document"):
        DiscoveryPage("tool-access", 0, 1, 3, query, records[:1])
    with contract_error("invalid_document"):
        DiscoveryPage("tool-access", 0, 10, 3, query, records[:2])


def test_records_round_trip_and_reject_bad_shapes(library):
    for record in (
        library.assets.get("trivy"),
        library.groups.get("ci-release"),
        library.accesses.get("trivy.scan"),
    ):
        assert record_from_document(record_document(record)) == record
    with pytest.raises(RecordError, match="invalid_record"):
        record_from_document({"tool_id": "trivy"})
    with pytest.raises(RecordError, match="invalid_record"):
        record_from_document(
            {
                "access_id": "x.run",
                "tool_id": "x",
                "method": "native",
                "target": "x",
                "contract": {},
                "summary": "s",
                "extra": 1,
            }
        )


def test_diagnostics_and_errors_are_not_business_results():
    diagnostic = DiscoveryDiagnostic(
        "unregistered", detail="no such tool", ref="trivy.old"
    )
    assert (
        DiscoveryDiagnostic.from_document(diagnostic.document()).document()
        == diagnostic.document()
    )
    failure = DiscoveryErrorDocument("unknown_reference", "no such catalog")
    assert (
        DiscoveryErrorDocument.from_document(failure.document()).document()
        == failure.document()
    )
    with contract_error("invalid_document"):
        DiscoveryDiagnostic("passed")
    with contract_error("invalid_document"):
        DiscoveryErrorDocument("not-a-code")


def test_legacy_conversion_happens_only_at_the_outermost_layer():
    """The temporary converter produces explicit conclusions: group members
    convert (catalog_ref dropped), access summaries cannot — no method or
    target. It is deleted once adaptation completes; nothing else imports
    it."""
    from vesryn_tool_runtime import legacy_convert

    old_group = {
        "group_id": "ci-security",
        "summary": "Security gates",
        "members": [{"tool_id": "trivy", "catalog_ref": "ci"}],
    }
    converted = legacy_convert.convert_legacy_group(old_group)
    assert converted is not None
    assert converted.members[0].tool_id == "trivy"
    assert converted.members[0].aliases == ()

    old_access = {
        "access_id": "ci:python.dead-code@default",
        "tool_id": "python.dead-code",
        "contract_version": "1",
        "contract_sha256": "0" * 64,
    }
    assert (
        legacy_convert.convert_legacy_access(old_access)
        == legacy_convert.LEGACY_UNSUPPORTED
    )
