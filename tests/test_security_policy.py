"""Trusted policy consumption: snapshot decisions and the boundary gate."""

import pytest

from vesryn_tool_runtime import (
    AssetFile,
    AssetIndex,
    AssetPolicy,
    AssetReceipt,
    AssetSelection,
    AssetTarget,
    Catalog,
    DiscoveryScope,
    SecurityPolicyError,
    SecurityPolicySnapshot,
    ToolResult,
    ToolSpec,
    admit_protected_asset,
    decide_asset_admission,
    load_shared_definitions,
    register_shared_definitions,
)
from vesryn_tool_runtime.documents import WorkflowError

LINUX = AssetTarget("linux", "x86_64")
POLICY = AssetPolicy("eci-tools-2026-10-23")
NOW = "2026-10-24T12:00:00+00:00"


def rule(rule_id, effect, tool_id, **selector):
    asset = {
        "tool_id": tool_id,
        "access_id": None,
        "version": None,
        "platform": None,
        "source": None,
        "digest": None,
    }
    asset.update(selector)
    return {
        "rule_id": rule_id,
        "effect": effect,
        "reason": f"{effect} {rule_id}",
        "asset": asset,
    }


def snapshot(rules, *, revision=7, profiles=("ci-security",)):
    return SecurityPolicySnapshot(
        {
            "schema_version": 1,
            "kind": "engineering-ci-security-policy-snapshot",
            "policy": {
                "revision": revision,
                "minimum_revision": 1,
                "issued_at": "2026-10-24T00:00:00Z",
                "not_before": "2026-10-24T00:00:00Z",
                "expires_at": "2027-10-24T00:00:00Z",
                "publisher": {
                    "repository": "dymzz/engineering-ci",
                    "workflow": ".github/workflows/release.yml",
                },
                "protected_profiles": list(profiles),
                "rules": rules,
                "sha256": "a" * 64,
                "size": 1234,
            },
            "publication": {
                "sha256": "b" * 64,
                "published_at": "2026-10-24T09:00:00Z",
            },
            "release": {"repository": "dymzz/engineering-ci", "tag": "v0.7.0"},
            "verified_at": "2026-10-24T09:30:00Z",
            "state": {"initialized": True, "previous_revision": 6},
        }
    )


def catalog_with_osv():
    record = next(
        item
        for item in load_shared_definitions("native.json")
        if item.definition.asset_id == "osv-scanner"
    )
    tools = Catalog()
    tools.provider_name = "policy-tests"
    tools.register(
        ToolSpec("dependency.vulnerability-scan", {}, {}, effect="check"), None
    )
    register_shared_definitions(tools, (record,))
    return tools, record


def osv_selection(tools=None):
    tools = tools or catalog_with_osv()[0]
    return tools.select_asset(
        "dependency.vulnerability-scan", target=LINUX, policy=POLICY
    )


def trivy_selection():
    record = next(
        item
        for item in load_shared_definitions("security.json")
        if item.definition.asset_id == "trivy"
    )
    tools = Catalog()
    tools.provider_name = "policy-tests"
    tools.register(ToolSpec("example.trivy", {}, {}, effect="check"), None)
    register_shared_definitions(tools, (record,))
    return tools.select_asset("example.trivy", target=LINUX, policy=POLICY)


def cached_receipt(tmp_path, selection):
    """Record a real verified installation: the entry file exists and hashes."""
    import hashlib

    from vesryn_tool_runtime import native_asset_directory

    location = native_asset_directory(tmp_path, selection)
    location.mkdir(parents=True, exist_ok=True)
    content = selection.release.sha256.encode()
    (location / "osv-scanner").write_bytes(content)
    index = AssetIndex(tmp_path)
    index.record(
        AssetReceipt(
            selection,
            ToolResult("passed", 0, executed=True, complete=True, current=True),
            locator=str(location),
            files=(AssetFile("osv-scanner", hashlib.sha256(content).hexdigest()),),
            verified_source_sha256=selection.release.sha256,
        )
    )
    return index


