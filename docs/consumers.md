# Consumer migration

## Current consumers and integration boundaries

The following is a source-level inventory at the fixed revisions cited below, not
a claim that the latest Tool Runtime release has been adopted or that all
consumer combinations have passed compatibility tests.

- [Vesryn at f3446915](https://github.com/dymzz/vesryn/blob/f3446915e64f0a2f6d8a997e3aee6fbfbbde77b6/pyproject.toml)
  declares `vesryn-tool-runtime==0.1.0` at a fixed Git revision and consumes
  the independently packaged Workflow and Log components.
  [Workflow at 735e2725](https://github.com/dymzz/vesryn-workflow/blob/735e2725584cf4cc1224a995c9b4fa3fe8f8181b/pyproject.toml)
  also declares Tool Runtime 0.1.0, with its own fixed source. The Runtime
  0.4.0 release is not evidence that either consumer has migrated to it.
  Evaluate the actual affected interfaces and resolved dependency closure
  together where required, using the existing consumer entry points.
- [Engineering CI at e5dddf94](https://github.com/dymzz/engineering-ci/blob/e5dddf942ff93fd55daeeb8b199ed754ca0cf0b8/docs/architecture/repository-overview.md#依赖与跨仓库关系)
  no longer uses the former Python Check Provider/Adapter or compatibility
  Workflow integration. Its
  [package manifest](https://github.com/dymzz/engineering-ci/blob/e5dddf942ff93fd55daeeb8b199ed754ca0cf0b8/pyproject.toml)
  does not declare Tool Runtime or Log as a runtime dependency. Its current
  [public integration interfaces](https://github.com/dymzz/engineering-ci/blob/e5dddf942ff93fd55daeeb8b199ed754ca0cf0b8/docs/delivery/public-components.md)
  include native Dagger functions, reusable GitHub Actions workflows and
  supported CLI operations. Engineering CI may directly use Tool Runtime for
  actual tool contracts/invocation, and Log for CI event recording, where
  needed; it must not directly or transitively depend on Vesryn or Workflow.
  Adopting a tool does not require restoring the retired Provider.
- Runtime's own
  [package manifest](https://github.com/dymzz/vesryn-tool-runtime/blob/354fbde13e146760c354a2cc6782756b011ef2e7/pyproject.toml)
  declares Log as its event-recording dependency, not Vesryn, Workflow or
  Engineering CI. The
  [EventSink contract](https://github.com/dymzz/vesryn-log/blob/ecda07fd167b0bd47008b9e6748acb94d730c114/docs/python-api.md)
  remains distinct from execution outcomes and release decisions. Runtime
  also consumes Engineering CI's
  [fixed reusable CI workflow](https://github.com/dymzz/vesryn-tool-runtime/blob/354fbde13e146760c354a2cc6782756b011ef2e7/.github/workflows/ci.yml);
  that CI relationship is not a Python package dependency.

For current integrations, consult the actual consumer's configuration,
[public Python API](python-api.md), [tool assets](tool-assets.md) and
[release readiness](delivery/release-readiness.md). Use explicitly authorized
development source overrides only as development inputs. Before a formal
consumer release, verify immutable references, the resolved lock, actual
public contracts and applicable consumer execution. Python API shape
comparison is complementary to CLI, schema, SQLite, Dagger and runtime
behavior verification. An independent tool adoption or candidate smoke
test does not authorize a release.

The cross-repository engineering adoption task
[engineering-ci#162 C](https://github.com/dymzz/engineering-ci/issues/162)
references these boundaries. Runtime retains its tool contract/asset
responsibility; the consuming project owns its configuration and release
acceptance. See [Runtime #13](https://github.com/dymzz/vesryn-tool-runtime/issues/13)
for the existing managed-policy integration and
[Vesryn #30](https://github.com/dymzz/vesryn/issues/30) for actual shared-tool
asset consumption.

## Historical extraction and development integration

The following paragraphs retain the earlier migration record for provenance.
They describe the former integration at the time of the extraction, **not
current Engineering CI or latest Vesryn/Workflow installation instructions**.
In particular, the former Check Provider/Adapter, compatibility Workflow
imports, optional Harness pin and adjacent development checkout examples
must not be restored or assumed current solely from this record.

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
