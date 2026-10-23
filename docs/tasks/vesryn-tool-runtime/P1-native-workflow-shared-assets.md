# TR-ASSET-CI-01C — issue #18 delivery record

Source: [issue #18](https://github.com/dymzz/vesryn-tool-runtime/issues/18), stage C of
[issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12). The issue's local
task-book path does not exist in this checkout; this record is created from the fetched
issue #18 body (same handling as the #6/#16 records).

Baseline: main `36672388624fd3008117d3b79c9819790d21a602` — the merged 12-A
foundation (PR #21), which provides the public read/explicit-assembly interface
and this group's exclusive paths. No release is performed; the package version
stays 0.2.0.

Handoff identity: [PR #22](https://github.com/dymzz/vesryn-tool-runtime/pull/22)
(branch `codex/issue-18-native-workflow-shared-assets`, commit `2fecfc3` plus this
record update), CI run 39994511975 green on the delivered head.

## Handoff

- **Definitions** (`src/vesryn_tool_runtime/shared_assets/native.json`, this
  group's exclusive data file): osv-scanner 2.6.0, actionlint 1.7.12,
  shellcheck 0.11.0, zizmor 1.31.1 — Linux x86_64 only, real publisher
  sources/digests, accurate entrypoints. Details and the ownership/authorization
  boundaries are in [native and workflow shared assets](../../assets/native-workflow.md).
- **Capability relations**: `dependency.vulnerability-scan` for osv-scanner is
  the real relation ECI #51 already selected and consumed. actionlint,
  shellcheck and zizmor carry explicit `example.*` associations because **no
  formal Runtime capability contract exists for them yet** — ECI main's
  `actionlint_workflows` check predates the asset consumption work, and
  ShellCheck/zizmor integration is ECI #58's to deliver. This is the "available
  asset, unassembled capability" state the issue requires; no empty ToolSpec or
  `Adapter=None` masquerade, and shared registration authorizes nothing.
  **Open coordination item**: when ECI #58 lands its real check entries, the
  `tools` values for these three assets are updated through this group in one
  data-file change.
- **Samples**: `examples/native-assets.json` references all four assets from
  `native.json` (osv-scanner no longer maintains a second version authority);
  `examples/native_asset_delivery.py` resolves the references and now accepts
  `--asset {hyperfine,osv-scanner,actionlint,shellcheck,zizmor}`. The hyperfine
  #8 example definitions and `asset_acceptance.py` are untouched.
- **ECI consumption**: same pattern as #51 — explicit selection plus
  `NativeAssetDelivery` File/Directory inputs; see the sample command in the
  group doc. ECI #58/#52 own Required/Optional, rules and exit-code gates.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| Four shared definitions with real sources/hashes, targets/entrypoints and accurate capability relations, obtainable via A's explicit interface; OSV not maintained twice | Done: `native.json` loads via `shared_definition_documents`/`load_shared_definitions`; digests pinned in `tests/test_shared_assets_native.py`; osv-scanner keeps its verified 2.6.0 declaration (re-checked unchanged on 2026-10-24) and the example references it instead of redeclaring. |
| At least one new native tool actually prepared, verified and delivered via the existing backend, proving archive/entrypoint usability; no full project scan | Done for **all three** new tools on 2026-10-24 with `Aria2NativeBackend` (aria2 1.37.0, executable sha256 `be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2`) on a Windows host for the Linux x86_64 target: download, source-digest verify, safe extraction, per-file payload hashes, ELF x86_64 header check, offline reuse, read-only revalidation via `delivery()`. No binary executed; no project scan run. |
| Reuse #8 backend/corruption/policy evidence and #51 OSV evidence; only new-format-affected checks | Done: backend code unchanged; no generic cases re-run. New checks are only this group's data-level tests. |
| Items not actually prepared/executed honestly marked | Done: all four assets declared; the three new tools marked "not executed here" (Linux target on a Windows host; execution is ECI #58's domain); capability relations marked pending where no formal contract exists. |
| Accurate commit/artifacts, revisions, target/delivery samples and valid evidence references for ECI | This record plus the group doc; handoff identity is this branch's PR. |

### Preparation evidence (2026-10-24, local aria2 backend)

| asset | version | source sha256 | selection_id | artifact_id | entrypoint | payload files |
| --- | --- | --- | --- | --- | --- | --- |
| actionlint | 1.7.12 | `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8` | `cafc8b0982e600e7d6b7c6217c929117ff4f8bcdcddb88db2840d4a915a9295d` | `5e23b116c2efca94e79d33e2744eb27835df917a4ad4511520f54a0da4c8abd1` | `actionlint` | 11 files (binary, docs, man) |
| shellcheck | 0.11.0 | `8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198` | `6b411f8ed9f63dfb96d9149b9d6c5daedd70d96200dfba8b966f927b9f3e66d5` | `ad04f13ad3df8c1374a6ab597859aa1a9666727e77af93cd97535ea611aa79e0` | `shellcheck-v0.11.0/shellcheck` | 3 files (binary, LICENSE, README) |
| zizmor | 1.31.1 | `d185f726bdaf92df78273217dfdd24ebcd6b0ef48cf3ce776ff5762b6e138c99` | `0f1b9a2c91797bdc29a01a8b6839805533a1e9078b0374048a46f2131a3e3cb8` | `e1ac2473517d500e54536e2f3e17967c167d912292f29b3e69ace3268c5ee886` | `zizmor` | 1 file (binary) |

All three receipts: `passed/0`, `executed/complete/current`, offline reuse
re-prepared `passed` with `reused=True`. actionlint's digest additionally
matches the publisher's `actionlint_1.7.12_checksums.txt`. Publisher digests
were read from the GitHub Release asset API on 2026-10-24; osv-scanner's was
re-checked unchanged (`ca69b3d3cd08f889a49dc0a383122f71cc528b83803671df5fd874d97485b108`).
The raw evidence document is kept under `.test-tools/issue-18/` (not part of
the package).

## Verification

Verified on 2026-10-24 with CPython 3.14.8 (this checkout's locked environment):

| Evidence | Result |
| --- | --- |
| New group tests (`tests/test_shared_assets_native.py`) | 8 passed. |
| Full suite on this delivery's scope | 160 passed, 1 skipped (baseline 152 + 8 group tests) — no regression. |
| Lint / format | `ruff check src tests examples` clean; `ruff format --check` clean for every file in this delivery (Python and markdown samples). |
| Wheel/sdist packaging | `native.json` ships inside the wheel via the existing module-directory rule; no packaging config change (12-A already widened sdist includes). |

Note: this checkout's working tree also contains group B's (issue #17) untracked
in-progress files (`shared_assets/python.json`, `tests/test_shared_assets_python.py`,
`docs/assets/python-cli.md`, `docs/tasks/…/P1-python-cli-shared-assets.md`,
`docs/verification/tr-asset-ci-01b.json`). They are **not** part of this
delivery and are excluded from this branch; the full-suite count above is this
delivery's scope only. Observation for group B: `docs/assets/python-cli.md`
currently fails `ruff format --check` (markdown Python block), which would fail
CI on their branch.

Boundaries kept: only this group's files were created/changed
(`shared_assets/native.json`, `tests/test_shared_assets_native.py`,
`docs/assets/native-workflow.md`, this record, and the two example files the
issue explicitly assigned for the osv-scanner single-authority change). No
edits to common exports, Python/OCI/Trivy definitions, or other agents' files;
no ECI/Vesryn changes; no new downloader, runner or full-platform matrix.
