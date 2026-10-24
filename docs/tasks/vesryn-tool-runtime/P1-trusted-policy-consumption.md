# TR-POLICY-01 — issue #13 delivery record

Source: [issue #13](https://github.com/dymzz/vesryn-tool-runtime/issues/13). The
issue's local task-book path does not exist in this checkout; this record is created
from the fetched issue #13 body.

Baseline: main `29b99dc` (v0.3.0 + #27 field contracts via PR #28 + #29 platform
fixes via PR #31). Publisher contract: [ECI #56], merged as `c40fb69`, read
only — its snapshot/decision builders (`src/engineering_ci/security_policy.py`)
and contract docs were consulted to mirror shapes and codes exactly; no ECI
code is imported. Git identity: `zcode <zcode@local>`.

## Handoff

`src/vesryn_tool_runtime/security_policy.py` + public exports
(`SecurityPolicySnapshot`, `SecurityPolicyError`, `decide_asset_admission`,
`admit_protected_asset`); full field/semantics documentation in
[security policy consumption](../../security-policy.md). Summary:

- **Decisions**: `decide_asset_admission(snapshot, selection, *, protected_profile,
  access_id=None, now=None, superseded=False, minimum_revision=None)` evaluates a
  real `AssetSelection` against a verified `engineering-ci-security-policy-snapshot`,
  producing the exact publisher decision document kind with identical reasons
  (`matched_allow`/`matched_deny`/`no_matching_rule`/`policy_expired`/
  `policy_not_yet_valid`/`protected_profile_not_covered`/`policy_superseded`),
  deny-over-allow, wildcard selectors, decision-time window re-check and the
  current-policy/original-selection identities kept separate.
- **Boundary gate**: `admit_protected_asset(...)` — protected calls require an
  actual snapshot and an `allow` decision (missing basis is `policy_state_missing`,
  never unknown-as-allowed; refusals raise `SecurityPolicyError` with the decision
  reason), and the existing `DiscoveryScope.admit` applies independently;
  unprotected callers are untouched (no-op). Offline by construction: a synced
  disable refuses new delivery/invocation with the publisher unreachable, and a
  refusal never rewrites receipts or index facts.
- **Anti-rollback at the boundary**: `minimum_revision` (the receiver-state floor)
  refuses older snapshots with `policy_rollback`; tool-version decisions stay the
  policy's business (a new revision may allow an older tool).
- **No duplication**: no reception/verification/state machinery, no second policy
  authority, no new status enums (codes are the publisher's stable set), and the
  selection's own `AssetPolicy.enabled` is never treated as trusted security.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| Cached SHA-correct asset usable under allow; synced disable refuses new delivery/invocation offline | `test_synced_disable_rejects_new_use_offline_while_cache_stays_honest`: revision-7 allow admits; revision-8 deny refuses repeatedly, fully offline; the recorded installation stays `present` and the selection document is unchanged. |
| Protected policy missing/expired/rolled-back refused; offline promises nothing unsynced | `test_missing_expired_or_rolled_back_trust_refuses_protected_use`: `policy_state_missing`, `policy_expired` (window re-check at decision time), `policy_rollback` (below the accepted floor). Decisions evaluate only the presented snapshot — no network, no unsynced effect. |
| Two consumers' selections and unrelated assets unaffected; history kept; identities separately readable | `test_unrelated_assets_and_unprotected_calls_stay_unaffected`: an osv rule leaves the trivy selection `unknown/no_matching_rule`; unprotected gate is a no-op; discovery still needs no policy; the decision carries `selection_id` + original `AssetPolicy` revision apart from the policy revision/sha/release. |
| Scope overreach not admitted by security allow; discovery creates no eligibility/installation | `test_scope_overreach_is_not_admitted_by_a_security_allow` (WorkflowError despite an allow decision) and the discovery assertion in the unaffected test. |
| Minimal public signatures, decision identity/scope, structured errors and examples for ECI #57 / discovery/evidence reuse; existing artifact/asset interfaces not duplicated | The signatures above, the exact decision kind ECI #57 consumes, publisher-stable error codes, and the doc's example section; no artifact/index/backend surface was copied or modified. |

Additional coverage: the full decision-contract shape (asset echo from the real
selection, policy/selection identity separation), deny-over-allow, platform and
`access_id` limited rules, `policy_superseded`, eleven malformed-snapshot
rejections, and canonical round-trips.

## Verification (2026-10-24, CPython 3.14.8, locked env)

| Evidence | Result |
| --- | --- |
| New policy tests | 19 passed. |
| Full suite | 196 passed, 1 skipped (main baseline 176 + 19 + the stacked #29/#27 suites already in main) — no regression. |
| Lint / format | `ruff check` clean; `ruff format --check` clean repo-wide. |
| Publisher conformance | Snapshot validation bounds and decision semantics transcribed from ECI `c40fb69` sources (`load_policy`, `_snapshot`, `_decide_snapshot`, `_matches`, `_asset_input`) and checked against the committed `config/security-policy.example.json` shapes; no ECI execution was required. |

Not delivered here (by design): reception/trust verification and protected state
storage stay with ECI (`policy receive`); execution-entry admission wiring is
ECI #57's consumption of these decisions; no ECI, Vesryn or host configuration
was modified, and no policy publication or release was performed.
