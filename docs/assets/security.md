# Security scanner shared assets (E group)

Delivery for [issue #20](https://github.com/dymzz/vesryn-tool-runtime/issues/20)
(TR-ASSET-CI-01E / 12-E, child of [#12](https://github.com/dymzz/vesryn-tool-runtime/issues/12)),
on top of the 12-A foundation (PR #21) with main at `193ca14` (which already
carries D's #19 OCI declarations). This group exclusively owns
`src/vesryn_tool_runtime/shared_assets/security.json`,
`tests/test_shared_assets_security.py` and this document.

## Trivy — delivered definition

Loads through the public 12-A interface
(`shared_definition_documents()` / `load_shared_definitions("security.json")`),
assembles with `register_shared_definitions`.

| field | value |
| --- | --- |
| asset_id | `trivy` |
| version | 0.76.1 (publisher release v0.76.1, 2026-10-21) |
| target / ABI | linux x86_64, none (static Go binary) |
| source | `https://github.com/aquasecurity/trivy/releases/download/v0.76.1/trivy_0.76.1_Linux-64bit.tar.gz` |
| sha256 | `c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0` |
| entrypoint | `trivy` (tar.gz: binary + LICENSE + README + 5 `contrib/` templates, 8 files) |
| capability relation | `example.trivy` — **pending**: no formal Runtime capability contract exists yet; ECI #59 owns the scan/SBOM check entries. |

The digest is the publisher GitHub Release asset digest read on 2026-10-24 and
cross-checked against the publisher's `trivy_0.76.1_checksums.txt` (the release
also ships sigstore bundles; they are not consumed here).

**Distribution decision (single path):** native/aria2. ECI #59 executes in the
existing Dagger module using Runtime-verified assets, which is exactly the
consumption pattern ECI #51 already proved with osv-scanner — aria2 preparation
plus `NativeAssetDelivery` File/Directory inputs. The Runtime's OCI support is
declaration-only (no preparation backend), so no second delivery/execution path
is added for uniformity. If ECI #59 later needs an OCI form of Trivy, that is a
coordinated addition through this group, not a silent second declaration.

## Actual preparation evidence (2026-10-24)

Trivy was actually prepared, verified and delivered through the unchanged
`Aria2NativeBackend` (issue #8's backend; local aria2 1.37.0, executable sha256
`be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2`) on a
Windows host for the Linux x86_64 target: download, source-digest verify, safe
extraction, per-file payload hashes, ELF x86_64 machine-header check, offline
re-preparation (`reused=True`) and read-only `delivery()` revalidation.

| fact | value |
| --- | --- |
| selection_id | `6041b791987a26180c5c36dbcb9d66c8635d81b7e7b6f9e9eb7830f0a86066f9` |
| artifact_id | `495fcccb8ba3244713e3bc224aded828324d6dded2a09e402a715324fa358b2d` |
| entrypoint found | `trivy` |
| payload | 8 files (binary, LICENSE, README, 5 contrib templates) |
| outcome | `passed/0`, executed/complete/current; offline reuse passed |

The binary was **not executed** (Linux target on a Windows host) and no
vulnerability database was downloaded: database/rule identities and scan
parameters are ECI #59's consumption conditions, and an executable digest is
never treated as a whole security-result identity. ECI #59's first actual scan
is its own check integration, not re-run here. #8's generic backend evidence
(corruption/policy/offline semantics) is reused unchanged; this group's tests
cover only this asset's new archive/entrypoint/platform facts.

## Gitleaks — deferred, not delivered

Gitleaks is **not** delivered: it is conditional on a consumer/Profile actually
selecting Git-history checking, and no such selection exists — ECI #60 is an
Optional, P2-phase task whose task book explicitly keeps it non-blocking while
marked not integrated/not verified. Nothing in this group's data declares
gitleaks, and this absence is asserted by
`tests/test_shared_assets_security.py`. When a Profile selects it, the same-grade
definition (verified source/version/platform/digest/entrypoint, same single-path
distribution decision) is delivered through this group's file; the deferral does
not block parent-task closure and is not counted as a passed item.

## Boundaries

Trivy stays owned by this group regardless of distribution form; D's
Semgrep/Lychee OCI files and every other group's files are untouched. Syft is
out of scope. No scanning, SBOM conversion, Git-history checking,
Required/Optional policy, downloader, runner or cache manager is introduced;
no secrets are read and no vulnerability database is fetched by registration or
preparation.
