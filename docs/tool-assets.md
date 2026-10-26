# CLI assets, selections and host tools

This document defines CLI asset contracts, targets, version resolution, local receipt boundaries, and the host-tool lifecycle in `vesryn-tool-runtime`. Native acquisition via aria2 is described in [Native assets](native-assets.md), and python tool environments via uv in [uv tool environments](uv-tool-assets.md).

## Definitions and authority

`AssetDefinition(asset_id, catalog_revision, releases)` is an immutable CLI release declaration associated with existing ToolSpecs by `Catalog.register_asset`. One program can support several capabilities. Ordinary project libraries remain project dependencies, managed by the project's own pyproject/uv.lock.

`AssetRelease` fields:

| Field | Meaning |
| --- | --- |
| `version` | Exact publisher version. `latest`, `stable`, `default`, `current` are rejected. Independent of `ToolSpec.contract_version`. |
| `distribution` | `python`, `native`, or an existing `oci` reference. |
| `backend` | `uv`, `aria2`, or `oci`, respectively. An acquisition identifier; never a capability Provider. |
| `source` | HTTPS/file artifact URL without embedded credentials, query or fragment; OCI source must end in its exact `@sha256:…` digest. A definition does not establish backend support or readiness. |
| `sha256` | Full lowercase SHA-256 of the distribution artifact. For OCI, its pinned digest. This is distinct from hashes of extracted entry files. |
| `entrypoint` | CLI entry name, without arguments or path traversal. |
| `os`, `arch`, `abi` | Declared target constraints. Native/OCI require explicit OS and architecture; Python universal artifacts may use `any`. An ABI constraint requires an exact target match. For Linux, `abi` carries the C library: `gnu` (glibc) or `musl`; a `manylinux` wheel declares `gnu`, a `musllinux` wheel `musl`, and an absent ABI means the artifact is genuinely unconstrained — not that any libc matches. |
| `package`, `requires_python` | Required for Python distributions: package name and PEP 440 interpreter constraint. Target interpreter version must be supplied explicitly. |
| `lock_ref` | Optional publisher-owned immutable lock reference. Not copied uv metadata or a takeover of the consumer's project lock. |

The release declaration's **ordered tuple** is the default preference order. The first compatible release satisfying consumer requirements and current policy is chosen. The publisher changes the declaration/revision to advance that default; an approval does not permanently freeze today's version. There is no implicit network query, numeric-version sorting, host detection or installed-version lookup. An explicit `version` matches literal publisher versions; `specifier` uses PEP 440. Non-PEP-440 native versions can still be selected exactly or by published default.

`AssetPolicy(revision, enabled=True, specifier="")` records policy revision, disablement and optional allowed-version constraints. Disablement is a policy property. `AssetTarget(os, arch, abi=None, python=None)` is explicit; examples use `windows`/`linux`, `x86_64`/`aarch64`, and `gnu`/`msvc`. Labels are matched exactly.

Release declarations are version authority. Selection documents, environment locks, cache keys and reports are derived records. Artifact source/backend metadata does not replace `Catalog.provider_for(tool_id)`, which keeps its original meaning.

## Platform and ABI semantics

`abi` states the artifact's real C-library constraint, not a documentation note. Universal Python wheels (`py3-none-any.whl`) are platform-independent and keep `abi: null`. Wheels with compiled extensions (such as `manylinux_2_17_x86_64`) declare `abi: "gnu"`, while Alpine/musl wheels declare `abi: "musl"`.

Per the [PyPA platform tag specification](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/), `manylinux` means glibc and `musllinux` means musl; `linux`/`x86_64` alone does not equate the two.

Enforced consequences:
- An explicit target `AssetTarget("linux", "x86_64", abi="musl")` rejects glibc wheels (`unsupported_target`), and the uv backend resolves them with the `x86_64-unknown-linux-musl` triple — never a silent GNU one.
- A Linux target with no ABI states an unknown C library. It is explicitly rejected (`unsupported_target`) for libc-constrained artifacts: an artifact requiring glibc is not reported usable where compatibility cannot be proven. Consumers whose real environment is glibc explicitly declare `abi: "gnu"`.
- The uv backend reads the wheel's filename (`manylinux…`/`musllinux…`) and admits only a matching Linux/libc target.
- Pinned tool versions, digests, and sources are declared in the bundled seed (`record_seed.sql`) and loaded via `bundled_records()`.

## OCI asset distribution and execution boundaries

OCI tool declarations represent containerized tool entrypoints.

