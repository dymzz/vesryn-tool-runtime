# CLI assets, selections and local facts

This is the public handoff for [issue #6](https://github.com/dymzz/vesryn-tool-runtime/issues/6),
TR-ASSET-01A. These APIs are working-tree additions after source baseline
`e016a50cbe242fac2148fb9ca974a7e3ea393006`, package version `0.1.0`.
They are not present in the original released wheel. The issue reports a consumer
pin of `b3079be2331a19b9168fa7c8f26607bafc059cec`; this task does not inspect or
update that consumer. Do not treat these source revisions as identical artifacts.

## Definitions and authority

`AssetDefinition(asset_id, catalog_revision, releases)` is an immutable CLI release
declaration associated with existing ToolSpecs by `Catalog.register_asset`.
One program can support several capabilities. Ordinary project libraries remain
project dependencies, managed by the project's own pyproject/uv.lock.

`AssetRelease` fields:

| Field | Meaning |
| --- | --- |
| `version` | Exact publisher version. `latest`, `stable`, `default`, `current` are rejected. Independent of `ToolSpec.contract_version`. |
| `distribution` | `python`, `native`, or an existing `oci` reference. |
| `backend` | `uv`, `aria2`, or `oci`, respectively. An acquisition identifier; never a capability Provider. |
| `source` | HTTPS/file artifact URL without embedded credentials, query or fragment; OCI source must end in its exact `@sha256:…` digest. A definition does not establish backend support or readiness. |
| `sha256` | Full lowercase SHA-256 of the distribution artifact. For OCI, its pinned digest. This is distinct from hashes of extracted entry files. |
| `entrypoint` | CLI entry name, without arguments or path traversal. |
| `os`, `arch`, `abi` | Declared target constraints. Native/OCI require explicit OS and architecture; Python universal artifacts may use `any`. An ABI constraint requires an exact target match. |
| `package`, `requires_python` | Required for Python distributions: package name and PEP 440 interpreter constraint. Target interpreter version must be supplied explicitly. |
| `lock_ref` | Optional publisher-owned immutable lock reference. Not copied uv metadata or a takeover of the consumer's project lock. |

The release declaration's **ordered tuple** is the default preference order.
The first compatible release satisfying consumer requirements and current policy
is chosen. The publisher changes the declaration/revision to advance that default;
an approval does not permanently freeze today's version. There is no implicit
network query, numeric-version sorting, host detection or installed-version lookup.
An explicit `version` matches literal publisher versions; `specifier` uses PEP 440.
Non-PEP-440 native versions can still be selected exactly or by published default.

`AssetPolicy(revision, enabled=True, specifier="")` records policy revision,
disablement and optional allowed-version constraints. Disablement is a policy
property. `AssetTarget(os, arch, abi=None, python=None)` is explicit; examples use
`windows`/`linux`, `x86_64`/`aarch64`, and `gnu`/`msvc`. Labels are matched exactly.

Release declarations are version authority. Selection documents, environment locks,
cache keys and reports are derived records. Artifact source/backend metadata does
not replace `Catalog.provider_for(tool_id)`, which keeps its original meaning.

## Public signatures

All types/helpers below are exported from `vesryn_tool_runtime`.

```python
Catalog.register_asset(definition: AssetDefinition, *, tools)
Catalog.asset_for(tool_id, *, scope=None) -> AssetDefinition
Catalog.select_asset(tool_id, *, target, policy, version=None,
                     specifier="", scope=None) -> AssetSelection
Catalog.asset_view(tool_id, *, target, policy, selection=None,
                   index=None, scope=None) -> dict
AssetSelection.document() -> dict
AssetSelection.from_document(value) -> AssetSelection
asset_root(path=None, *, environ=None, platform=None) -> Path
native_asset_directory(root, selection) -> Path
AssetIndex(root, *, timeout=10)
AssetIndex.record(receipt: AssetReceipt) -> dict
AssetIndex.installed(selection: AssetSelection) -> dict
```

Register the ToolSpec/adapter first. `register_asset` requires at least one existing
tool ID, supports one definition associated with many tools, and rejects conflicting
asset ownership atomically. Composition and scoped catalogs preserve associations
and original Provider identities; they do not build a second Registry.

The selection contains tool ID/Provider/contract hash, asset ID, publication revision
and definition hash, exact release, complete target, policy snapshot/revision and
consumer version requirements. Its `selection_id` covers that full snapshot.
Its `artifact_id` covers asset ID, release and target, allowing two consumers or
policy revisions to share identical installed content. Neither ID grants permission.

Persist selections using the existing `documents.write`; read bounded JSON with
`documents.read` and validate with `AssetSelection.from_document`. Frozen choices
remain readable without today's Catalog/default. Reading does not silently reselect
or establish current approval. Consumers own Selected state and execution records.

`asset_view` separates:

- **Available:** release declarations matching the requested target, regardless of
  installation or policy enablement.
- **Installed:** validated local facts for the supplied selection, or the current
  resolvable candidate when no selection is supplied. With no index, status is
  `not_configured`; with an index and no resolvable choice, `not_selected`.
- **Selected:** only the caller-supplied frozen choice; defaults remain `null` until
  the consumer selects one. A selection for another target is rejected.
- **Policy/selection_status:** current policy, with `selectable` or a distinct reason.

Existing `resolve`, `page`, `search`, `documents` and asset discovery do not download,
write an index, execute a subprocess, start Dagger or prepare an environment.

## B/C backend receipt boundary

```python
AssetFile(path, sha256)
AssetReceipt(selection, outcome: ToolResult, locator=None, files=(),
             environment_id=None, verified_source_sha256=None)
AssetReceipt.document() -> dict
AssetReceipt.from_document(value) -> AssetReceipt
```

B (uv) and C (aria2) produce the **same** receipt after their actual backend operation.
They preserve the original `ToolResult` status and exit code. A successful delivery
of JSON or a report is not installation success. Success needs `passed`, exit 0,
`executed`, `complete`, `current`, an absolute locator, an entry-file manifest and
the backend's verified source-artifact SHA matching the frozen definition. Python
also needs an opaque full-SHA `environment_id` from the backend's actual uv
environment identity. A manifest must include the declared CLI entry (including
the Windows `.exe` entry variant where appropriate).

The receipt boundary validates facts, not the truthfulness of a third-party
backend. B/C must actually verify the archive/wheel before reporting
`verified_source_sha256`, and must produce file hashes from its installed payload.
This task performs no backend operation. It never invents a passed receipt.
`ToolResult` retains its existing success/failure/uncertain semantics; no new
backend-ready status is introduced.

The persisted form allowlists status, exit code and execution/completeness/current
facts. It excludes backend outputs, parameters, stdout and raw diagnostics.
`failed/17` remains `failed/17`. A failed attempt updates `last_receipt` but preserves
an older verified installation of that same artifact; the failed attempt remains
visible independently. Missing facts cannot create an installed entry.
With no verified installation, unknown/unavailable/interrupted/incomplete backend
outcomes remain `unknown/backend_unknown`, distinct from an indexed local miss.
Backends retain the existing EventSink observation boundary where applicable;
the local receipt/index is not a replacement logging system.

Native locators must equal `native_asset_directory(index.root, selection)`:

```text
<root>/native/asset-<asset_id>/<os>-<arch>-<full-target-sha256>/
    version-<exact-version>/<full-distribution-sha256>/
```

The target hash includes ABI and interpreter constraints and prevents ambiguous
target labels from sharing a directory. Prefixes avoid reserved Windows asset or
version basenames. Caller/configuration owns the root. `asset_root` supports an
explicit path, `VESRYN_TOOL_ASSETS`, Windows LOCALAPPDATA or POSIX XDG_CACHE_HOME
(with ordinary user-cache fallbacks); resolving it creates nothing.

Python receipts retain the explicit uv-owned environment locator, its opaque
identity and entry-file checksums. The index does not copy package metadata,
manage uv private caches, or move/modify uv environments. The backend owns uv
compatibility, environment identity, installation and immutable publication.

OCI definitions can be frozen, but this task has no engine verifier. An absent or
unknown OCI fact remains `missing`/`unknown`; a claimed success is refused with
`backend_unknown`. Reads never probe an engine to turn it into Installed.

## Index integrity and concurrency

Index records use bounded ordinary JSON, canonical checksums, the existing atomic
document writer and a cross-process `filelock`. Writers lock, read the current
index, merge one artifact record and atomically replace the file. Readers do not
create directories or lock files. Multiple versions/platforms coexist. Basic
thread/process concurrency does not discard independent records; this is not a
transaction service, remote registry, general cache manager or scheduler.

Every Installed read checks the index structure/checksum **and re-hashes actual
entry files**. Missing files become `missing/local_missing`; different bytes become
`invalid/integrity_mismatch`. Relative manifest paths cannot escape the explicit
locator. An index file or its checksum alone does not prove installation integrity,
source authenticity, execution permission, or cross-platform executability.
Native installation publication and the uv environment lifecycle remain B/C-owned;
they must not modify a payload while publishing it as an immutable installation.

An invalid index is refused and never overwritten automatically. Index writes have
the existing 2 MiB document bound and an explicit lock timeout. There is no automatic
repair, pruning or eviction. File/index IO errors remain errors, not passed receipts.

## Stable asset errors and consumer use

`AssetError` extends existing `ToolRuntimeError` and exposes `.code`:

| Code | Meaning |
| --- | --- |
| `unregistered_tool` / `unregistered_asset` | Missing capability / missing CLI association; distinct from a local cache miss. |
| `unsupported_target` | No declared OS/architecture/ABI/interpreter-compatible release. |
| `selection_disabled` / `no_matching_version` | Current policy disables selection / no release satisfies exact version and constraints. |
| `invalid_selection` / `selection_target_mismatch` | Invalid frozen snapshot or its digest / view target differs from the caller's choice. |
| `backend_unknown` | Required backend facts absent or no verifier exists; never backend readiness. |
| `local_missing` / `integrity_mismatch` | Entry files missing / source or entry checksum differs. |
| `invalid_location` / `invalid_receipt` | Locator containment/layout or receipt structure is invalid. |
| `invalid_index` / `index_busy` | Corrupt/unsupported local document / another writer holds its lock past timeout. |
| `invalid_definition`, `invalid_digest`, `invalid_source`, `mutable_source`, `mutable_version`, `invalid_backend`, `invalid_target`, `invalid_policy`, `invalid_requirement`, `conflicting_asset` | Invalid release/policy/registration inputs; no installation is attempted. |

Existing Scope errors keep the existing exception/behavior. ECI/Vesryn consumers
must choose using their requirements and target, retain that selection in their
own run, let B/C acquire it explicitly when authorized, inspect the receipt's actual
outcome, and separately use existing Binding/Scope admission for invocation.
Neither cached bytes, selection nor a successful installer authorizes a tool call.
ToolSpec/Binding digests and Provider identity do not contain local install state.

## Real metadata example

Run `python examples/asset_selection.py` after installing this candidate package
(or with this checkout's `src` explicitly on PYTHONPATH). It reads
`examples/asset-definitions.json` and selects two explicit target artifacts offline:

- ripgrep 15.2.0, Windows ARM64/MSVC ZIP, SHA-256
  `e4abca10c3a64ebea742667dd7009449d49403db5460dd6873e389fa2945360f`,
  as declared by the [publisher's release](https://github.com/BurntSushi/ripgrep/releases/tag/15.2.0).
- pytest 9.0.3's universal wheel, SHA-256
  `2c5efc453d45394fdd706ade797c0a81091eccd1d6e4bccfcd476e2b8e0ab5d9`,
  from this checkout's `uv.lock`; installed distribution metadata declares
  Python >=3.10. This is an independent CLI example, not registration of a project library.

These are real source/hash declarations checked on 2026-10-23. No archive is fetched,
backend is run, or installation asserted by the example; Installed is explicitly
`not_configured`. Actual B/C integration and download/install verification are later
tasks. `unregistered/` binaries are not modified or automatically registered.
