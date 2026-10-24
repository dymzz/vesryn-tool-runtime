# Trusted security-policy consumption (TR-POLICY-01)

This is the Runtime side of the trusted security-policy contract published by
[engineering-ci #56](https://github.com/dymzz/engineering-ci/issues/56) (merged
as `c40fb69`; contract:
[security policy snapshots](https://github.com/dymzz/engineering-ci/blob/main/docs/architecture/security-policy.md)).
Delivery for [issue #13](https://github.com/dymzz/vesryn-tool-runtime/issues/13),
baseline main `29b99dc`.

The publisher owns authoring, publication, trust anchoring, reception and the
protected receiver state. Runtime **consumes** a verified snapshot and produces
the same decision documents ECI #57 consumes — it re-implements none of the
reception/trust machinery, keeps no second policy authority, and never treats
a selection's own `AssetPolicy.enabled` as a trusted security decision.

## Public signatures

```python
from vesryn_tool_runtime import (
    SecurityPolicyError,        # stable refusal code from the publisher set
    SecurityPolicySnapshot,     # parsed, structurally validated snapshot
    admit_protected_asset,      # the boundary gate (policy ∩ existing scope)
    decide_asset_admission,     # decision document for one real selection
)

SecurityPolicySnapshot.from_document(value) -> SecurityPolicySnapshot
decide_asset_admission(snapshot, selection, *, protected_profile,
                       access_id=None, now=None, superseded=False,
                       minimum_revision=None) -> dict
admit_protected_asset(snapshot, selection, *, protected_profile,
                      spec=None, scope=None, access_id=None, now=None,
                      superseded=False, minimum_revision=None) -> dict | None
```

- `snapshot` is a `SecurityPolicySnapshot` parsed from the
  `engineering-ci-security-policy-snapshot` document `engineering-ci policy
  receive` prints. Structural validation mirrors the publisher's own bounds
  (window ordering, revision ranges, complete six-field rule selectors,
  1–1000 rules, 1–32 profiles); failures are `policy_snapshot_invalid`.
  Verification itself happened at reception and is not redone.
- `selection` is a real `AssetSelection`. The asset echo is derived from it —
  `tool_id`, `release.version`, `{os, arch}` from the target,
  `release.source`, `release.sha256` as the digest — never invented.
- `now` accepts a tz-aware datetime or ISO-8601 string; the window is
  **re-checked at decision time** (`policy_expired` / `policy_not_yet_valid`
  as `unknown`), because a received snapshot can expire later.
- `superseded=True` mirrors the receiver-state verdict that a newer revision
  was accepted (`unknown`/`policy_superseded`). `minimum_revision` is the
  host's accepted-revision floor; a snapshot below it is refused as
  `policy_rollback` — an older policy can never re-admit a revoked asset.
- `access_id` (composed per the #27 field contract, e.g.
  `ci:python.dead-code@default`) is matched only when a rule actually limits
  one entry; a rule with `access_id` never matches a call without it.

## Decision semantics (identical to the publisher's contract)

- Rules match `tool_id` exactly plus optional `version`, `platform`
  (`{os, arch}`), `source`, `digest` and `access_id`; absent fields are
  wildcards. **Deny wins over allow**; a complete/cached asset never bypasses
  a matching deny. No matching rule is `unknown`/`no_matching_rule` — for a
  protected caller that is **not permitted**.
- A protected profile not covered by the policy is
  `unknown`/`protected_profile_not_covered`.
- The decision document has the exact publisher kind
  (`engineering-ci-security-policy-decision`) and keeps the **current policy
  identity** (`revision`, `sha256`, release) and the **original selection
  identity** (`selection_id` plus its own `AssetPolicy` revision) separate;
  neither is rewritten, and the decision never claims the old selection
  policy is current.

## The boundary gate

`admit_protected_asset` is called immediately before a protected delivery or
invocation:

- **Protected caller** (`protected_profile` given): a missing snapshot is
  `policy_state_missing` (never unknown-as-allowed); any non-`allow` decision
  raises `SecurityPolicyError` carrying the decision reason
  (`matched_deny`, `no_matching_rule`, `policy_expired`,
  `policy_superseded`, …). The existing `DiscoveryScope.admit(spec)` still
  applies independently when `spec`/`scope` are supplied — a security allow
  never widens scope, and scope never substitutes for policy.
- **Unprotected caller** (`protected_profile=None`): the gate is a no-op; the
  existing explicit authorization behavior is untouched. Ordinary discovery
  and `asset_view` never require a policy and never gain execution eligibility.
- Preparation success, cached bytes, an old receipt or the selection's own
  `enabled=true` never replace this admission; conversely a refusal never
  fakes an install failure — receipts and index facts stay exactly as they
  are, and only the new delivery/invocation is refused.
- Decisions are pure and offline: evaluating the currently accepted snapshot
  contacts no network, so a **synced disable rejects new use even when the
  publisher is unreachable**; offline evaluation never promises that an
  unsynced announcement has taken effect.

## Identity note

Policy rules match the tool primary key the consumer's catalog presents
(bare program key or a real, source-backed capability ID, per the #27 record
model). On this baseline, shared-asset selections carry their registered
capability IDs (e.g. `dependency.vulnerability-scan`); with the unified
registration stack (issues #32/#33, open PRs) bare tool keys select directly.
Runtime keeps no permanent legacy-identity mapping — writing rules against
the identity the consumer actually presents is the policy author's
responsibility (ECI #53).

## Errors

`SecurityPolicyError.code` reuses the publisher's stable codes; none is
invented here: `policy_snapshot_invalid`, `policy_state_missing`,
`policy_rollback`, `asset_invalid`, `clock_invalid`. Scope refusals keep the
existing `WorkflowError` semantics unchanged.
