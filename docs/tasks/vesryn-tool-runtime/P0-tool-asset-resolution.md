# TR-ASSET-01A — issue #6 delivery record

Source: [issue #6](https://github.com/dymzz/vesryn-tool-runtime/issues/6), child of
[issue #5](https://github.com/dymzz/vesryn-tool-runtime/issues/5). The referenced
task file was absent from this checkout; this record is created from the fetched
issue #6 body, not an inferred copy of an external task book.

Baseline verified locally: source `e016a50cbe242fac2148fb9ca974a7e3ea393006`, version
0.1.0. The issue's reported Vesryn source pin `b3079be…` is a separate identity;
no consumer directory is read or changed by this task. Existing user changes to
AGENTS.md, `.codex/` and `unregistered/` remain outside this implementation.

## Handoff

The supported structures and exact signatures are in
[CLI asset contracts](../../tool-assets.md). Authoritative release definitions
attach to existing Catalog capabilities. They do not alter ToolSpec semantic hashes,
Binding Schema 1, `provider_for`, permission admission, or the execution backend.
Public examples are `examples/asset_selection.py` and its real source/hash JSON.

| Consumer | Required behavior |
| --- | --- |
| B: uv | Consume AssetSelection; install/verify using uv's native environment model; provide actual ToolResult facts, source verification, environment identity/locator and entry-file hashes via AssetReceipt; explicitly record into AssetIndex. Do not copy uv private metadata. |
| C: aria2 | Consume the same selection/receipt/index; verify the downloaded artifact; publish extracted native files to native_asset_directory and report actual source/entry checksums. Do not report installer success from file/JSON delivery alone. |
| ECI / Harness | Supply target, consumer requirements and current policy revision; retain Selected per run; inspect available/local/backend outcomes distinctly; invoke only after existing Binding/Scope admission. No tool contract version inferred from a program version. |

## Directed acceptance

`tests/test_assets.py` exercises:

- Deterministic inputs and revisions, advancing publisher defaults, continued reading
  of old snapshots and sharing content across policy revisions.
- Independent consumer versions, OS/architecture/ABI/Python constraints, disablement,
  unregistered capability/asset, missing files and unknown backend facts.
- Common native/Python receipts, required source/environment/entry facts, original
  failure preservation, exclusion of raw backend outputs and actual file tampering.
- Eight concurrent threads and six separate processes merging independent records
  into one index; lock timeout and refusal to overwrite a corrupt index.
- Unchanged existing Binding digest/admission after local installation, Provider
  identity under composition/scoped wrapping, and discovery with subprocess/network/
  write operations forbidden.

The affected existing runtime/boundary suites are rerun because Catalog composition
and public imports are extended. Python package metadata promotes existing locked
`filelock==3.20.3` and `packaging==26.3` dependencies to direct runtime requirements;
no project dependency resolver, installer or downloader is introduced.

Verified on 2026-10-23 with CPython 3.14.3:

| Directed evidence | Result |
| --- | --- |
| New asset/index cases | 34 passed, including 8 concurrent threads and 6 independent processes. |
| Existing affected runtime/boundary cases | 40 passed. |
| Installed candidate wheel, isolated imports | All 74 directed cases passed; neither consumer package installed. |
| Offline real-definition example | ripgrep 15.2.0 and pytest 9.0.3 selected; Installed `not_configured`; no backend run. |
| Lint / format / root lock consistency | Passed for affected sources, tests and example. |
| Candidate wheel source and contents | All package Python bytes match this working tree; work/cache/personal directories absent. |

Candidate SHA-256 and public signatures are recorded in
[machine-readable evidence](../../verification/tr-asset-01a.json). This wheel is
stored under `.test-tools/issue-6/dist/`; it does not replace the published 0.1.0
artifact. No formal release, consumer adaptation, issue comment, or adjacent-repository
change is implied by this local delivery. Source hashes in the example establish
declared identity; actual uv/aria2 installation is not claimed as verified here.
