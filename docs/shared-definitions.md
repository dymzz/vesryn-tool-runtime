# Shared asset definitions: reads, explicit assembly and group ownership

This is the public handoff for [issue #16](https://github.com/dymzz/vesryn-tool-runtime/issues/16),
TR-ASSET-CI-01A / 12-A, child of [issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12).
Baseline: released 0.2.0, commit `306912152545e442a698b8b0c1f3188ce0fc09c1`. These APIs are
working-tree additions after that baseline; they are not in the released 0.2.0 wheel.
The referenced local task book was absent from this checkout; the delivery record was
created from the fetched issue #16 body.

This task adds the minimal public read/explicit-assembly entry for shared asset
definitions plus the identity mapping rules, so sub-tasks B/C/D/E [#17–#20] only add
their own definition data files. It does not add a second registry, another
Tool/AssetSpec kind, an installer, implicit Provider loading, or any ToolGroup/Access
query (those are [#14](https://github.com/dymzz/vesryn-tool-runtime/issues/14) and
[#15](https://github.com/dymzz/vesryn-tool-runtime/issues/15)).

## Public signatures

All symbols below are exported from `vesryn_tool_runtime`:

```python
SharedAssetDefinition(definition: AssetDefinition, tools)  # frozen record
SharedAssetDefinition.definition -> AssetDefinition
SharedAssetDefinition.tools -> tuple[str, ...]
shared_definition_documents() -> tuple[str, ...]
load_shared_definitions(source) -> tuple[SharedAssetDefinition, ...]
register_shared_definitions(catalog, definitions) -> None
```

- `shared_definition_documents()` lists bundled shared-definition document names in
  sorted order. Listing reads no document content and loads no Provider.
- `load_shared_definitions(source)` reads exactly one shared-definitions document.
  `source` is either a bundled document name (which takes precedence over an equally
  named filesystem path) or a filesystem path (`str`/`Path`). Loading an in-memory
  mapping is intentionally not provided; write a bounded document and read it, or
  coordinate a common-entry change with this task/#12.
- `register_shared_definitions(catalog, definitions)` associates loaded records with
  a Catalog. `definitions` is the tuple from `load_shared_definitions` (a single
  record is also accepted). It returns existing `AssetDefinition` objects to
  `Catalog.register_asset`; nothing else is registered, installed or persisted.

## Document format

A shared-definitions document is one bounded JSON object (2 MiB limit, duplicate
fields and non-finite numbers rejected by the existing `documents` reader), with
exactly these top-level fields:

```json
{
  "schema_version": 1,
  "kind": "shared-asset-definitions",
  "assets": [
    {
      "asset_id": "hyperfine",
      "catalog_revision": "official-2026-10-23",
      "tools": ["example.benchmark"],
      "releases": [
        {
          "version": "2.0.0", "distribution": "native", "backend": "aria2",
          "source": "https://…", "sha256": "…", "entrypoint": "hyperfine.exe",
          "os": "windows", "arch": "x86_64", "abi": "msvc"
        }
      ]
    }
  ]
}
```

- `assets` is a non-empty list; each entry has exactly `asset_id`, `catalog_revision`,
  `tools` and `releases`.
- `releases` entries are validated as existing `AssetRelease` documents; all existing
  release reason codes (`mutable_version`, `invalid_digest`, `invalid_source`,
  `invalid_backend`, `invalid_target`, `invalid_requirement`, `invalid_definition`)
  are preserved unchanged.
- `tools` is a non-empty list of unique tool IDs matching the existing tool ID
  pattern (`domain.operation`, lowercase). It declares which **existing capabilities**
  the asset serves; it never creates or modifies a capability.
- The same `asset_id` twice in one document is rejected as `conflicting_asset` at
  read time. Across documents, an identical re-declaration of the same asset is
  idempotent at registration, while differing content for the same `asset_id` keeps
  the existing `conflicting_asset` behavior of `Catalog.register_asset`.
- Unknown fields, wrong `schema_version`/`kind`, empty `assets`, or unreadable JSON
  are rejected (`invalid_definition`, or the existing `WorkflowError` for unreadable
  documents). There is no "unknown definition" fallback that invents an asset.

## Identity mapping rules

- `ToolSpec.tool_id` remains the callable capability identity; `AssetDefinition.asset_id`
  remains the program asset identity. Version, platform, entrypoint and
  install-location changes never reassign either ID.
- One asset can be declared to serve many capabilities; one capability is associated
  with at most one asset (the existing `Catalog.register_asset` invariant).
- New asset IDs use the program's canonical lowercase name (for example `vulture`,
  `pyright`, `trivy`), matching the delivered `hyperfine`/`osv-scanner` style.
  Existing delivered IDs (`cli.ripgrep`, `cli.pytest`, `hyperfine`, `osv-scanner`)
  stay exactly as they are.
- Contract Provider, artifact source, preparation backend, execution environment and
  artifact identity stay separately expressed by the existing fields. A backend
  identifier is never a capability Provider, and a definition never states backend
  readiness or install state.

## Read and assembly guarantees

- Reading shared definitions requires no ECI checkout, no Adapter, no consumer
  project environment and no Catalog. Ordinary reads perform no installation,
  network access, subprocess or write, and grant no execution permission.
- Assembly reuses `Catalog.register_asset`: every associated capability must already
  be registered with its real `ToolSpec` and adapter. An unimplemented capability
  cannot be masqueraded by an empty Schema, an example ID or `Adapter=None`;
  association with a missing capability is rejected as `unregistered_tool`.
- Records apply in order; the first conflict raises its existing `AssetError` while
  associations already applied remain. Pure capabilities without an asset keep the
  existing `unregistered_asset` answer from `asset_for`.
- Existing IDs, Provider identity, Scope/Binding semantics, admission and selection
  behavior are unchanged by these entries; the common compatibility test below pins
  this.

## Bundled data and packaging rule

Shared definition data lives in `src/vesryn_tool_runtime/shared_assets/`, ships
inside the wheel, and is enumerated by `shared_definition_documents()`. There is no
central manifest: adding a group's `.json` file to this directory requires no change
to `__init__.py`, `pyproject.toml`, a manifest, or any common test file. A bundled
document name resolves to the shipped document, never to an equally named neighbor
file. One read from one installed artifact is the packaging proof; no repeated
installation matrix is required.

The bundled seed `examples.json` carries the already-verified definitions —
ripgrep 15.2.0 (Windows aarch64/MSVC) serving `example.search`, and hyperfine
2.0.0/1.20.0 (Windows/Linux x86_64) serving `example.benchmark` — as verified on
2026-10-23 by the [#6](https://github.com/dymzz/vesryn-tool-runtime/issues/6) and
[#8](https://github.com/dymzz/vesryn-tool-runtime/issues/8) deliveries. Their
`example.*` associations are example capability identities, not formal callable
capabilities; consumers assemble only the documents whose capabilities they
actually implement.

Run the offline sample with `python examples/shared_definitions.py` (installed
candidate package, or this checkout's `src` on `PYTHONPATH`):

```python
records = [
    r for name in shared_definition_documents() for r in load_shared_definitions(name)
]
tools = Catalog()  # a consumer's real capabilities first
tools.register(ToolSpec("example.benchmark", {}, {}, effect="check"), adapter)
register_shared_definitions(tools, records)
view = tools.asset_view("example.benchmark", target=target, policy=policy)
```

## Path ownership for B/C/D/E

Each sub-task owns its files exclusively. Nobody co-edits another group's files or
the common files; a needed common-entry change goes back to this task/#12 once,
not into four branches.

| Group | Definition data (exclusive) | Test file (exclusive) | Document (exclusive) |
| --- | --- | --- | --- |
| B — Python CLI ([#17](https://github.com/dymzz/vesryn-tool-runtime/issues/17)) | `src/vesryn_tool_runtime/shared_assets/python.json` | `tests/test_shared_assets_python.py` | `docs/assets/python-cli.md` |
| C — native/workflow ([#18](https://github.com/dymzz/vesryn-tool-runtime/issues/18)) | `src/vesryn_tool_runtime/shared_assets/native.json` | `tests/test_shared_assets_native.py` | `docs/assets/native-workflow.md` |
| D — OCI ([#19](https://github.com/dymzz/vesryn-tool-runtime/issues/19)) | `src/vesryn_tool_runtime/shared_assets/oci.json` | `tests/test_shared_assets_oci.py` | `docs/assets/oci.md` |
| E — Trivy/Gitleaks ([#20](https://github.com/dymzz/vesryn-tool-runtime/issues/20)) | `src/vesryn_tool_runtime/shared_assets/security.json` | `tests/test_shared_assets_security.py` | `docs/assets/security.md` |

Common files owned by this task (and, after merge, by the parent #12 integrator):
`src/vesryn_tool_runtime/__init__.py`, `src/vesryn_tool_runtime/shared_definitions.py`,
`pyproject.toml`, `tests/test_shared_definitions.py`, `examples/shared_definitions.py`,
`docs/shared-definitions.md`, `docs/README.md`, `docs/changelog.md` and the bundled
seed `shared_assets/examples.json`. Group delivery records continue to use the
existing `docs/tasks/vesryn-tool-runtime/P1-*.md` pattern.

Group test files may load their own data file and exercise their own declarations;
they reference the common compatibility test's evidence instead of copying or
rerunning it.

## Common compatibility test and evidence

`tests/test_shared_definitions.py` is the common compatibility test verified by this
task. B/C/D/E cite its passing evidence instead of duplicating it. It covers:

- Pure reads without a Catalog/adapter/consumer environment, with no filesystem
  side effects, and bundled-name precedence over equally named local files.
- Explicit assembly reusing `register_asset`; unregistered capability, conflicting
  re-association, pure capability without asset, non-Catalog and non-record inputs
  keeping their existing explicit reasons.
- One asset serving many capabilities; `artifact_id` sharing across capabilities;
  version/platform changes not reassigning asset IDs; idempotent identical
  re-declaration across documents.
- Provider identity and Scope filtering unchanged by assembly.
- Unknown/invalid documents and release-level reasons staying explicit.
- The bundled seed loading as examples, not formal callable capabilities.

Verified results are recorded in the
[issue #16 delivery record](tasks/vesryn-tool-runtime/P1-shared-asset-registration-foundation.md).
