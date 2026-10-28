# CLI assets, selections and host tools

This document defines CLI asset contracts, targets, version resolution, local receipt boundaries, and the host-tool lifecycle in `vesryn-tool-runtime`. Native acquisition via aria2 is described in [Native assets](native-assets.md), and python tool environments via uv in [uv tool environments](uv-tool-assets.md).

## Definitions and authority

`AssetDefinition(asset_id, catalog_revision, releases)` is an immutable CLI release declaration associated with existing ToolSpecs by `Catalog.register_asset`. One program can support several capabilities. Ordinary project libraries remain project dependencies, managed by the project's own pyproject/uv.lock.

`AssetRelease` fields:

| Field                        | Meaning                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `version`                    | Exact publisher version. `latest`, `stable`, `default`, `current` are rejected. Independent of `ToolSpec.contract_version`.                                                                                                                                                                                                                                                                             |
| `distribution`               | `python`, `native`, or an existing `oci` reference.                                                                                                                                                                                                                                                                                                                                                     |
| `backend`                    | `uv`, `aria2`, or `oci`, respectively. An acquisition identifier; never a capability Provider.                                                                                                                                                                                                                                                                                                          |
| `source`                     | HTTPS/file artifact URL without embedded credentials, query or fragment; OCI source must end in its exact `@sha256:…` digest. A definition does not establish backend support or readiness.                                                                                                                                                                                                             |
| `sha256`                     | Full lowercase SHA-256 of the distribution artifact. For OCI, its pinned digest. This is distinct from hashes of extracted entry files.                                                                                                                                                                                                                                                                 |
| `entrypoint`                 | CLI entry name, without arguments or path traversal.                                                                                                                                                                                                                                                                                                                                                    |
| `os`, `arch`, `abi`          | Declared target constraints. Native/OCI require explicit OS and architecture; Python universal artifacts may use `any`. An ABI constraint requires an exact target match. For Linux, `abi` carries the C library: `gnu` (glibc) or `musl`; a `manylinux` wheel declares `gnu`, a `musllinux` wheel `musl`, and an absent ABI means the artifact is genuinely unconstrained — not that any libc matches. |
| `package`, `requires_python` | Required for Python distributions: package name and PEP 440 interpreter constraint. Target interpreter version must be supplied explicitly.                                                                                                                                                                                                                                                             |
| `lock_ref`                   | Optional publisher-owned immutable lock reference. Not copied uv metadata or a takeover of the consumer's project lock.                                                                                                                                                                                                                                                                                 |

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
default_tools() -> tuple[dict, ...]
prepare_tool(tool_id, *, version=None, command=None, description=None,
             root=None, allow_network=False, platform=None, uv="uv",
             aria2=None, environ=None, runner=subprocess.run,
             with_packages=None) -> dict
refresh_tools(root=None, environ=None) -> int
uninstall_tool(tool_id, *, root=None, uv="uv", environ=None,
               runner=subprocess.run) -> dict
