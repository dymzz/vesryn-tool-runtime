# Progressive group discovery and bounded member matching (TR-DISC-01E)

Public handoff for [issue #35](https://github.com/dymzz/vesryn-tool-runtime/issues/35)
(TR-DISC-01E / 14-E, child of [#14](https://github.com/dymzz/vesryn-tool-runtime/issues/14)),
stacked on the entry-resolution delivery of [#34](https://github.com/dymzz/vesryn-tool-runtime/issues/34)
and the registration of [#32](https://github.com/dymzz/vesryn-tool-runtime/issues/32).
It reads registered groups, members and the same Scope judgement as entry
resolution; it never installs, starts Dagger, creates a Binding or executes a tool.

## Public signatures

```python
discover_groups(catalog, *, catalog_ref, scope, query="", offset=0, limit=10,
                members_limit=5) -> DiscoveryPage   # item_kind="group-summary"
group_summary(catalog, group_id, *, catalog_ref, scope,
              members_limit=50) -> GroupSummary
discover_group_members(catalog, group_id, *, catalog_ref, scope, query="",
                       offset=0, limit=10) -> DiscoveryPage  # item_kind="candidate-summary"
```

Bounds and defaults come from the existing #27 page limits: `limit` 1–50
(default 10), `offset` ≥ 0, `members_limit` 1–50 (default 5). Ordering is
deterministic: groups by `group_id`, member candidates by `tool_id`; a summary's
members stay in registration order. `next_offset` is present exactly when a next
page exists.

## The progressive flow

1. `discover_groups(...)` enumerates the groups the caller may see. Each item is
   the existing #27 `GroupSummary`: identity, display metadata, aliases and a
   **bounded** member list of references. No contract, Schema or asset version is
   copied into the summary.
2. `discover_group_members(...)` answers "which tools in this group match this
   purpose/alias?" with #27 `CandidateSummary` items: `tool_id`, the group
   context (`group_id`), the matched alias when applicable, and summary facts —
   never parameter Schemas.
3. The selected `tool_id` goes to #34's `resolve_tool_access(...)` once for its
   entries and contracts; the ToolAsset does not have to be read again.

## Scope, disclosure and bounds

- Every member passes the same `DiscoveryScope.decision(spec)` used by entry
  resolution. An explicit `scope.available` set is applied to every member,
  including asset-only tools that have no environment/effect fact. Filtering
  happens before ordering and paging.
- A group with no visible member is not disclosed at all: it appears in no item,
  count or diagnostic, so hidden members cannot be inferred from a total.
- `member_count` equals the number of disclosed members in that summary. When a
  group has more visible members than `members_limit`, the summary carries an
  `undisclosed` diagnostic naming the already-disclosed group
  ("member list is bounded; use group member discovery for the rest"). The page
  therefore never reports a truncated group as complete.
- Member candidates count only members with a registered callable contract; an
  aggregate `unregistered` diagnostic states that some members have none,
  without naming them. Asset-only members (a registered `ToolAsset` without a
  `ToolSpec`) are still disclosed as group-member references.
- An empty result only describes this Catalog, Scope and query. It never claims
  that anything is globally unregistered or that execution failed.

## Matching

Queries are token containment over the group id, display name, description and
aliases (case-insensitive, `[a-z0-9]+` tokens); all query tokens must appear. A
match through an alias is reported as `matched_alias` and never creates a new
tool or capability identity. There is no ranking service, LLM or index: ordering
is the deterministic sort above.

The issue's example names are preserved as registered values: `trivy` stays one
`ToolAsset` referenced by both `ci.security` and `ci.release` (whose aliases carry
`ci-security` / `ci-release` / `sbom`). A tool registered once is not duplicated
per group, and per-group purpose lives in that group's description/aliases.

## Evidence

The directed tests use the real records the earlier tasks delivered:

- `trivy` from the bundled `shared_assets/security.json` (asset-only, one record,
  referenced by two groups).
- `pytest.artifacts` from the saved engineering-ci introspection snapshot of #34
  (`github.com/dymzz/engineering-ci@9949e22…`, contract `9386a800…`), exposed
  with `domain="test"` so it can appear as a candidate summary. Domain and
  description are metadata outside the contract digest.
- `ci.security`, `ci.release`, `ci.quality` group records with descriptions and
  aliases; the tests assert the records survive enumeration, alias queries pick
  the right group, Scope filtering precedes paging, and member pages continue
  stably.

The verification details (fixture identity, digests, counts) are recorded in
[the verification record](../verification/tr-disc-01e.json). No Dagger function
was executed; a test patches `subprocess.run` to fail and discovery still works.

## Boundaries

- Group membership is a registration fact, not authorization, installation or a
  callable contract. A visible member still needs entry resolution, Scope
  admission and a Binding before any invocation.
- The member-candidate page pages over matching candidates, not over raw group
  members: when a group has asset-only members, candidate offsets and the
  summary's reference list are different views. This is deliberate — one view
  states registration, the other states callable contracts.
- Group ranking, alias scoring and search services remain out of scope; so do
  MCP/CLI consumers, installation and invocation.

## Consumer handoff

- Vesryn #31: `discover_groups` → pick group → `discover_group_members` → pick
  `tool_id` → `resolve_tool_access` → `resolve_access` for a specific entry.
  Map `undisclosed`/`unregistered` diagnostics and empty pages to protocol
  states; do not re-derive Scope or parse error text.
- #15: the selected `tool_id`/`access_id` and its contract come from the same
  read path; Binding creation and admission stay with #15.

Up: [Access entry resolution](access-resolution.md) · [Discovery field contracts](discovery-contracts.md) · [Documentation](README.md).
