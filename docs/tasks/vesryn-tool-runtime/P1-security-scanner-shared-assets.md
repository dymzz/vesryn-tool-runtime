# TR-ASSET-CI-01E — issue #20 delivery record

Source: [issue #20](https://github.com/dymzz/vesryn-tool-runtime/issues/20), stage E of
[issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12). The issue's local
task-book path does not exist in this checkout; this record is created from the fetched
issue #20 body (same handling as the #6/#16/#18 records).

Baseline: main `193ca14` — the merged 12-A foundation (PR #21) plus D's #19 OCI
declarations. No release is performed; the package version stays 0.2.0.

Handoff identity: [PR #25](https://github.com/dymzz/vesryn-tool-runtime/pull/25)
(branch `codex/issue-20-security-scanner-shared-assets`, commit `cbe8510` plus
this record update); submitted for review without merging.

## Handoff

- **Trivy definition** (`src/vesryn_tool_runtime/shared_assets/security.json`,
  this group's exclusive data file): trivy 0.76.1, Linux x86_64, native/aria2,
  publisher digest `c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0`
  (GitHub Release asset digest read 2026-10-24, cross-checked against the
  publisher's `trivy_0.76.1_checksums.txt`), entrypoint `trivy`. Full details,
  the single-path distribution rationale (matching ECI #59's existing Dagger
  module consumption and the osv-scanner/#51 prepare→File-delivery precedent)
  and boundaries are in [security scanner shared assets](../../assets/security.md).
- **Capability relation**: `example.trivy` is an explicit placeholder — no
  formal Runtime capability contract exists for Trivy scanning yet (ECI #59 owns
  the scan/SBOM check entries). Assembly without the capability fails
  `unregistered_tool`; shared registration authorizes nothing. When ECI #59
  lands, the relation update goes through this group in one data-file change.
- **Gitleaks**: **deferred, not delivered** — ECI #60 is Optional/P2 and no
  Profile has selected Git-history checking; the absence is asserted by this
  group's tests and is not counted as a passed item. On selection, the
  same-grade definition is delivered through this group.
- **ECI consumption**: same pattern as #51 — explicit selection plus
  `NativeAssetDelivery` File/Directory inputs into ECI #59's Dagger module;
  scan databases/rules/parameters and Required/Optional choices stay with ECI.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| Trivy has a verifiable shared definition, target platform, source/artifact identity and an existing-backend consumption path; delivery status accurate | Done: `security.json` loads via the 12-A public interface; Linux x86_64 native/aria2 with the verified publisher digest; consumed like #51's osv-scanner (prepare → File/Directory delivery). Status: definition delivered and actually prepared; capability unassembled; not executed; ECI #59's first scan remains its own integration. |
| Reuse #8/C/D generic preparation/OCI evidence where available; only minimal verification for this asset's new archive/entrypoint/platform facts | Done: #8's backend evidence reused unchanged; this group adds only its data-level tests plus one actual preparation of this artifact (below). C/D completion was not a prerequisite; D's merged #19 files are untouched. |
| Gitleaks inclusion decision and basis explicit; same-grade definition if selected, otherwise marked not delivered | Done: deferred with the ECI #60 Optional/P2 basis recorded; no gitleaks declaration exists in any bundled document (test-asserted); not written up as passed. |
| Accurate commit/artifacts, version/asset identity, preparation/consumption samples and unverified conditions for ECI #59/#60, without touching their tree | This record, the group doc and the sample below; no ECI/Vesryn changes. |

### Preparation evidence (2026-10-24, local aria2 backend)

| fact | value |
| --- | --- |
| asset / version | trivy / 0.76.1 (release v0.76.1, published 2026-10-21) |
| source sha256 | `c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0` (also matches the publisher's checksums.txt) |
| selection_id | `6041b791987a26180c5c36dbcb9d66c8635d81b7e7b6f9e9eb7830f0a86066f9` |
| artifact_id | `495fcccb8ba3244713e3bc224aded828324d6dded2a09e402a715324fa358b2d` |
| entrypoint / payload | `trivy` / 8 files (binary, LICENSE, README, 5 contrib templates) |
| outcome | `passed/0`, executed/complete/current; offline re-preparation `passed` with `reused=True`; `delivery()` revalidated read-only |

Host: Windows x86_64 preparing the Linux x86_64 target with aria2 1.37.0
(executable sha256 `be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2`,
the same version CI pins). The binary was not executed; no vulnerability
database downloaded; no scan, SBOM conversion or secret access performed. The
raw evidence document is kept under `.test-tools/issue-20/` (not packaged).

## Verification

Verified on 2026-10-24 with CPython 3.14.8 (this checkout's locked environment):

| Evidence | Result |
| --- | --- |
| New group tests (`tests/test_shared_assets_security.py`) | 3 passed. |
| Full suite | 162 passed, 1 skipped (main baseline 159 + 3 group tests) — two consecutive stable runs, no regression. |
| Lint / format | `ruff check src tests examples` clean; `ruff format --check .` clean for the whole repository. |
| Packaging | `security.json` ships inside the wheel via the existing module-directory rule; no packaging config change. |

Local-environment observation (not this delivery's regression): the pre-existing
#8 concurrency case `tests/test_native_assets.py::test_two_concurrent_preparations_publish_once`
fails intermittently on this Windows host only, together with a pytest-cache
`WinError 183` warning. It flakes identically on the unchanged main baseline
(158 passed/1 failed on one run, 159 passed on others) and is green in every CI
run, including this PR's; it is left untouched as another group's file.

Boundaries kept: only this group's files were created
(`shared_assets/security.json`, `tests/test_shared_assets_security.py`,
`docs/assets/security.md`, this record). No edits to common exports, other
groups' definitions (including D's `oci.json`/`oci.md`), the native example, or
any ECI/Vesryn tree; no Syft, no second delivery path, no new downloader,
runner, cache manager or release.
