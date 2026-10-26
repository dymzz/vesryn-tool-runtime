# Public Python API

This document describes the currently supported public API groups, essential behavioral contracts, failure semantics, and usage patterns in `vesryn_tool_runtime`.

> **Note**: Exhaustive, symbol-level API reference documentation is generated from docstrings and type annotations via Sphinx AutoAPI in subsequent documentation tooling integration.

Import all public symbols directly from `vesryn_tool_runtime`.

## 1. Public API Groups

The exported symbols in `__all__` belong to seven functional groups:

### 1.1 Tool Contracts & Invocation
- **Core Types**: `ToolSpec`, `ToolResult`, `Invocation`, `ExecutionContext`, `ToolAdapter`, `DispatchReceipt`.
- **Runtime & Execution**: `ToolRuntime`, `invoke_tool()`, `checked_result()`.
- **Exceptions**: `ToolRuntimeError` (base exception for runtime errors).

Contracts define generic tools independent of workflow engines. `ToolAdapter.invoke(calls, context)` receives admitted Invocations and yields one `ToolResult` per step. `ToolRuntime` handles batch grouping, admission evaluation, result validation, and safe observation emission.

### 1.2 Catalog & Providers
- **Catalog Management**: `Catalog`, `compose()`, `compose_catalog()`, `ComposedCatalog`.
- **Providers & Scope**: `provider()`, `DiscoveryScope`.

Catalogs represent explicit collections of tool specifications and adapters. Duplicate tool ownership is rejected atomically during composition. `DiscoveryScope` governs visibility filtering and host-level admission permissions.

### 1.3 Selection Binding
- **Binding Functions**: `create_binding()`, `verify_binding()`, `canonical_binding()`, `verify_document()`.
- **Constants**: `SELECTION_BINDING` (Schema 1 identifier).

Selection bindings freeze the exact contract hash, tool version, provider identity, parameter constraints, and scope permissions into an immutable, verifiable document.

