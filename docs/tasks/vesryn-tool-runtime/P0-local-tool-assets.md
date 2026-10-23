# TR-ASSET-01 — joint acceptance and 0.2.0 release assessment

Source: [issue #5](https://github.com/dymzz/vesryn-tool-runtime/issues/5). This is
an acceptance record for the delivered A/B/C components, not another registry,
state machine or acquisition implementation.

## Source identities and public handoff

- A: #6, `ae1fbb2`, merged as `f60eadd`; [contracts](../../tool-assets.md),
  [evidence](../../verification/tr-asset-01a.json).
- B: #7, `f4035b9`, merged as `deed69f`; [uv API](../../uv-tool-assets.md),
  [historical evidence](../../verification/tr-asset-01b.json).
- C: #8, `6e8a8b3`; [native API](../../native-assets.md),
  [historical evidence](../../verification/tr-asset-01c.json).

The 0.2.0 candidate combines these actual sources. It does not update the separate
consumer pin `b3079be…` reported by the original issue. The original published
0.1.0 wheel is a different artifact. Versioned wheel/sdist hashes, accepted source
revision, current-head CI identifiers and publication facts belong in each Release's
`release-provenance.json` and `SHA256SUMS`.

Current public signatures are in the linked APIs. The original #7 signatures lacked
a current-policy input. Joint acceptance fixes that before first publication of
this feature: `lock`, `prepare`, `installed` and `command` now require `policy=`.
It also fixes repeated preparation deleting/rebuilding an already published uv
environment. Verified environments and their full hashed locks are reused; damaged
published environments fail visibly rather than being replaced during another run.
Both refinements are covered by directed real-uv regressions.
Windows version probes also exposed WinError 206 for the long, versioned native
archive entry path. The consumer Adapter supplies an explicit `executable=` to
Windows process creation; stored identity and Dagger-relative paths stay unchanged.
This is a Windows path compatibility limitation, not an upstream
Hyperfine defect. The actual Hyperfine version probes verify the corrected path.

## Joint verification

`examples/asset_acceptance.py` is a standalone consumer of the installed public
package. Supply an explicit test root, prepared aria2 path/version/SHA, and explicit
network permission. The example prepares and reuses two Hyperfine versions and two
Vulture versions through one shared index. Its own consumer ToolAdapter receives
one admitted batch of version probes; logging or checksum validation does not run
those probes again. Neither backend becomes a generic tool executor.

With `--with-dagger` on Linux, the example additionally imports one native payload
as a `dagger.File`, another as a `dagger.Directory`, and checks the declared native
versions. A full hashed Vulture lock prepares a separate Linux tool environment
using uv; no host venv is copied. The declared verification toolchain is Dagger
CLI `v1.0.0-beta.16`, SDK `dagger-io==1.0.0b16`, CPython 3.14 and uv 0.12.23.
The base image is the existing `ghcr.io/astral-sh/uv:python3.14-trixie-slim` toolchain.

The CI `package` job installs the built wheel without either consumer package,
runs this example through `dagger run`, and retains the resulting
`vesryn-tool-runtime-asset-acceptance` artifact. The actual `acceptance.json`
contains selections, common receipts, per-environment identities, version results,
the full Linux hash lock, aria2 executable hash and File/Directory outcomes.
The Linux downloader is independently prepared from Ubuntu Noble's signed package
repository as `aria2=1.37.0+debian-1build3`; `aria2-package.txt` retains package-source
and digest facts. Windows aria2 and official native artifact records retain their
separate, already verified provenance in the C documentation.

Reuse valid earlier evidence for default advancement/old snapshots, source checks,
restore/tampering, unsafe archives, interrupted downloads, platform distinctions,
concurrent index updates, unchanged Binding hashes and scope admission. Rerun the
affected public suites for the combined candidate. A successful unit run alone
does not establish the Dagger or published-artifact paths.

The [local combined evidence](../../verification/tr-asset-01.json) records the
Windows installed-wheel run and real four-version batch separately from the
required Linux/Dagger CI results. Its candidate hash is not a published artifact.

## C1–C8 release gates

| Criterion | Required observable evidence |
| --- | --- |
| C1 Independent consumption | Accepted-main CI wheel installed into an isolated environment; neither Vesryn nor engineering-ci installed; normal dependency metadata and fixed Log source documented. |
| C2 Public contract | A/B/C documented signatures and side effects match the installed package; common receipt/index and current policy are verified. |
| C3 Documentation | Index, quickstart, backend handoffs, official records, example and this assessment are included in the candidate source distribution. |
| C4 Reproducible examples | Installed direct-tool example plus real A/B/C acceptance; Dagger File/Directory and Linux lock results are actual successful CI outputs. |
| C5 Failure semantics | Directed missing/disabled/corrupt/interrupted/failure tests; original downloader codes and independent observation failures remain authoritative. |
| C6 Versioned delivery | Runtime metadata/API wheel path agree on 0.2.0; exact accepted-main CI wheel/sdist match source and hashes; immutable tag points to that source. |
| C7 Consumer verification | Independent installed example and real Dagger transport, separate from provider unit tests. Downstream ECI/Vesryn adaptation remains their tasks. |
| C8 Compatibility | Existing ToolSpec/Provider/Scope/Binding/Invocation tests pass; no original 0.1 callable changes; current-policy arguments refine only the unreleased uv prototype. |

The preparation decision is **READY only after every applicable row is PASS**
for the accepted candidate. The Release provenance records actual statuses and
links; a missing or failed Dagger outcome is a release blocker. Publication is
separate: verify tag target, non-draft Release, asset names/hashes and downloaded
bytes before claiming completion. The user authorized publication after acceptance
on 2026-10-23; this document does not independently authorize it.

Known limits: macOS, additional CPU targets, other checkers, downstream business
scans and Harness-Python compatibility are not established here. Semgrep remains
OCI. Native files cached on Windows do not prove Windows executability of Linux
payloads or installation on other runners. Consumers own current policy, explicit
execution Scope and approved roots; ordinary Catalog discovery stays read-only.

Before publication, preserve accepted `main` with an immutable backup tag and a
verified local Git bundle. Keep backups outside disposable validation directories.
