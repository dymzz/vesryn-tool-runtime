# TR-DISC-01D — issue #34 delivery record

Source: [issue #34](https://github.com/dymzz/vesryn-tool-runtime/issues/34), stage D of
[issue #14](https://github.com/dymzz/vesryn-tool-runtime/issues/14). The issue's local
task-book path did not exist in this checkout; this record is created from the fetched
issue #34 body, same handling as #16/#27/#32.

Baseline: `codex/issue-32-unified-tool-registration` at `e8967b1` (v0.3.0 + #27 field
contracts + #32 unified registration). This branch is stacked on #32's still-open
branch because #34 consumes its registration/read surface; the #32 branch itself is
being reviewed together with #14 later. Package version stays 0.3.0; no release or
publication is performed.

## Handoff

- Branch: `dsh-34-tool-access-resolution` (issue-id naming), stacked on
  `codex/issue-32-unified-tool-registration`; commit `882748a`,
  [PR #38](https://github.com/dymzz/vesryn-tool-runtime/pull/38) against the #32
  branch. The repository's CI workflow only runs for pull requests whose base is
  `main`, so this stacked PR reports no checks; the full suite and lint were run
  locally on the recorded head instead. CI runs again when #32 merges and GitHub
  retargets this PR to `main`.
- Commit: `codex` author and committer (per the issue's Git identity rule).
- Files:
  - `src/vesryn_tool_runtime/access_resolution.py` — new resolution module
    (`AccessResolution`, `resolve_tool_access`, `resolve_access`).
  - `src/vesryn_tool_runtime/scope.py` — `ScopeDecision` and the single
    `DiscoveryScope.decision` authority (`matches` delegates to it).
  - `src/vesryn_tool_runtime/discovery_contracts.py` — access-id registration rule
    (composed default, host-registered identity accepted).
  - `src/vesryn_tool_runtime/contracts.py` — `Catalog.has_tool` /
    `Catalog.accesses_for` read surface.
  - `src/vesryn_tool_runtime/__init__.py` — public exports.
  - `tests/test_access_resolution.py` + `tests/fixtures/dagger/` — directed tests and
    the saved real contract snapshot.
  - `tests/test_discovery_contracts.py` — updated #27 assertion for the relaxed
    access-id rule.
  - `docs/access-resolution.md`, this record, `docs/verification/tr-disc-01d.json`,
    `docs/README.md` link.

## Decisions

- **One Scope authority.** `DiscoveryScope.decision(spec)` reports the matched fact or
  the caller's constraint (`environment`, `effect`, `availability`, `constraint`);
  `matches()` delegates, and #15/#35 consume the same decision. No new error family
  and no "ready" flag.
- **Access identity.** `access_id` is the host-registered entry identity. The composed
  `catalog_ref:tool_id@entry_key` form stays the default when omitted, but a host may
  register its own bounded value such as `trivy.scan`, as #34 requires. This is an
  additive relaxation of #27's field rule (old documents stay valid); the #27 document
  itself is not edited here and should be reconciled once by the #14 integrator.
- **One contract per tool.** Entries are access paths to the tool's registered
  `ToolSpec` contract (two entry keys or two catalogs). A per-entry distinct call
  contract is not represented by the #27/#32 model; a differing recorded
  `contract_sha256` is reported as `unknown` and never expanded into a contract.
- **Real contract evidence** is a saved, unmodified Dagger introspection snapshot of
  engineering-ci `9949e22…` (`EngineeringCi.repositoryTestArtifacts`, `main.py:122`),
  parsed offline by the existing `dagger_discovery.discover`. Only mapping is claimed,
  never execution.

## Directed acceptance

| Issue criterion | Result | Evidence |
| --- | --- | --- |
| Two real registered entries resolve separately; method/target/contract agree with the source; an old internal id does not rename the tool | passed | Two entries (`host-registered` and composed forms) of the real `pytest.artifacts` contract resolve by tool id and by each access id; contract digest `9386a800…` and source identity `…@9949e22…/EngineeringCi.repositoryTestArtifacts` match the saved snapshot. |
| Selecting `tool_id` returns applicable entries and contracts in one query; bounds are explicit | passed | `resolve_tool_access` returns entries and `ContractDetail`s together; `total`/`next_offset` are over disclosed entries; paging tests cover limit/offset and invalid bounds. |
| Unauthorized/hidden/no-entry/unbound/unknown availability stay accurate and non-leaking under the same Scope judgement | passed | Scope parametrized tests (environment/effect/availability/constraint) exclude before paging; `undisclosed` never names hidden ids; `unregistered` covers a registered asset-only tool; entry facts surface as `unassembled`/`binding_invalid`/`unavailable` with disclosed refs. |
| Queries trigger no Dagger, install, binding write or execution; a contract is not backend readiness | passed | A test patches `subprocess.run` to fail and resolution still succeeds; no write/probe code path exists; availability stays `unknown` unless recorded. |
| Independent real contract with original revision/source; static mapping distinct from execution | passed (parsing only) | Dagger introspection of ECI `9949e22…`, recorded snapshot SHA-256, contract and interface digests; no engine call and no function execution in the tests. |
| Public signatures, result/error definitions, candidate commit/package and directed evidence for #15/#35; unknown-state boundaries stated | passed | `docs/access-resolution.md`; verification JSON; tests; explicit `not_verified` list. |

## Not verified

- Actual execution of `repositoryTestArtifacts` in a Dagger engine.
- Binding creation/verification, execution admission or invocation.
- Backend health/availability for any entry.
- engineering-ci consuming the signatures (#52/#53), group discovery/ranking (#35).
- A second real contract source or per-entry distinct contracts (model limitation).

## Verification

- New tests: 14 passed; field-contract tests: 15 passed; full suite: 210 passed, 1 skipped.
- `ruff check src tests` and `ruff format --check src tests` clean.
- Recorded details: [verification/tr-disc-01d.json](../../verification/tr-disc-01d.json),
  [access resolution](../../access-resolution.md).

Environment note: the Windows sandbox rejects the `0o700` temporary directories pytest
creates, so the full suite ran unconfined; no test or production file was changed for
that. Work happened in the isolated worktree `.worktrees/dsh-34-tool-access-resolution`
because the shared checkout was in use by another task.
