# Native and workflow check tools — shared asset definitions (C group)

Delivery for [issue #18](https://github.com/dymzz/vesryn-tool-runtime/issues/18)
(TR-ASSET-CI-01C / 12-C, child of [#12](https://github.com/dymzz/vesryn-tool-runtime/issues/12)),
on top of the 12-A foundation merged as PR #21. This group exclusively owns
`src/vesryn_tool_runtime/shared_assets/native.json`,
`tests/test_shared_assets_native.py` and this document. Common files
(`__init__.py`, `shared_definitions.py`, `pyproject.toml`, the common test,
`docs/README.md`, `docs/changelog.md`) stay with 12-A/#12.

## Definitions

All four definitions load through the public 12-A interface
(`shared_definition_documents()` / `load_shared_definitions("native.json")`) and
assemble with `register_shared_definitions`. Digests are publisher GitHub
Release asset digests, read on 2026-10-24.

| asset_id | version | target / ABI | entrypoint (archive layout) | sha256 | capability relation |
| --- | --- | --- | --- | --- | --- |
| `osv-scanner` | 2.6.0 | linux x86_64, none (static Go) | `osv-scanner` (raw binary) | `ca69b3d3…5b108` | `dependency.vulnerability-scan` — **real**: the capability ECI #51 already selected and consumed; release and identity unchanged from the #8 verification (re-checked 2026-10-24, unchanged). |
| `actionlint` | 1.7.12 | linux x86_64, none (static Go) | `actionlint` (tar.gz: binary + docs + man) | `8aca8db9…a3d8` | `example.actionlint` — **pending**: ECI main runs the `actionlint_workflows` check, but no formal Runtime capability contract exists yet; ECI #58 owns the real entry. |
| `shellcheck` | 0.11.0 | linux x86_64, none (static Haskell) | `shellcheck` (tar.xz: `shellcheck-v0.11.0/shellcheck` + LICENSE/README) | `8c3be12b…7198` | `example.shellcheck` — **pending** ECI #58. |
| `zizmor` | 1.31.1 | linux x86_64, `gnu` (glibc target triple) | `zizmor` (tar.gz: flat binary) | `d185f726…8c99` | `example.zizmor` — **pending** ECI #58. |

Full source URLs and exact digests are pinned by
`tests/test_shared_assets_native.py`; the declarations live only in
`shared_assets/native.json`. `osv-scanner` keeps its existing asset ID and
`official-2026-10-23` revision; the three new IDs use bare canonical program
names per the 12-A naming rule. Only Linux x86_64 is declared: selecting any
other target is an explicit `unsupported_target`, not an untested promise.
Windows PSScriptAnalyzer stays outside this group.

## Assembly status and authorization

- `dependency.vulnerability-scan` is the only formal capability relation; it is
  backed by ECI #51's actual selection/File-delivery consumption. Registering
  the document into a catalog without that capability fails `unregistered_tool`.
- The three `example.*` associations are placeholders, not formal callable
  capabilities: no empty ToolSpec or `Adapter=None` masquerade exists, and
  shared registration grants no execution permission. When ECI #58 lands its
  real check entries, the relation update for these three assets goes through
  this group (one data-file change), not through consumer-side edits.
- Source declaration success is not installation success and not CI enablement:
  actual scanning remains ECI #58's Linux/Dagger domain.

## Actual preparation evidence (2026-10-24)

All three **new** tools were actually prepared, verified and delivered through
the existing `Aria2NativeBackend` (issue #8's backend, unchanged), using the
locally pinned aria2 1.37.0 executable
(sha256 `be2099c214f63a3cb4954b09a0becd6e2e34660b886d4c898d260febfe9d70c2`, the
same version CI pins) on a Windows host for the Linux x86_64 target — the
backend verifies source digest, archive safety, per-file payload hashes and the
ELF x86_64 machine header without executing the foreign binary:

| asset | selection_id | entrypoint found | offline reuse | notes |
| --- | --- | --- | --- | --- |
| actionlint 1.7.12 | `cafc8b09…a9295d` | `actionlint` | passed/reused | digest also matches the publisher's `actionlint_1.7.12_checksums.txt` |
| shellcheck 0.11.0 | `6b411f8e…e66d5` | `shellcheck-v0.11.0/shellcheck` | passed/reused | versioned archive directory layout confirmed |
| zizmor 1.31.1 | `0f1b9a2c…e3cb8` | `zizmor` | passed/reused | flat single-binary archive confirmed |

Full selection/receipt/file digests are recorded in the
[issue #18 delivery record](../tasks/vesryn-tool-runtime/P1-native-workflow-shared-assets.md).
The prepared binaries were **not executed** here (Linux target, Windows host);
execution and check semantics are ECI #58's. No project scan was run for this.

## Evidence reuse

- #8's backend behaviors (corruption/policy/offline-reuse semantics) are reused
  unchanged; no generic positive/negative cases are re-run. The only new checks
  are this group's data-level tests (`tests/test_shared_assets_native.py`, 8
  cases) covering the four declarations, the OSV single-authority reuse, the
  Linux-only/unassembled status of the new tools, public-interface assembly and
  the example manifest references.
- OSV keeps #8's verification record and ECI #51's consumption evidence; the
  digest was re-checked against the publisher API on 2026-10-24 (unchanged) and
  no vulnerability scan was re-run for this reorganization.

## Consumer sample

`examples/native-assets.json` now references all four assets from
`native.json` (`{"asset_id": …, "shared_document": "native.json"}`) — osv-scanner
no longer maintains a second version authority. `examples/native_asset_delivery.py`
resolves those references and registers each asset under an explicitly example
capability (`<asset_id>.example`):

```text
python examples/native_asset_delivery.py --asset zizmor --version 1.31.1 \
  --os linux --arch x86_64 --abi gnu --root <asset-root> \
  --aria2 <aria2c> --aria2-version 1.37.0 --aria2-sha256 <digest> \
  --policy-revision <revision> --allow-network
```

The printed receipt/delivery documents are the same records ECI #51 consumed for
OSV (selection + `NativeAssetDelivery` File/Directory inputs). ECI #58/#52
choose Required/Optional, rules and exit-code gates; this group only delivers
the assets and the invocation conditions above.