user_data_root(environ=None, platform=None) -> Path
```

### The two local stores

The user data root (`user_data_root()`) resolves to `%LOCALAPPDATA%\vesryn\data` on Windows and `$XDG_DATA_HOME|~/.local/share/vesryn/data` on other platforms. It holds two persistent stores:

1. `tools.sqlite3`: Registration and installation facts: tool, version, entry, preparation backend (`uv`, `aria2`, or `external`), and the actual verified source URL and SHA256 (`verified_source`, `verified_sha256`).
2. `tools.json`: The Agent-facing tool list: strictly `command` and short `description`, sorted and deduplicated. This file is mounted by Agent hooks (e.g. at SessionStart); it is a snapshot of available commands, not the registry itself.

Verified artifacts (such as fetched Python wheels) live in the asset root (`%LOCALAPPDATA%\vesryn\tool-assets\python\...`), never in the user data root.

### Operational realities and failure semantics

- **Explicit Invocation**: Tool preparation and registration require an explicit call to `prepare_tool()`. The runtime never performs background installation during resolution or queries.
- **Non-Atomic Store Commits**: SQLite commit and `tools.json` publication are coordinated under a cross-process `FileLock`, but are not cross-file atomic. If writing `tools.json` fails after the SQLite commit succeeds, `prepare_tool()` reports status `registered_not_synced`. The registration is safe, and the snapshot can be repaired at any time by calling `refresh_tools()`.
- **Existing Tool Reuse**: A successful entry/version probe permits reuse and registration. The same recorded version and resolved entry retain their installation owner and source proof. An installation without a matching record is `prepared_via: "external"`; lacking source evidence does not make a working CLI unavailable.
- **Verified Python Installation**: For runtime-managed installations, the selected artifact is verified against the publisher digest before installation (`uv tool install <verified artifact>`). An unverifiable wheel is never installed.
- **Safe Uninstallation**: `uv` ownership permits removal through uv; `aria2` ownership permits removal of the runtime exposure copy while cached artifacts remain. External installations are only unregistered. A failed backend uninstall retains the registration and reports `uninstall_failed`.

For a uv-managed CLI without a version line, Runtime verifies the selected
version and resolved entry against uv's environment inventory and requires
consistent installed dependencies. If `--version` fails without reporting a
version, `--help` must succeed before this fallback is allowed. Launch failures,
a version printed with a nonzero exit, and failed help probes remain `conflict`.
The same checks apply after installation and when reusing an existing entry.

### Installation verification

The bundled `sphinx` asset declares Sphinx 9.2.0 (`sphinx-build`, Python
`>=3.13`) and its official universal wheel's source and SHA-256. MyST-Parser,
Sphinx-Needs, CodeLinks, Test-Reports and AutoAPI are extensions of that tool
environment, not independent Agent CLI registrations. A verified Sphinx wheel
alone does not establish that those extensions or all transitive dependencies
are installed or verified.

### Python CLI plugins in the same tool environment

Pass an explicit `with_packages` list/tuple of `name==version` requirements
to prepare plugins alongside a uv-managed main tool. Runtime normalizes package
names and order, deduplicates equal pins and rejects conflicting pins, main-package
overrides, ranges, wildcards, markers, extras, URLs and paths before preparation.
Explicit package requests apply only to `provider="uv"`.

`with_packages=None` preserves the existing behavior for callers that do not
manage plugins. Explicit `()` asks uv to reconcile an empty additional-request
set; it is distinct from leaving plugin configuration alone. A package that is
still needed transitively can remain in the environment.

```python
from vesryn_tool_runtime import prepare_tool

