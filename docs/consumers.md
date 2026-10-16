# Consumer migration

Vesryn depends on `vesryn-tool-runtime==0.1.0`. Old imports from
`vesryn.workflow_core`, `.contracts`, `.documents`, `.scope`, `.schemas`, and
`vesryn.tool_discovery` export the authoritative types/functions. In particular,
there are no duplicate ToolSpec/ToolResult classes. `runtime.checked_result` stays
a compatibility export. `vesryn.invocation.invoke_tool` keeps its original
workflow/history receipt; the new package's direct convenience function is the
tool-level API and returns DispatchReceipt.

Vesryn Workflow Runtime delegates Adapter invocation/result handling after saving
attempt intent. DAG grouping supplies each Adapter's existing predecessor view.
The optional `scope`, `event_sink`, `bindings` Runtime arguments allow host policy;
legacy raw Catalog workflows retain their existing trusted explicit-registration
admission behavior. Unified Catalogs use their declared discovery/admission scope.

engineering-ci directly imports common contracts in its check Provider/Adapter.
Its compatibility workflow imports continue through Vesryn. Generic binding
verification is delegated; workflow generation, execution associations, paths,
execution locking and `call`/`run`/`resume` remain in engineering-ci. Frozen bindings
are revalidated again at ToolRuntime dispatch against current scope and execution
identity. Old Schema 1 document bytes/hash inputs remain valid.
The 12 existing shared/engineering descriptor hashes were compared before and
after extraction and are unchanged in the same dependency environment. Vesryn's
local Dagger transport already binds contracts to complete package/module source
identities. Changed source invalidates those source-bound selections under the
existing rule; old bindings are rejected rather than silently retargeted.

Development `tool.uv.sources` overrides explicitly select the adjacent Tool Runtime
checkout in these two consumers. They are development inputs, not wheel metadata.
Before a consumer release, replace the override with the accepted immutable
component reference and regenerate its lock; do not release an adjacent path pin.
engineering-ci's optional Harness pin must likewise move to the integrated Vesryn
candidate before distribution; testing only its older pinned Harness is insufficient.
The existing dependency scanner intentionally rejects these local path sources.
Its production policy is unchanged; development-path rejection is explicitly
asserted by the consumer regression test. Production security readiness requires
the immutable references, not a waiver for these paths.

For local shared-tool Dagger development, pass both existing Vesryn source/module
inputs and `--tool-runtime-source <authorized-runtime-checkout>` to Vesryn's
Workflow CLI/Registry. The optional Python `tool_runtime_source` argument and
Dagger `tool_runtime_source` Directory are forwarded explicitly. The module mounts
the selected package at the path declared by the development lock. Its contents
are checked on the host before/after invocation. No neighboring source is inferred.

The logs repo/API is unchanged. Additional safe tool events are independent of
existing workflow observations and readable history.