def test_decision_contract_matches_the_publisher_shape():
    tools, record = catalog_with_osv()
    selection = osv_selection(tools)
    allow = snapshot(
        [
            rule(
                "allow-osv",
                "allow",
                "dependency.vulnerability-scan",
                version="2.6.0",
                platform={"os": "linux", "arch": "x86_64"},
                digest=record.definition.releases[0].sha256,
            )
        ]
    )
    decision = decide_asset_admission(
        allow, selection, protected_profile="ci-security", now=NOW
    )
    assert decision["kind"] == "engineering-ci-security-policy-decision"
    assert decision["decision"] == "allow" and decision["allowed"] is True
    assert decision["reason"] == "matched_allow"
    assert decision["rule_id"] == "allow-osv"
    # Current policy identity and the original selection identity are kept
    # separate; the old AssetPolicy revision is echoed, never merged.
    assert decision["policy"]["revision"] == 7
    assert decision["policy"]["sha256"] == "a" * 64
    assert decision["policy"]["release"] == {
        "repository": "dymzz/engineering-ci",
        "tag": "v0.7.0",
    }
    assert decision["selection"]["selection_id"] == selection.selection_id
    assert decision["selection"]["policy_revision"] == POLICY.revision
    # The asset echo is exactly this selection's facts.
    assert decision["asset"] == {
        "tool_id": "dependency.vulnerability-scan",
        "access_id": None,
        "version": "2.6.0",
        "platform": {"os": "linux", "arch": "x86_64"},
        "source": selection.release.source,
        "digest": selection.release.sha256,
    }
    assert decision["protected_profile"] == "ci-security"
    assert decision["evaluated_at"] == "2026-10-24T12:00:00Z"


def test_deny_wins_and_unmatched_or_wildcard_mismatch_is_unknown():
    selection = osv_selection()
    both = snapshot(
        [
            rule("allow-all-osv", "allow", "dependency.vulnerability-scan"),
            rule(
                "deny-digest",
                "deny",
                "dependency.vulnerability-scan",
                digest=selection.release.sha256,
            ),
        ]
    )
    denied = decide_asset_admission(
        both, selection, protected_profile="ci-security", now=NOW
    )
    assert (denied["decision"], denied["reason"]) == ("deny", "matched_deny")
    assert denied["allowed"] is False
    # A rule limited to another platform does not match; unknown is not allowed.
    elsewhere = snapshot(
        [
            rule(
                "a",
                "allow",
                "dependency.vulnerability-scan",
                platform={"os": "windows", "arch": "x86_64"},
            )
        ]
    )
    unknown = decide_asset_admission(
        elsewhere, selection, protected_profile="ci-security", now=NOW
    )
    assert (unknown["decision"], unknown["reason"]) == ("unknown", "no_matching_rule")
    assert unknown["allowed"] is False
    # access_id limits a rule to one entry; without that entry it never matches.
    keyed = snapshot(
        [rule("a", "allow", "dependency.vulnerability-scan", access_id="ci:x@y")]
    )
    assert (
        decide_asset_admission(
            keyed, selection, protected_profile="ci-security", now=NOW
        )["reason"]
        == "no_matching_rule"
    )


def test_window_recheck_profile_coverage_and_superseded_are_unknown():
    selection = osv_selection()
    allow = snapshot([rule("a", "allow", "dependency.vulnerability-scan")])
    expired = SecurityPolicySnapshot(
        {
            **allow.document,
            "policy": {
                **allow.document["policy"],
                "expires_at": "2026-10-24T01:00:00Z",
            },
        }
    )
    assert (
        decide_asset_admission(
            expired, selection, protected_profile="ci-security", now=NOW
        )["reason"]
        == "policy_expired"
    )
    future = SecurityPolicySnapshot(
        {
            **allow.document,
            "policy": {
                **allow.document["policy"],
                "not_before": "2026-10-25T00:00:00Z",
                "expires_at": "2027-10-25T00:00:00Z",
            },
        }
    )
    assert (
        decide_asset_admission(
            future, selection, protected_profile="ci-security", now=NOW
        )["reason"]
        == "policy_not_yet_valid"
    )
    assert (
        decide_asset_admission(
            allow, selection, protected_profile="release-gates", now=NOW
        )["reason"]
        == "protected_profile_not_covered"
    )
    assert (
        decide_asset_admission(
            allow, selection, protected_profile="ci-security", now=NOW, superseded=True
        )["reason"]
        == "policy_superseded"
    )


def test_synced_disable_rejects_new_use_offline_while_cache_stays_honest(tmp_path):
    """Acceptance: a cached SHA-correct asset is usable under an allowing
    policy; after the disable syncs (revision 8 deny), new protected use is
    refused entirely offline, and the refusal never fakes an install failure."""
    tools, _ = catalog_with_osv()
    selection = osv_selection(tools)
    index = cached_receipt(tmp_path, selection)
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    spec = tools.resolve("dependency.vulnerability-scan")[0]

    allowing = snapshot([rule("allow-osv", "allow", "dependency.vulnerability-scan")])
    allowed = admit_protected_asset(
        allowing,
        selection,
        protected_profile="ci-security",
        spec=spec,
        scope=scope,
        now=NOW,
    )
    assert allowed["allowed"] is True

    disabled = snapshot(
        [rule("deny-osv", "deny", "dependency.vulnerability-scan")], revision=8
    )
    for _ in range(2):  # repeated attempts stay refused; nothing warms up
        with pytest.raises(SecurityPolicyError) as error:
            admit_protected_asset(
                disabled,
                selection,
                protected_profile="ci-security",
                spec=spec,
                scope=scope,
                now=NOW,
            )
        assert error.value.code == "matched_deny"
    # The cached installation fact is untouched and still readable; only the
    # new admission is refused. No network, backend or installer is involved.
    assert index.installed(selection)["status"] == "present"
    assert selection.document() == osv_selection(tools).document()


