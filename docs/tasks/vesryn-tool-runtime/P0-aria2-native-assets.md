# TR-ASSET-01C — issue #8 delivery assessment

Source: [issue #8](https://github.com/dymzz/vesryn-tool-runtime/issues/8), child of
[issue #5](https://github.com/dymzz/vesryn-tool-runtime/issues/5), consuming the
[issue #6 contracts](P0-tool-asset-resolution.md). The task-book path was absent
at the start; this record is based on the fetched issue body and its empty comments.

## Baseline and scope

Implementation starts from `f60eadd`, the merge of #6, rather than treating the
issue's earlier `e016a50…` baseline or reported consumer pin `b3079be…` as the
same artifact. Package metadata remains 0.1.0; the original released wheel does
not contain this backend. The concurrent #7 uv task is on a separate checkout;
this delivery does not modify its backend, consumers, their locks or release flows.

The public handoff is [Native assets](../../native-assets.md), with exact signatures,
formats/targets, current-policy checks, downloader provenance, stable failure reasons,
offline verification requirements and existing File/Directory consumption.
Reviewed sources/hashes are in [native-assets.json](../../../examples/native-assets.json);
the runnable consumer example is
[native_asset_delivery.py](../../../examples/native_asset_delivery.py).

## Acceptance evidence

Verified 2026-10-23 on Windows with CPython 3.14.3 and independently prepared
aria2 1.37.0. Directed machine-readable evidence is
[tr-asset-01c.json](../../verification/tr-asset-01c.json).

| Criterion | Evidence / result |
| --- | --- |
| Real first download and validated second hit | aria2 downloaded Hyperfine 2.0.0 and 1.20.0 Linux x86_64/gnu, and OSV Scanner 2.6.0 Linux x86_64 from their exact official URLs. Runtime matched every source SHA and ELF target. A second preparation of each succeeded offline with subprocesses forbidden. |
| Two actual versions coexist and select accurately | Both Hyperfine archives have distinct declared versions, source digests, artifact IDs, paths and verified entry hashes. Neither preparation replaced the other. |
| Offline miss, corruption, disablement | Directed tests distinguish offline absence, changed source, changed payload, extra injected files, forged index manifests, current disablement and version-policy rejection. No corrupted payload is overwritten to hide the failed attempt. |
| Interrupted download / archive escape | Interrupted staging is cleaned without publishing; TAR and ZIP traversal, absolute/drive/backslash/reserved aliases, TAR links/special files and duplicate names fail without a success entry. Original downloader exit 17 is retained. |
| Existing Dagger File/Directory handoff | Example imports only verified payload files and returns the exact entry File. Existing SDK signatures were checked locally. All three real Linux deliveries have verified ELF headers and exact manifest paths; no Linux binary was executed on Windows. |
| Public API and trust | Aria2Source pins an independently prepared executable/version; preparation and read-only delivery use the shared AssetReceipt/AssetIndex. Reuse derives expected files from the hashed source again; no state.json assertion establishes trust. |
| Existing contract and permission behavior | Existing asset/Binding/runtime/boundary cases pass. Preparing a CLI does not change ToolSpec hashes or admit a call. Ordinary Catalog discovery does not start acquisition or create the root. |

The independently installed candidate wheel passed **121 directed tests**: 47 new
native cases and 74 affected existing cases. One additional symlink-boundary case
was skipped because this Windows host does not permit creating a file symlink;
the test remains enabled on hosts that support it. Two concurrent preparations of
the same artifact publish once and make one download. The existing A tests also
exercise cross-process index merging.

Ruff lint/format passed. Candidate Python package bytes match source, and no consumer
packages, private work directories or virtual environments are in the wheel.
The offline public consumer sample succeeds using the independently installed wheel.
No runtime dependency or lock resolution changes are needed; `uv.lock` is unchanged.

This assessment does **not** claim an actual Dagger Engine run or Linux business
scan/benchmark. Consumers own their existing Dagger graphs, runner compatibility,
business validation, supply-chain approval and invocation admission. These examples
require their own current policy; their declarations are not silently registered
into consumer catalogs. No remote registry, cache service, general installer,
transport, tool executor or workflow scheduler is added.

## Upstream observation

CPython 3.14.3 `zipfile.ZipInfo.filename` normalizes Windows separators and truncates
NUL; `orig_filename` retains the archive name. This affected construction and
inspection of malformed ZIP test fixtures. The backend validates the original
name before using stdlib extraction; the Windows traversal fixture restores raw
separator bytes in local and central ZIP headers after writing. This is a verified
stdlib normalization/compatibility pitfall, not an asserted upstream defect.
The directed cases guard this behavior; no third-party code is patched.

Only local candidate artifacts and this repository's source are produced. A formal
Release, issue mutation, consumer adaptation or publication is not authorized by
this assessment.
