# TR-DISC-01A — issue #27 delivery record

Source: [issue #27](https://github.com/dymzz/vesryn-tool-runtime/issues/27), stage A of
[issue #14](https://github.com/dymzz/vesryn-tool-runtime/issues/14). The issue's local
task-book path does not exist in this checkout; this record is created from the fetched
issue #27 body (same handling as the #6/#16/#18/#20 records).

Baseline: v0.3.0 main `3902efcb2154c82caf95c8d7d449f7268d68f6d1` (issue #12
completed and released). No release is performed here; the package version
stays 0.3.0.

Handoff identity: [PR #28](https://github.com/dymzz/vesryn-tool-runtime/pull/28)
(branch `codex/issue-27-discovery-field-contract`, rebased onto main `098bf4d`;
the PR is the stable identity); submitted for review without merging.

## Handoff

The single field authority is `src/vesryn_tool_runtime/discovery_contracts.py`,
described field-by-field in
[discovery field contracts](../../discovery-contracts.md). Public exports:
`DiscoveryQuery`, `DiscoveryPage`, `GroupSummary`, `GroupMember`,
`CandidateSummary`, `AccessEntrySummary`, `ContractDetail`,
`DiscoveryDiagnostic`, `DiscoveryErrorDocument`, `DiscoveryContractError` and
`compose_access_id`; enums and JSON Schemas are module constants.

Key decisions (full rationale in the doc):

- **Identity**: `catalog_ref`/`entry_key` are host-provided stable NAMEs for
  explicitly supplied inputs; `group_id` uses the `domain.group` grammar unique
  per catalog; `access_id` is exactly
  `"<catalog_ref>:<tool_id>@<entry_key>"`, never derived from bindings,
  addresses, paths or install locations, and stable across version/digest
  changes. Missing mapping basis ⇒ the entry stays unreported; nothing is
  guessed.
- **Fact separation**: Adapter assembly (`assembled`/`missing`/`unknown`),
  binding (`not_provided`/`known_absent`/`pending_validation`/`valid`/`invalid`/
  `not_required`), discovery scope (`matched`/`excluded`, no default),
  execution admission (`not_evaluated`/`admitted`/`rejected`) and availability
  (`unknown`/`available`/`unavailable`) are distinct fields with structured
  `reason_code` conditionals; no combined ready/callable flag exists, and no
  default states a positive fact.
- **Disclosure**: summaries never carry parameter schemas or copied contracts;
  `ContractDetail` expands the existing `ToolSpec` document (digest verified
  through `ToolSpec` itself) only at detail level; `total` counts disclosable
  results only; diagnostics cannot name hidden items.
- **Value rules**: strict `schema_version: 1` envelopes with unknown fields
  rejected; null never used (omission vs explicit-unknown enums);
  `discovery_id` is passthrough only; no content-derived identities at this
  layer.
- **Compatibility**: query paging reuses the existing bounds (limit 1–50,
  default 10); candidate fields derive from `ToolSpec.summary()` itself;
  `Catalog`'s duplicate-rejection invariant is untouched — multi-entry is
  expressed via host-named `catalog_ref`/`entry_key`, with no new registry.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| Complete, verifiable field foundation as code with schemas, serialization and validation — not docs-only, placeholders or fixed examples | `discovery_contracts.py` (~950 lines) with 8 document types, 7 JSON Schemas, strict `document()`/`from_document()` round-trips and `DiscoveryContractError` codes; exercised by `tests/test_discovery_contracts.py`. |
| All nine field domains covered with fixed semantics | Field dictionary in the doc, mirroring the code field-for-field; query/paging, groups, candidates, access entries, contract detail, assembly/binding/admission/availability facts, asset/policy references, results/diagnostics, versioning and unknown-value rules. |
| The five common decisions resolved once | Identity/namespaces, multi-entry without Catalog changes, fact sources with permission boundaries, summary/detail separation, single field source — see the decisions above and the doc's sections. |
| Only the field layer; no retrieval/ranking/admission/binding/health implementation | No such algorithm exists in the module; existing logic is referenced only for field semantics. |

Verified on 2026-10-24 with CPython 3.14.8 (this checkout's locked environment):

| Evidence | Result |
| --- | --- |
| New field-contract tests | 15 passed. |
| Full suite | 191 passed, 1 skipped — no regression. |
| Lint / format | `ruff check` clean; `ruff format --check .` clean repo-wide. |
| Packaging | the new module ships via the existing module-directory rule; no packaging change. |

Local-environment observation (pre-existing, not this delivery's regression):
the #8 concurrency case
`tests/test_native_assets.py::test_two_concurrent_preparations_publish_once`
flakes intermittently on this Windows host (with a pytest-cache `WinError 183`
warning); verified to fail identically on the unchanged v0.3.0 baseline while
this branch's changes were stashed. It is green in every CI run and belongs to
another group's file, so it is left untouched.

## Ownership for later #14 tasks

This task uniquely owns `discovery_contracts.py`,
`tests/test_discovery_contracts.py`, `docs/discovery-contracts.md` and the new
exports. Later group-retrieval / scope-diagnostic / entry-query tasks own only
their own modules, tests and docs, referencing this contract (imports, not
copies). Shared-field changes go back through this task/#14 once — the split
of those tasks happens after this handoff, per issue #27.
