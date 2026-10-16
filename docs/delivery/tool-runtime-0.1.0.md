# 0.1.0 extraction assessment

This records the local extraction baseline before publication. The authorized
release continues through current-head PR checks, merge to main and an immutable
`v0.1.0` tag. The final preparation/publication assessment, exact source revision,
CI URLs and artifact digests are recorded in `release-provenance.json` attached to
[the release](https://github.com/dymzz/vesryn-tool-runtime/releases/tag/v0.1.0).
That verified publication receipt supersedes the pending baseline below; a link
alone does not establish that publication succeeded.

This applies the existing [Release Readiness C1–C8 criteria](release-readiness.md),
without introducing another acceptance standard. Verified on 2026-10-16 with
Windows CPython 3.14.3, uv/uv_build 0.12.23, Dagger CLI/Engine 1.0.0-beta.16 and
Docker 29.4.0. Logging uses the released vesryn-log 0.1.0 public API from exact
commit `030c5a8edf820588e29f53803b6baaf53b1f6e57`.

The local extraction and consumer integration are verified. Formal release
readiness is **BLOCKED** by C6: accepted immutable component/consumer references
and source-to-artifact publication provenance remain unverified. No Release or
Tag was created during that baseline verification. Remote GitHub CI is not
claimed from these local results.

| Criterion | Status | Evidence / boundary |
| --- | --- | --- |
| C1 Independent Consumption | PASS | Wheel installed without either consumer; 39 independent public tests and direct example passed. No checkout paths in wheel dependencies. |
| C2 Public Contract | PASS | Documented API, authoritative types, original Binding Schema 1 fixture, safe event schema and separate execution/validation/recording facts verified. |
| C3 Documentation | PASS | Indexed quickstart, API, ownership, failure and integration docs; relative links verified. Source distribution includes docs, example and independent tests. |
| C4 Reproducible Examples | PASS | Shipped example produced value 4 and passed/0 from an isolated installed wheel, without Workflow construction. |
| C5 Failure Semantics | PASS | Failure, interruption, unknown, malformed evidence, scope and sink-loss tests passed. Real Dagger failure/1 remained failure/1 through call, run and resume. |
| C6 Versioned Delivery | NOT VERIFIED | 0.1.0 wheel/version and artifact digest exist; accepted source revisions, production-safe consumer pins and formal provenance remain pending. |
| C7 Consumer Verification | PASS | Vesryn 470 passed; engineering-ci 1232 passed, 8 skipped, 103 subtests passed. Actual shared/domain Dagger calls, resume reuse and batch evidence passed. Main Dagger CI: 3/3 passed. |
| C8 Compatibility & Evolution | PASS | Old imports share exact authoritative types; original Schema 1 reads; workflow/recovery tests pass; 12 descriptor hashes unchanged. Development and source-bound Dagger migration limits are explicit. |

## Actual verification

| Scope | Result |
| --- | --- |
| Main checkout pytest | 40 passed, including the retained scaffold test. |
| Independent installed wheel | 39 public tests passed; `vesryn` and `engineering_ci` absent. The public example passed/0. |
| Main lint and format | Passed locally and in actual delegated Dagger CI. |
| Main Dagger check | format-check, lint, tests: all 3 passed. Existing report function still exports one pytest execution for the Workflow gate. |
| Vesryn complete pytest | 470 passed. Includes process-death intent/recovery, old imports, previous-result verification, shared CLI/history and Dagger transport regressions. |
| engineering-ci complete pytest | 1232 passed, 8 skipped, 103 subtests passed. Optional skips are not counted as verified integrations. |
| Real shared Dagger tool | `verify.stateful`: passed/0, executed; Hypothesis 6.169.1, 3 cases and 15 transitions; observation_errors 0. Direct Schema 1 Binding invocation also passed with complete observation, without constructing a Workflow. |
| Real engineering Dagger | Installed Provider loaded; Schema 1 Binding call passed/0; resume retained identity and reused verified evidence; existing CLI run passed/0. |
| Real engineering batch | ruff-lint + ruff-format passed/0 through original ChecksAdapter; both results reference one original check report. |
| Real failure preservation | First actual lint run reported failed/1; call, resume and CLI run retained failed/1 and evidence. Syntax/import integration defects were fixed; subsequent real executions passed. |
| Contract identity | [Before/after descriptor hashes](../verification/contract-hashes.json): 12 identical hashes. Local source-bound Dagger identities continue to invalidate changed-source bindings. |
| Independent artifact | `vesryn_tool_runtime-0.1.0-py3-none-any.whl`, SHA-256 `93ce72f1c9119ad9802b6c94bc0cfa4ca769d76b21c644d7c48419bb4d3fff5e`. |

JUnit XML and full local receipts remain under `.test-tools/` in the main
checkout; consumer checkpoints/evidence remain in each consumer's `.test-tools/`
directory. [Verification summary](../verification/results.json) records counts
and identities without parameters, raw tool output or credentials.

The main CI consumes engineering-ci fixed commit
`0f74b2f776796b9db83f7a61c0849e504afdbea0`. Private Git access uses its existing
Secret interface, with the same pin in Workflow and Dagger metadata. Existing OCI
pins are retained; obsolete floating v0.6.5 lock entries were removed because the
new module address is an explicit immutable SHA.

## Publication boundary

No component/consumer commit, push, Release or Tag was created by this task.
Pre-existing unrelated uncommitted changes are preserved. C6 remains NOT VERIFIED
until accepted immutable source references and delivery provenance exist. Local
source overrides are development inputs. The production dependency scanner still
rejects the consumers' local paths; its policy was not weakened. Remote GitHub
jobs are configured but were not dispatched in this session.
