# Public Python API (0.1.0)

Import public symbols from `vesryn_tool_runtime`. `ToolRuntimeError` is a
`ValueError`; the legacy `documents.WorkflowError` names the same exception type.
`documents.canonical`, `digest`, `read`, `decode`, `write`, and the documented
`schemas` helpers retain bounded, finite, deterministic JSON behavior. Documents
use a 2 MiB bound and reject duplicate fields; writes are exclusive or atomic.

| API | Contract |
| --- | --- |
| `ToolSpec` | Existing fields/defaults and SHA-256 computation. Purpose/display metadata does not change the contract digest; schemas, effect, recovery, environment and source do. `document`, `summary`, `validate`, `sha256` retain existing behavior. Write tools require manual recovery. |
| `ToolResult` | `status`, `exit_code`, `outputs`, `executed`, `complete`, `current`, `reused`, `report_generated`, `reason`, optional `summary`; `document()` serializes facts. |
| `Invocation` | Existing `step_id`, `tool_id`, `inputs`, `attempt`, optional `previous`. Attempts are positive for dispatch and step IDs unique within a request. |
| `ExecutionContext` | Existing `execution_id`, `generation_id`, `definition_id`, `run_dir`, `predecessors`. Direct calls use a default context without workflow identifiers; no new workflow model is introduced. |
| `ToolAdapter.invoke(calls, context)` | Receives a tuple of admitted Invocations; returns exactly one ToolResult per step_id. Backend execution and previous-evidence verification remain adapter responsibilities. |
| `Catalog` | `register`, `merge`, `resolve`, `documents`, `page`, `search`; duplicate ownership is rejected atomically. `provider_for(tool_id)` retains declared Provider ownership across composition. |
| `DiscoveryScope` | Existing repository/task labels, environment, permissions, availability and host constraint. `matches` filters; `admit` requires explicit permissions. Repository labels never grant permission. |
| `compose(*catalogs)` | Explicitly combines existing Catalogs. No global registry or automatic matching. |
| `provider(name, root)` | Loads exactly one explicitly named installed `vesryn.adapters` entry point, preserving the existing discovery mechanism. Reserved shared provider names cannot load as domain providers. |
| `create_binding(catalog, tool_id, *, provider, parameters=None, scope=None)` | Returns a Schema 1 binding document; no workflow or persistence. Provider identity must be declared on the supplied Catalog. |
| `verify_document(binding)` | Schema and canonical integrity validation. |
| `verify_binding(binding, catalog, *, current_scope=None)` | Checks current tool version/hash/summary, Provider, parameters, bound and current scope; returns `(spec, adapter)`. No reselection or permission grant. |
| `ToolRuntime(catalog, *, scope=None, event_sink=None)` | Defaults to Catalog discovery scope or discovery-only scope. |
| `runtime.invoke(call, context=None, *, binding=None)` | Single invocation, returns DispatchReceipt. |
| `runtime.dispatch(calls, context=None, *, bindings=None, batch_id=None)` | Groups calls by original Adapter identity; one invocation per admitted Adapter group. Bindings map step IDs to frozen documents. |
| `invoke_tool(tool_id, inputs=None, *, catalog, scope, context=None, binding=None, event_sink=None)` | Direct one-call convenience API, with step ID `call` and attempt 1. No disk side effects unless Adapter/Sink writes. |
| `checked_result(result, spec)` | Strict result and output validation; returns a document or raises ToolRuntimeError. |

`DispatchReceipt` contains `results` (validated/normalized result documents),
`execution_facts` (safe original Adapter facts, including its actual exit code), unique
`invocation_ids`, `batch_ids`, `admission_errors`, `validation_errors`,
`observation_errors`, `observation_status` and `interrupted`. Diagnostics are safe
fixed messages, without input or SDK error contents. Observation status is
`not_configured`, `complete` or `incomplete` for this dispatch only.

`registry.scoped_catalog(catalog, scope)` applies the existing scoped Adapter
wrapper while preserving original batching and per-tool Provider identity.

The extracted `dagger_discovery` module exposes existing exposure loading,
introspection, mapping and registration interfaces from Vesryn. It maps explicit
TypeDefs/exposures without importing the Dagger SDK or executing exposed functions.