def test_missing_expired_or_rolled_back_trust_refuses_protected_use():
    selection = osv_selection()
    with pytest.raises(SecurityPolicyError) as missing:
        admit_protected_asset(None, selection, protected_profile="ci-security", now=NOW)
    assert missing.value.code == "policy_state_missing"
    base = snapshot([rule("a", "allow", "dependency.vulnerability-scan")]).document
    expired = SecurityPolicySnapshot(
        {
            **base,
            "policy": {
                **base["policy"],
                "expires_at": "2026-10-24T01:00:00Z",
            },
        }
    )
    with pytest.raises(SecurityPolicyError) as past:
        admit_protected_asset(
            expired, selection, protected_profile="ci-security", now=NOW
        )
    assert past.value.code == "policy_expired"
    rollback = snapshot([rule("a", "allow", "dependency.vulnerability-scan")])
    with pytest.raises(SecurityPolicyError) as old:
        admit_protected_asset(
            rollback,
            selection,
            protected_profile="ci-security",
            now=NOW,
            minimum_revision=8,
        )
    assert old.value.code == "policy_rollback"


def test_unrelated_assets_and_unprotected_calls_stay_unaffected():
    osv = osv_selection()
    trivy = trivy_selection()
    policy = snapshot([rule("allow-osv", "allow", "dependency.vulnerability-scan")])
    # The unrelated consumer's selection evaluates on its own identity and is
    # unknown — never collaterally denied or allowed.
    other = decide_asset_admission(
        policy, trivy, protected_profile="ci-security", now=NOW
    )
    assert (other["decision"], other["reason"]) == ("unknown", "no_matching_rule")
    assert (
        decide_asset_admission(policy, osv, protected_profile="ci-security", now=NOW)[
            "decision"
        ]
        == "allow"
    )
    # Unprotected callers keep the existing explicit authorization behavior:
    # the gate is a no-op and ordinary discovery needs no policy at all.
    assert admit_protected_asset(policy, trivy, protected_profile=None, now=NOW) is None
    tools = Catalog()
    tools.register(ToolSpec("example.trivy", {}, {}, effect="check"), None)
    page = tools.page(limit=5)
    assert page["total"] == 1  # discovery neither installs nor authorizes


def test_scope_overreach_is_not_admitted_by_a_security_allow():
    tools, _ = catalog_with_osv()
    selection = osv_selection(tools)
    allow = snapshot([rule("allow-osv", "allow", "dependency.vulnerability-scan")])
    spec = tools.resolve("dependency.vulnerability-scan")[0]
    with pytest.raises(WorkflowError):
        admit_protected_asset(
            allow,
            selection,
            protected_profile="ci-security",
            spec=spec,
            scope=DiscoveryScope(permissions=frozenset({"read"})),
            now=NOW,
        )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(kind="other-kind"),
        lambda d: d.update(extra=1),
        lambda d: d["policy"].update(rules=[]),
        lambda d: d["policy"].update(sha256="nothex"),
        lambda d: d["policy"].update(revision=0),
        lambda d: d["policy"].update(minimum_revision=99),
        lambda d: d["policy"].update(expires_at="2026-01-01T00:00:00Z"),
        lambda d: d["policy"]["rules"][0].update(missing_key=1),
        lambda d: d["policy"]["rules"][0]["asset"].pop("digest"),
        lambda d: d["policy"]["rules"].append(dict(d["policy"]["rules"][0])),
        lambda d: d.update(verified_at="not-a-time"),
    ],
)
def test_invalid_snapshots_are_refused(mutate):
    document = {
        **snapshot([rule("a", "allow", "t")]).document,
    }
    mutate(document)
    with pytest.raises(SecurityPolicyError) as error:
        SecurityPolicySnapshot(document)
    assert error.value.code == "policy_snapshot_invalid"


def test_decision_documents_round_trip_and_stay_canonical():
    from vesryn_tool_runtime.documents import canonical

    selection = osv_selection()
    allow = snapshot([rule("a", "allow", "dependency.vulnerability-scan")])
    decision = decide_asset_admission(
        allow, selection, protected_profile="ci-security", now=NOW
    )
    assert canonical(decision)
    assert AssetSelection.from_document(selection.document()) == selection