receipt = prepare_tool(
    "sphinx",
    version="9.2.0",
    command="sphinx-build",
    description="Build the project's Sphinx documentation",
    with_packages=(
        "myst-parser==5.1.0",
        "sphinx-needs==9.1.0",
        "sphinx-codelinks==2.0.1",
        "sphinx-test-reports==3.0.1",
        "sphinx-autoapi==3.8.1",
    ),
    allow_network=True,
)
```

The main wheel still comes from the bundled declaration and existing SHA-256
verification path. Runtime passes it and the complete additional request to
`uv tool install --python ... --with ...`; uv resolves transitive dependencies
and manages its own environment. Plugins do not receive independent Agent entries.
Use explicit package requests on subsequent calls whenever the plugin set matters.

A matching CLI version alone cannot establish plugin reuse. Explicit requests
also require uv's recorded complete additional set, that tool environment's actual
distribution versions and a successful `uv pip check`. A changed/missing set is
reconciled by uv; an unidentifiable or shadowing external command is `conflict`.
After reconciliation, Runtime repeats those checks before registration. Failed uv
operations remain `uv_install_failed`; missing/inconsistent evidence is
`environment_unverified`, never a successful registration. `installed` means the
requested configuration was prepared, not that every package was downloaded again.

Explicit-package outcomes include an `environment` document: `python`, `prefix`,
`python_version`, canonical `with_packages`, sorted `packages` (`name`/`version`),
and `dependencies_consistent`. These are observed through the tool's own Python
with `-I -B` and uv's public interfaces. They are returned evidence, not another
environment registry or an inventory hash. SQLite's existing installation facts
and the strict `tools.json` command/description list retain their shapes.

The public tool text view is verified with uv 0.12.23. Unsupported output or a
Python reporting another prefix is refused; Runtime does not parse private
`uv-receipt.toml` or package-cache layouts. The caller's effective `environ`,
including `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` and `UV_CACHE_DIR`, reaches the uv
processes, allowing fully isolated roots without changing global configuration.

Check extensions with `receipt["environment"]["python"]`, rather than project
Python: for this example it must import `sphinx`, `myst_parser` and `sphinx_needs`
and report the selected distribution versions. A package inventory/import probe
does not verify all installed distribution bytes or replace publisher provenance.

### Main-artifact provenance

:::{spec} Verify the installed main artifact against its selected release
:id: SPEC_TR_MAIN_ARTIFACT_PROOF

The proof fields record the source URL and SHA256 actually verified and used
for the installation; they are both present or both NULL. The `prepare_tool`
result's `source_verified` compares that proof with the selected release's
version, source and digest for the target. It is computed, not a stored boolean,
and does not depend on the installation owner.
:::

Inspection and an unchanged uv environment preserve existing main-artifact proof,
including an unknown proof. If an explicit plugin preparation needs to establish
new main provenance, it requests `--reinstall-package <main>` from the already
verified wheel. It does not globally force or reinstall every dependency.

See [Persist Installation Provenance](adr/persist-installation-provenance.md)
for the architecture decision and [the Schema upgrade boundary](discovery-contracts.md#migration-boundary-explicit)
for existing registration stores.

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

| Code                                                                                                                                                                                             | Meaning                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| `unregistered_tool` / `unregistered_asset`                                                                                                                                                       | Missing capability / missing CLI association; distinct from a local cache miss.         |
| `unsupported_target`                                                                                                                                                                             | No declared OS/architecture/ABI/interpreter-compatible release.                         |
| `selection_disabled` / `no_matching_version`                                                                                                                                                     | Current policy disables selection / no release satisfies exact version and constraints. |
| `invalid_selection` / `selection_target_mismatch`                                                                                                                                                | Invalid frozen snapshot or its digest / view target differs from the caller's choice.   |
| `backend_unknown`                                                                                                                                                                                | Required backend facts absent or no verifier exists; never backend readiness.           |
| `local_missing` / `integrity_mismatch`                                                                                                                                                           | Entry files missing / source or entry checksum differs.                                 |
| `invalid_location` / `invalid_receipt`                                                                                                                                                           | Locator containment/layout or receipt structure is invalid.                             |
| `invalid_index` / `index_busy`                                                                                                                                                                   | Corrupt/unsupported local document / another writer holds its lock past timeout.        |
| `invalid_definition`, `invalid_digest`, `invalid_source`, `mutable_source`, `mutable_version`, `invalid_backend`, `invalid_target`, `invalid_policy`, `invalid_requirement`, `conflicting_asset` | Invalid release/policy/registration inputs; no installation is attempted.               |

Host tool operations raise `HostToolError`, with specific failure codes including `conflict`, `missing_release`, `unsupported_target`, `backend_required`, `install_failed`, `uninstall_failed`, and `registered_not_synced`.

Existing Scope errors keep the existing exception/behavior. Consumers must choose using their requirements and target, retain that selection in their own run, let the backend acquire it explicitly when authorized, inspect the receipt's actual outcome, and separately use existing Binding/Scope admission for invocation. Neither cached bytes, selection nor a successful installer authorizes a tool call. ToolSpec/Binding digests and Provider identity do not contain local install state.
