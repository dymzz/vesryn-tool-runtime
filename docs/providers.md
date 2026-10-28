# Provider and Dagger integration

Use the existing `vesryn.adapters` entry-point group. The host explicitly chooses
a name, and `provider(name, root)` loads that one Catalog. Domain Catalogs declare
`provider_name` matching the entry-point name. `Catalog.merge`/`compose` retains
each tool's Provider identity. Duplicate tool ownership is rejected before merge.
Vesryn's built-in catalogs declare their existing identities: `tooling` for
evaluation tools (including their explicit Dagger transport), and `unified` for
shared CLI profiles. `Catalog.provider_for(tool_id)` supplies the identity when
freezing a Binding from that same explicitly assembled Catalog.

`Catalog.search` and `Catalog.page` operate on registered ToolSpecs, with bounded,
deterministic results and scope filtering before ranking or pagination. Page
summaries precede opt-in full contracts. Selection never grants permissions; a
mutable host constraint is reevaluated at dispatch.

`ComposedCatalog` exposes ordered record traversal and lookup. It does not
implement ranked group/member discovery or turn a `ToolAccess` record into an
executable Adapter or Binding. The host explicitly supplies an Adapter, scope and
available dependencies for invocation.

Dagger TypeDef mapping is optional in `dagger_discovery`. Remote modules require
explicit immutable source identity and an exposure allowlist; unsupported or
recursive types require the existing domain mapper. No Dagger Python SDK is a
base dependency, and mapped ToolSpecs still need a host-supplied Adapter.

Vesryn's DaggerAdapter stays in Vesryn, including source/module identity checks,
explicit package/module inputs and existing failure behavior. engineering-ci's
ChecksAdapter and Dagger check graph stay in engineering-ci. A ready batch is
dispatched as a whole to the original Adapter; the generic runtime does not launch
an execution backend per tool. Existing backend-specific grouping is preserved.
