# TR-ASSET-CI-01B — issue #17 delivery record

Source: [issue #17](https://github.com/dymzz/vesryn-tool-runtime/issues/17), stage B of
[issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12). The issue's local
task-book path is this file; no task book existed in the checkout, so this record is
created from the fetched issue body (same handling as the #16 and #6 records).

Baseline: `main` at `3667238`, the merge of [PR #21](https://github.com/dymzz/vesryn-tool-runtime/pull/21)
(#16 / 12-A). Package version stays 0.2.0; no release, tag or publication is performed.
Existing changes from other groups working in the same checkout are outside this
implementation.

## Handoff

- Branch: `codex/issue-17-python-cli-shared-assets`, based on `3667238`; commit
  `803fce3`, [PR #23](https://github.com/dymzz/vesryn-tool-runtime/pull/23).
- Exclusive files added by this group:
  - `src/vesryn_tool_runtime/shared_assets/python.json` — the four definitions.
  - `tests/test_shared_assets_python.py` — offline group test.
  - `docs/assets/python-cli.md` — public group document.
  - `docs/verification/tr-asset-ci-01b.json` — recorded checks.
- No common file was edited: `__init__.py`, `shared_definitions.py`, `pyproject.toml`,
  `docs/README.md`, `docs/changelog.md`, the common compatibility test and the bundled
  examples data are unchanged. B–E group files stay exclusive.

## Decisions

- The frozen `catalog_revision` `eci-tools-2026-10-23` is preserved for all four
  definitions, so vulture, pyright and pylint keep the exact
  `definition_sha256` recorded by engineering-ci #51. deptry's correction necessarily
  publishes a different digest under that revision; the definition hash, not the
  revision string, is the content identity recorded by a selection.
- `abi` stays `null` for deptry: the #51 target is `linux`/`x86_64`/`abi: null`, and
  the manylinux_2_17 x86_64 (glibc) constraint is documented as a consumption
  condition instead of forcing every consumer to add an ABI label.
- Only Linux x86_64 is declared for deptry. The other upstream wheels (Windows,
  macOS, aarch64, musllinux) exist but have no evidence in this task and are not
  declared.

## Directed acceptance

| Issue criterion | Result | Evidence |
| --- | --- | --- |
| Four definitions load through A's public entry; metadata, source, platform and existing capability IDs agree | passed | Group test asserts bundled read, tools mapping, revision, URL, SHA-256, Requires-Python, entrypoint, platform and definition digests; three digests equal the #51 record byte-for-byte. |
| deptry platform correction and re-resolution verifiable; incompatible target not mis-selected; old selections stay readable | passed | deptry is `linux`/`x86_64`; Windows target raises `unsupported_target`; the #51 frozen selection loads unchanged by `AssetSelection.from_document`; the re-resolved Linux lock has the identical `requirements_sha256` `be985aac…7632`. |
| Minimal verification of the affected selection/lock handoff; reuse #7 and #51 evidence instead of rerunning scans | passed with reuse | Locks for all four were re-resolved with uv 0.12.23 and compared field by field with #51; vulture/pyright/pylint artifact and requirement identities match. #7's prepared vulture 2.16 wheel is the same URL/SHA-256 and is cited, not rerun; no scan was executed. |
| Verify affected items if artifacts, locks, interpreter or implementation change | passed | Wheel URLs/SHA-256 re-read from PyPI on 2026-10-24; uv version and target platform match the #51 locks. No change beyond the declared platform correction. |
| Deliver commit/artifact, definition and derived-document identity, verification references, real prepared/verified state and uncovered targets | passed | Commit `803fce3` on [PR #23](https://github.com/dymzz/vesryn-tool-runtime/pull/23); data, test, document and checks are delivered; the wheel build contains `shared_assets/python.json`; installation/execution stays `not_verified`. |

## Real prepared/verified state

- `prepared`: none in this task. The four tools were not installed or executed here.
  #7 prepared the identical vulture 2.16 wheel (same URL and SHA-256) on Windows and is
  cited as reusable evidence; #51 produced the four Linux lock documents.
- `verified`: definition reads, explicit assembly against registered capabilities,
  selection identities, the deptry target rejection, old-selection readability and the
  lock requirement comparison.
- `not_verified`: installation/execution on Linux x86_64 / Python 3.14; Pyright Node
  availability in a consumer container; deptry or the others on Windows, macOS, aarch64
  or musl; engineering-ci regenerating its deptry selection and lock.

## Consumer handoff (engineering-ci #52/#53)

- Read the four records from `python.json` with `load_shared_definitions` and associate
  them through `register_shared_definitions`; capability IDs and contract identities
  are unchanged.
- Regenerate `deptry.selection.json` and its lock from the corrected definition; the
  requirement text is unchanged, the selection and artifact identities are not.
  This repository does not edit the consumer worktree or replace its lock files.
- Keep the frozen #51 deptry selection readable; do not rewrite it in place.

## Verification

- Group test: `tests/test_shared_assets_python.py` — 4 passed, offline.
- Full suite: 156 passed, 1 skipped; `ruff check` and `ruff format --check` clean;
  `uv lock --check` clean.
- Wheel check: one local worktree build contains
  `vesryn_tool_runtime/shared_assets/python.json` (digest is recorded in the
  verification JSON with its concurrency caveat).
- Required CI on PR #23: `package` passed and `python / checks` passed (format-check, lint, tests); `dependency-security` skipped.
- Recorded details: [verification/tr-asset-ci-01b.json](../../verification/tr-asset-ci-01b.json),
  [group document](../../assets/python-cli.md).

Environment note: the Windows sandbox rejects the `0o700` temporary directories pytest
creates, so the full suite was run in an unconfined process; no test, fixture or
production file was changed for that.