- **Immutable Artifact Identity**: Declarations pin exact SHA-256 digests. Tags or unpinned image names are strictly prohibited.
- **Manifest vs. Multi-Arch Index Digest**: Releases pin the target platform manifest digest in both `source` and `sha256`. Multi-arch index digests serve as provenance only; they are not substituted for the platform manifest.
- **No Local OCI Installer**: `vesryn-tool-runtime` does not implement an OCI puller, image unpacker, or container runtime. OCI image acquisition, layer caching, and isolation execution stay natively with Dagger (`dag.container().from_(image)`).
- **Target OS Restriction**: All OCI image releases target `linux` (`x86_64` or `aarch64`). Host attempts to select OCI assets on non-Linux targets (`windows`, `macos`) yield `unsupported_target`.

## Host tools lifecycle and local stores

The host tools module (`host_tools.py`) manages local tool preparation, registration, and synchronizes an Agent-facing tool manifest.

### Entry points

Exported from `vesryn_tool_runtime`:

```python
default_tools() -> list[dict]
prepare_tool(tool_id: str, *, command=None, version=None, root=None,
             environ=None, allow_network=True, backend=None,
             platform=None, runner=None) -> dict
refresh_tools(*, root=None, environ=None) -> list[dict]
uninstall_tool(tool_id: str, *, root=None, environ=None, runner=None) -> dict
user_data_root() -> Path
```

### The two local stores

The user data root (`user_data_root()`) resolves to `%LOCALAPPDATA%\vesryn\data` on Windows and `$XDG_DATA_HOME|~/.local/share/vesryn/data` on other platforms. It holds two persistent stores:

1. `tools.sqlite3`: The authoritative registration facts table: which tool, version, entry, installation owner (`runtime` vs `external`), and whether the source artifact was verified (`source_verified`).
2. `tools.json`: The Agent-facing tool list: strictly `command` and short `description`, sorted and deduplicated. This file is mounted by Agent hooks (e.g. at SessionStart); it is a snapshot of available commands, not the registry itself.

Verified artifacts (such as fetched Python wheels) live in the asset root (`%LOCALAPPDATA%\vesryn\tool-assets\python\...`), never in the user data root.

### Operational realities and failure semantics

- **Explicit Invocation**: Tool preparation and registration require an explicit call to `prepare_tool()`. The runtime never performs background installation during resolution or queries.
- **Non-Atomic Store Commits**: SQLite commit and `tools.json` publication are coordinated under a cross-process `FileLock`, but are not cross-file atomic. If writing `tools.json` fails after the SQLite commit succeeds, `prepare_tool()` reports status `registered_not_synced`. The registration is safe, and the snapshot can be repaired at any time by calling `refresh_tools()`.
- **External Tool Reuse**: If an existing executable matching the requested tool and version is discovered on `PATH`, it is registered as `prepared_via: "external"`. Reusing an existing executable does not assert that its source artifact matches the publisher SHA-256 (`source_verified: false`).
- **Verified Python Installation**: For runtime-managed installations, the selected artifact is verified against the publisher digest before installation (`uv tool install <verified artifact>`). An unverifiable wheel is never installed.
- **Safe Uninstallation**: `uninstall_tool()` only cleans up installations owned by the runtime (`prepared_via: "runtime"`). If the backend uninstall fails, the registration in `tools.sqlite3` is retained and `uninstall_failed` is reported. Registration is dropped only after successful removal.

## Public signatures

All types/helpers below are exported from `vesryn_tool_runtime`:

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

Register the ToolSpec/adapter first. `register_asset` requires at least one existing tool ID, supports one definition associated with many tools, and rejects conflicting asset ownership atomically. Composition and scoped catalogs preserve associations and original Provider identities; they do not build a second Registry.

The selection contains tool ID/Provider/contract hash, asset ID, publication revision and definition hash, exact release, complete target, policy snapshot/revision and consumer version requirements. Its `selection_id` covers that full snapshot. Its `artifact_id` covers asset ID, release and target, allowing two consumers or policy revisions to share identical installed content. Neither ID grants permission.

Persist selections using the existing `documents.write`; read bounded JSON with `documents.read` and validate with `AssetSelection.from_document`. Frozen choices remain readable without today's Catalog/default. Reading does not silently reselect or establish current approval. Consumers own Selected state and execution records.

`asset_view` separates:

- **Available:** release declarations matching the requested target, regardless of installation or policy enablement.
- **Installed:** validated local facts for the supplied selection, or the current resolvable candidate when no selection is supplied. With no index, status is `not_configured`; with an index and no resolvable choice, `not_selected`.
- **Selected:** only the caller-supplied frozen choice; defaults remain `null` until the consumer selects one. A selection for another target is rejected.
- **Policy/selection_status:** current policy, with `selectable` or a distinct reason.

Existing `resolve`, `page`, `search`, `documents` and asset discovery do not download, write an index, execute a subprocess, start Dagger or prepare an environment.

