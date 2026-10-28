# Consumer migration

Consumers (Vesryn and engineering-ci) depend on `vesryn-tool-runtime` through versioned package releases or development source pins.

Old imports from `vesryn.workflow_core`, `.contracts`, `.documents`, `.scope`, `.schemas`, and `vesryn.tool_discovery` export the authoritative types/functions from `vesryn_tool_runtime`. In particular, there are no duplicate ToolSpec/ToolResult classes. `runtime.checked_result` stays a compatibility export. `vesryn.invocation.invoke_tool` keeps its original workflow/history receipt; this package's direct convenience function is the tool-level API and returns `DispatchReceipt`.

Vesryn Workflow Runtime delegates Adapter invocation and result handling after saving attempt intent. DAG grouping supplies each Adapter's existing predecessor view. The optional `scope`, `event_sink`, `bindings` Runtime arguments allow host policy; legacy raw Catalog workflows retain their existing trusted explicit-registration admission behavior. Unified Catalogs use their declared discovery/admission scope.

engineering-ci directly imports common contracts in its check Provider/Adapter. Its compatibility workflow imports continue through Vesryn. Generic binding verification is delegated; workflow generation, execution associations, paths, execution locking and `call`/`run`/`resume` remain in engineering-ci. Frozen bindings are revalidated again at ToolRuntime dispatch against current scope and execution identity. Old Schema 1 document bytes/hash inputs remain valid.

Development `tool.uv.sources` overrides explicitly select the adjacent Tool Runtime checkout in these two consumers. They are development inputs, not wheel metadata. Before a consumer release, replace the override with the accepted immutable component reference and regenerate its lock; do not release an adjacent path pin. engineering-ci's optional Harness pin must likewise move to the integrated Vesryn candidate before distribution; testing only its older pinned Harness is insufficient. The existing dependency scanner intentionally rejects these local path sources. Its production policy is unchanged; development-path rejection is explicitly asserted by the consumer regression test. Production security readiness requires the immutable references, not a waiver for these paths.

For local shared-tool Dagger development, pass both existing Vesryn source/module inputs and `--tool-runtime-source <authorized-runtime-checkout>` to Vesryn's Workflow CLI/Registry. The optional Python `tool_runtime_source` argument and Dagger `tool_runtime_source` Directory are forwarded explicitly. The module mounts the selected package at the path declared by the development lock. Its contents are checked on the host before/after invocation. No neighboring source is inferred.

The logs repo/API is unchanged. Additional safe tool events are independent of existing workflow observations and readable history.

## Upgrading from 0.3.1

Version 0.4.0 replaces the discovery prototype and the shared-assets loader API.
Regenerate discovery payloads from the current declarations; the former JSON
shapes and summary classes have no compatibility layer.

| Former interface | Current interface |
|---|---|
| `shared_definition_documents`, `load_shared_definitions`, `register_shared_definitions` | Read `bundled_records()`, persist explicitly with `RecordStore.put_records()`, and compose with `compose_catalog()`. |
| `GroupSummary`, `CandidateSummary`, `AccessEntrySummary`, `ContractDetail` | Consume `ToolGroup`, `ToolAsset` and `ToolAccess` records and their documented fields. |
| `DiscoveryPage(item_kind=..., items=...)` | Supply `record_kind` and `records` using the [current document contract](discovery-contracts.md). |
| `GroupMember(catalog_ref=...)` | Use the member's `tool_id` and required `summary`; consult the generated API reference for optional member fields. |
| `compose_access_id()` | Supply the declared `ToolAccess.access_id`; it is not derived from a catalog path. |

Use `record_document()` and `record_from_document()` for current record
serialization. Own the writable database path explicitly, close the store after
use, and use `upgrade_record_store()` only for the local store versions it
supports. It does not translate the removed discovery prototype formats.

Host CLI consumers can call `prepare_tool()` with an explicit command and
description. Registration records the actual installation owner and source
proof; reusing an external installation does not establish publisher-artifact
verification. See [host-tool failure semantics](tool-assets.md#operational-realities-and-failure-semantics).

Griffe reports 48 native diagnostics against the 0.3.1 baseline for the accepted
source, including the removals and constructor changes above. The release keeps
those diagnostics as evidence. They cover Python API shape; consumers must
verify their own CLI, SQLite, hook and runtime-behavior integrations. The package
still requires Python 3.14 or later, and no wider consumer compatibility range
is claimed by this release.