### 1.4 Discovery Records & Store
- **Record Types**: `ToolAsset`, `ToolGroup`, `ToolAccess`, `GroupMember`, `Platform`, `ToolAssetVersion`.
- **Store & Seed**: `open_record_store()`, `upgrade_record_store()`, `bundled_records()`. Opening does not migrate an existing store; the explicit upgrade and its evidence rules are documented in [Discovery contracts](discovery-contracts.md#migration-boundary-explicit).
- **Serialization**: `record_document()`, `record_from_document()`.
- **Query & Pagination**: `DiscoveryQuery`, `DiscoveryPage`, `DiscoveryDiagnostic`, `DiscoveryErrorDocument`.
- **Exceptions**: `RecordError`, `DiscoveryContractError`.

Provides a normalized six-table SQLite backing store for tool assets, releases, groups, and access entry points with progressive disclosure contracts.

### 1.5 Asset Contracts & Backends
- **Asset Definitions & Policy**: `AssetDefinition`, `AssetRelease`, `AssetTarget`, `AssetSelection`, `AssetPolicy`.
- **Index & Receipts**: `AssetIndex`, `AssetReceipt`, `AssetFile`, `asset_root()`, `native_asset_directory()`.
- **Backends & Delivery**: `Aria2NativeBackend`, `Aria2Source`, `NativeAssetDelivery`, `UvToolBackend`, `UvLock`.
- **Exceptions**: `AssetError`.

Manages CLI asset declarations, target resolution (including Linux glibc/musl ABI constraints), receipts, aria2 native payload verification, and uv tool environments.

### 1.6 Host Tools Lifecycle
- **Functions**: `default_tools()`, `prepare_tool()`, `refresh_tools()`, `uninstall_tool()`, `user_data_root()`.
- **Exceptions**: `HostToolError`.

Manages host-level tool preparation and uninstallation, maintaining authoritative registration facts in SQLite (`tools.sqlite3`) and publishing the Agent-facing tool manifest (`tools.json`).

### 1.7 Compatibility Bridge
- **Functions**: `legacy_preparation_definitions()`.

Read-only adapter translating live record assets into legacy preparation structures for preparation backends.

---

## 2. Core Behavioral & Failure Contracts

1. **Deterministic Bounded Documents**:
   - JSON serialization adheres to strict bounds (default 2 MiB) with rejection of duplicate keys and NaN/Infinity values.
   - File writes are atomic or exclusive (`filelock`).

2. **Admission and Scope Gates**:
   - Tool discovery filtering precedes ranking and pagination.
   - Tool admission requires explicit host scope approval; discovery never implies execution admission.

3. **Result Validation**:
   - `checked_result(result, spec)` validates returned outputs strictly against the tool's declared JSON Schema.
   - If execution fails and output validation also fails, the non-zero exit code is preserved while `validation_errors` records the schema violation.

4. **Safe Event Emission**:
   - Events emitted to `vesryn_log.EventSink` include only allowlisted fields: tool ID, invocation ID, execution facts, status, and exit codes.
   - Raw parameters, execution diagnostics, credentials, and SDK exceptions are never emitted to logs.

5. **Dual-Store Host Tool Synchronization**:
   - SQLite commit and `tools.json` publication are non-atomic across storage boundaries.
   - If JSON synchronization fails after registration commits, `registered_not_synced` is reported; state is fully recovered by running `refresh_tools()`.

---

## 3. Representative Usage Examples

### 3.1 Direct Tool Invocation

```python
from vesryn_tool_runtime import (
    Catalog,
    DiscoveryScope,
    ToolAdapter,
    ToolResult,
    ToolSpec,
    invoke_tool,
)


class EchoAdapter(ToolAdapter):
    def invoke(self, calls, context):
        results = []
        for call in calls:
            msg = call.inputs.get("message", "")
            results.append(
                ToolResult(status="passed", exit_code=0, outputs={"echo": msg})
            )
        return tuple(results)


spec = ToolSpec(
    tool_id="demo.echo",
    contract_version="1.0.0",
    description="Echo message",
    inputs_schema={"type": "object", "properties": {"message": {"type": "string"}}},
    outputs_schema={"type": "object", "properties": {"echo": {"type": "string"}}},
)

catalog = Catalog()
catalog.register(spec, EchoAdapter())
scope = DiscoveryScope(permissions=("tool:demo.echo",))

receipt = invoke_tool(
    "demo.echo", inputs={"message": "hello"}, catalog=catalog, scope=scope
)
assert receipt.results[0]["outputs"]["echo"] == "hello"
```

### 3.2 Bundled Records Loading and Catalog Composition

```python
from vesryn_tool_runtime import bundled_records, compose_catalog, open_record_store

# Open persistent store (or in-memory with ":memory:")
store = open_record_store("tools_records.sqlite3")

# Atomic batch registration of bundled seed records
store.put_records(bundled_records())

# Read-only composed catalog for discovery and resolution
catalog = compose_catalog(store)
tool = catalog.resolve("ripgrep")
```

### 3.3 Host Tool Preparation

```python
from vesryn_tool_runtime import prepare_tool, refresh_tools

# Explicitly prepare a tool declared in the seed records
receipt = prepare_tool("vulture", version="2.16", allow_network=True)

if receipt["status"] == "registered_not_synced":
    # Recover JSON manifest synchronization
    refresh_tools()
```

For plugins in one Python CLI environment, explicitly select pinned packages:

```python
receipt = prepare_tool(
    "sphinx", version="9.2.0", command="sphinx-build",
    description="Build Sphinx documentation", allow_network=True,
    with_packages=("myst-parser==5.1.0", "sphinx-needs==9.1.0"),
)
```

`with_packages=None` keeps legacy behavior; explicit `()` removes additional
requests through uv's own reconciliation. A same-version CLI is not a plugin
environment hit: the complete request, actual tool Python/distributions and
dependency consistency are checked. Explicit-package results carry an
`environment` evidence document; its `python` is the interpreter to use for
extension imports. `source_verified` remains proof of the declared main artifact,
not an environment-wide supply-chain statement. See
[Python CLI plugin preparation](tool-assets.md#python-cli-plugins-in-the-same-tool-environment)
for ownership, failure and reuse semantics.