## B/C backend receipt boundary

```python
AssetFile(path, sha256)
AssetReceipt(selection, outcome: ToolResult, locator=None, files=(),
             environment_id=None, verified_source_sha256=None)
AssetReceipt.document() -> dict
AssetReceipt.from_document(value) -> AssetReceipt
```

B (uv) and C (aria2) produce the **same** receipt after their actual backend operation. They preserve the original `ToolResult` status and exit code. A successful delivery of JSON or a report is not installation success. Success needs `passed`, exit 0, `executed`, `complete`, `current`, an absolute locator, an entry-file manifest and the backend's verified source-artifact SHA matching the frozen definition. Python also needs an opaque full-SHA `environment_id` from the backend's actual uv environment identity. A manifest must include the declared CLI entry (including the Windows `.exe` entry variant where appropriate).

The receipt boundary validates facts, not the truthfulness of a third-party backend. B/C must actually verify the archive/wheel before reporting `verified_source_sha256`, and must produce file hashes from its installed payload. This task performs no backend operation. It never invents a passed receipt. `ToolResult` retains its existing success/failure/uncertain semantics; no new backend-ready status is introduced.

The persisted form allowlists status, exit code and execution/completeness/current facts. It excludes backend outputs, parameters, stdout and raw diagnostics. `failed/17` remains `failed/17`. A failed attempt updates `last_receipt` but preserves an older verified installation of that same artifact; the failed attempt remains visible independently. Missing facts cannot create an installed entry. With no verified installation, unknown/unavailable/interrupted/incomplete backend outcomes remain `unknown/backend_unknown`, distinct from an indexed local miss. Backends retain the existing EventSink observation boundary where applicable; the local receipt/index is not a replacement logging system.

Native locators must equal `native_asset_directory(index.root, selection)`:

```text
<root>/native/asset-<asset_id>/<os>-<arch>-<full-target-sha256>/
    version-<exact-version>/<full-distribution-sha256>/
```

The target hash includes ABI and interpreter constraints and prevents ambiguous target labels from sharing a directory. Prefixes avoid reserved Windows asset or version basenames. Caller/configuration owns the root. `asset_root` supports an explicit path, `VESRYN_TOOL_ASSETS`, Windows LOCALAPPDATA or POSIX XDG_CACHE_HOME (with ordinary user-cache fallbacks); resolving it creates nothing.

Python receipts retain the explicit uv-owned environment locator, its opaque identity and entry-file checksums. The index does not copy package metadata, manage uv private caches, or move/modify uv environments. The backend owns uv compatibility, environment identity, installation and immutable publication.

## Compatibility entry points

The package provides `legacy_preparation_definitions()` in `vesryn_tool_runtime`:
- **Role**: Read-only compatibility adapter that transforms records from `bundled_records()` into the legacy `AssetDefinition` format expected by preparation backends (`host_tools.py`).
- **Boundary**: It is an internal bridge; new code should directly consume discovery records (`ToolAsset`, `ToolGroup`, `ToolAccess`) and `RecordStore`.

## Index integrity and concurrency

Index records use bounded ordinary JSON, canonical checksums, the existing atomic document writer and a cross-process `filelock`. Writers lock, read the current index, merge one artifact record and atomically replace the file. Readers do not create directories or lock files. Multiple versions/platforms coexist. Basic thread/process concurrency does not discard independent records; this is not a transaction service, remote registry, general cache manager or scheduler.

Every Installed read checks the index structure/checksum **and re-hashes actual entry files**. Missing files become `missing/local_missing`; different bytes become `invalid/integrity_mismatch`. Relative manifest paths cannot escape the explicit locator. An index file or its checksum alone does not prove installation integrity, source authenticity, execution permission, or cross-platform executability. Native installation publication and the uv environment lifecycle remain B/C-owned; they must not modify a payload while publishing it as an immutable installation.

An invalid index is refused and never overwritten automatically. Index writes have the existing 2 MiB document bound and an explicit lock timeout. There is no automatic repair, pruning or eviction. File/index IO errors remain errors, not passed receipts.

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

Host tool operations raise `HostToolError`, with specific failure codes including `conflict`, `missing_release`, `unsupported_target`, `backend_required`, `install_failed`, `uninstall_failed`, and `registered_not_synced`.

Existing Scope errors keep the existing exception/behavior. Consumers must choose using their requirements and target, retain that selection in their own run, let the backend acquire it explicitly when authorized, inspect the receipt's actual outcome, and separately use existing Binding/Scope admission for invocation. Neither cached bytes, selection nor a successful installer authorizes a tool call. ToolSpec/Binding digests and Provider identity do not contain local install state.
