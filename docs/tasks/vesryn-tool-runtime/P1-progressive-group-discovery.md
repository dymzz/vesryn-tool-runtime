# TR-DISC-01E — issue #35 delivery record

Source: [issue #35](https://github.com/dymzz/vesryn-tool-runtime/issues/35), stage E of
[issue #14](https://github.com/dymzz/vesryn-tool-runtime/issues/14). The issue's local
task-book path did not exist in this checkout; this record is created from the fetched
issue #35 body, same handling as #16/#27/#32/#34.

Baseline: `dsh-34-tool-access-resolution` at `c245f9e` (v0.3.0 + #27 fields + #32
registration + #34 entry resolution). This branch is stacked on #34's still-open branch
because #35 consumes its Scope judgement and entry query; #32/#34 are reviewed together
with #14 later. Package version stays 0.3.0; no release is performed.

## Handoff

- Branch: `dsh-35-progressive-group-discovery` (issue-id naming), stacked on
  `dsh-34-tool-access-resolution`; commit `8292094`,
  [PR #39](https://github.com/dymzz/vesryn-tool-runtime/pull/39) against the #34
  branch. The repository's CI workflow only runs for pull requests whose base is
  `main`, so this stacked PR reports no checks; the full suite and lint were run
  locally on the recorded head. CI runs again when the parent branches merge and
  GitHub retargets this PR to `main`.
- Commit: `codex` author and committer (per the issue's Git identity rule).
- Files:
  - `src/vesryn_tool_runtime/group_discovery.py` — `discover_groups`,
    `group_summary`, `discover_group_members`.
  - `src/vesryn_tool_runtime/contracts.py` — `Catalog.groups()` read surface.
  - `src/vesryn_tool_runtime/__init__.py` — public exports.
  - `tests/test_group_discovery.py` — 13 directed tests.
  - `tests/fixtures/dagger/engineering-ci-9949e22.exposures.toml` — adds the
    `domain="test"` metadata needed to appear as a candidate summary (domain is
    outside the contract digest; the contract stays `9386a800…`).
  - `docs/group-discovery.md`, this record, `docs/verification/tr-disc-01e.json`,
    `docs/README.md` link.

## Decisions

- **Bounded disclosure, two views.** A group summary lists references only (no
  contracts); its member list is capped by `members_limit` (default 5) and the
  page states the boundary with an `undisclosed` diagnostic naming the disclosed
  group. `discover_group_members` is the paged view over matching **contract-backed**
  candidates, so its offsets are candidate offsets, not raw member offsets. This is
  documented rather than pretending a truncated group is complete.
- **Scope reuse.** Member filtering uses #34's `DiscoveryScope.decision`; an explicit
  `scope.available` set also applies to asset-only members, which have no
  environment/effect fact. A group with no visible member is not disclosed at all.
- **Matching without a new index.** Token containment over group id/display
  name/description/aliases, deterministic ordering (`group_id`, then `tool_id`),
  `matched_alias` reported when the match came through an alias. No ranking
  service, LLM or duplicate registry.
- **Real records first.** `trivy` stays one asset-only `ToolAsset` in two groups;
  `pytest.artifacts` is the real engineering-ci contract from #34 (same digest),
  exposed with a domain so it can be a candidate summary. No synthetic tools are
  used in the real-data tests; synthetic specs appear only in the member-paging test.

## Directed acceptance

| Issue criterion | Result | Evidence |
| --- | --- | --- |
| trivy, ci-security/ci-release and per-group purpose/aliases survive public discovery; one ToolAsset across groups | passed | Group summaries keep the registered ids, descriptions and aliases; `trivy` appears in `ci.security` and `ci.release` while `Catalog.asset_for("trivy")` is one record; aliases `ci-security`/`ci-release` query the right group. |
| Same alias in different groups matches per group purpose; deterministic order; unrelated query returns nothing | passed | `evidence` matches both `ci.quality` and `ci.release` (ordered by group id); `sbom` matches `ci.release` with `matched_alias="sbom"`; `nonexistent-topic` returns total 0, no items and no diagnostics. |
| Environment/permission/availability filtering precedes ordering and paging; same Scope judgement as direct queries; hidden members/totals not leaked | passed | `available={"pytest.artifacts"}` reduces `ci.release` to one member and hides `ci.security`; `environment="host"` hides the contract-backed member and the group that lost every member; the hidden tool id is absent from the document. |
| Large groups have real member bounds and continuation; initial results load no contracts | passed | `members_limit=1` reports `member_count=1` plus the `undisclosed` boundary; member page paging continues stably (3 synthetic members, limit 2 → next_offset 2); summaries contain no `input_schema`/`output_schema`. |
| Selected `tool_id` gets its contract through one D query; known tools/entries stay directly readable | passed | `discover_group_members` returns the candidate, then `resolve_tool_access` returns the entry and the same contract digest without an extra asset read. |
| Empty result, unmet prerequisite and unknown availability are not reported as global unregistered/execution failure; queries do not install/start Dagger/create Binding | passed | Empty query has no diagnostics; asset-only members yield an aggregate `unregistered` diagnostic only in the candidate view while the group summary keeps the reference; `subprocess.run` patched to fail and discovery still succeeds. |
| Public signatures, page defaults/limits, a group-discovery sample and directed results for Vesryn #31 | passed | `docs/group-discovery.md` with signatures, defaults (limit 10/50, members 5/50), ordering and the progressive flow; verification JSON records the tests. |

## Not verified

- Ranking or alias scoring beyond deterministic containment.
- Installation/execution of member tools; Dagger or backend health.
- Binding creation/verification or admission for a selected member (#15).
- Vesryn #31 MCP mapping and engineering-ci consumption of this flow.

## Verification

- New tests: 13 passed; full suite: 223 passed, 1 skipped.
- `ruff check src tests` and `ruff format --check src tests` clean.
- Recorded details: [verification/tr-disc-01e.json](../../verification/tr-disc-01e.json),
  [group discovery](../../group-discovery.md).

Environment note: the full suite ran unconfined because the Windows sandbox rejects
pytest's `0o700` temporary directories; work happened in the isolated worktree
`.worktrees/dsh-35-progressive-group-discovery` because the shared checkout is in use
by other tasks.
