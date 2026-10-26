# Changelog

## 0.1.0 — extraction candidate

- Migrate authoritative tool contracts, Registry/discovery and Schema validation
  from the current Vesryn worktree, preserving existing tool contract digests.
- Extract engineering-ci Selection Binding Schema 1 identity/integrity checks;
  retain consumer-owned workflow associations and recovery.
- Add independent single/batch invocation and explicit EventSink observations.
- Integrate both consumers through compatibility exports and delegated dispatch.
- No formal release or tag is created. Read readiness assessment
  for verified paths and remaining publication work.

## 0.2.0 — local tool assets

- Integrate A/B/C through the same Catalog, receipt and index, with independent
  multi-version uv environments and verified native payloads. See the
  joint acceptance and release assessment.
- Require current AssetPolicy on uv lock/preparation/inspection/command, retain a
  published environment's frozen lock and reuse it without rebuilding after cache
  removal. This refines the unreleased #7 prototype; released 0.1 interfaces and
  Binding Schema 1 remain compatible.

- Add explicit aria2 native-asset acquisition with pinned downloader provenance,
  verified offline reuse, safe staged extraction and immutable version directories.
  Reuse the common receipt/index and existing File/Directory transport; include
  reviewed OSV/Hyperfine definitions. See [native assets](native-assets.md) and
  issue #8 delivery.

- Add independent CLI asset definitions/target and version-policy resolution to the
  existing Catalog, plus frozen selection snapshots and a shared, integrity-checked
  local backend receipt/index boundary. Preserve tool/Binding hashes and admission;
  no downloader or installer is introduced. See [asset contracts](tool-assets.md)
  and issue #6 delivery.

- Widen the Log requirement to the compatible `>=0.1.0,<0.2.0` range while preserving the
  existing immutable development source and lock baseline. Tool contracts and Schema 1 are
  unchanged, and the delivered 0.1.0 wheel keeps its recorded SHA-256 until a new wheel is
  built. The binding and admission compatibility conclusion, and the real `JsonlSink`
  regression behind it, are recorded in
  TR-001.

- Add a thin uv adapter (UvToolBackend) that delegates resolution, download and environments to uv, with per-artifact environments, shared receipts and a hashed Linux lock description. Acquisition and execution stay separately permitted. See [uv tool environments](uv-tool-assets.md).

## 0.3.0 — shared CI tool asset declarations

- Add the shared asset definition foundation for TR-ASSET-CI-01A (issue #16): a strict
  shared-asset-definitions document format, a bundled per-group data directory and the
  thin `shared_definition_documents`/`load_shared_definitions`/`register_shared_definitions`
  entries over the existing Catalog. Tool/asset identity, Provider, Scope and Binding
  semantics are unchanged; no second registry, installer or implicit loading is added.
  See shared asset definitions and the
  issue #16 delivery.

- Bundle eleven CI program assets in four independently readable groups: Vulture,
  Pyright, deptry, Pylint, OSV-Scanner, actionlint, ShellCheck, zizmor, Semgrep,
  Lychee and Trivy. These are declarations, not automatic installation, executable
  bindings or required CI gates. Gitleaks remains deferred. The documentation index
  links each group's targets, provenance, preparation evidence and limitations.
- Correct deptry's existing manylinux x86_64 wheel declaration to Linux x86_64.
  Existing frozen selections remain readable; consumers regenerate the selection
  and lock identity rather than rewriting historical records. The artifact bytes
  and hashed requirement set are unchanged.
- Keep the offline seed example usable when additional groups ship, enforce the
  documented JSON object/list shapes, and correct OCI examples to the public
  AssetPolicy/AssetTarget APIs and per-platform manifest sources.
- Existing ToolSpec identities, Binding Schema 1, execution admission and uv/native
  backends remain compatible. actionlint, ShellCheck, zizmor and Trivy retain
  explicit example associations pending formal consumer check contracts. OCI
  installation is delegated to Dagger; no Runtime OCI installer is added.

## 0.3.1 — Linux asset target corrections

- Publish the deptry GNU-libc declaration and libc-aware uv lock resolution
  from issue #29; the publisher artifact URL and SHA-256 remain unchanged.
- Supply the known GNU target in the Python asset consumption example. The
  uv preparation example derives its local Linux libc and rejects an unknown
  value; its separate container lock explicitly targets GNU Linux.
- Retain independently traceable Semgrep Dagger version evidence from PR #30.
  This proves one pinned-image version call, not a project scan.
- Synchronize package metadata, the existing Dagger wheel output and installed
  package checks to 0.3.1. See the [release evidence](https://github.com/dymzz/vesryn-tool-runtime/releases/tag/v0.3.1)
  for the #12 acceptance, original preparation records and consumer reproduction.

### Included discovery prototype

The following summary-model code is included from the existing main baseline;
its separate #14 acceptance is not part of this asset-consumer patch.

- Add the discovery field contract foundation for TR-DISC-01A (issue #27): the
  single field authority for #14's grouped discovery and access entry queries —
  strict-versioned documents (query, page, group/candidate/access-entry
  summaries, contract detail, diagnostics, errors), the composed
  `<catalog_ref>:<tool_id>@<entry_key>` access identity, separated fact-state
  enums with safe defaults, disclosure-bounded summaries and canonical JSON
  Schemas. No retrieval, ranking, admission, binding-management or health
  algorithm is introduced. See
  [discovery field contracts](discovery-contracts.md) and the
  issue #27 delivery.
## Unreleased

- Redo the discovery record foundation for the reopened issue #27: the three
  logical records — ToolAsset, ToolGroup, ToolAccess — on six constrained
  SQLite tables; the frozen DDL and seed ship as package resources
  (`record_schema.sql`, `record_seed.sql`) read via `importlib.resources`,
  the writable store location is always caller-supplied, releases carry
  platform ABI and interpreter constraints, and the parity check compares
  the full DDL, not column names. Foreign keys, enum CHECKs, uniqueness and NOT NULL
  constraints live in the schema itself; member summaries and aliases are
  member-level only; every entry carries its own method/target/contract; no
  asset_id column exists. Records serialize with strict round trips and the
  query layer carries their documents directly, replacing the five PR #28
  deviations (including the forced access_id composition); old formats are
  explicitly unsupported with no compatibility layer. See
  [discovery contracts](discovery-contracts.md) and the
  issue #27 redo record.

## Unreleased (TR-DISC-01B)

- Migrate live registration onto the #27 record foundation (issue #32): the
  bundled seed becomes the single live declaration (20 tools — the #27 seeds
  plus ripgrep, hyperfine, osv-scanner, actionlint, shellcheck, zizmor,
  semgrep, lychee, pyright, deptry, pylint and vulture's still-used 2.14),
  the shared_assets JSON documents and their loader are retired, and
  Catalog.register_asset registers tool keys without a capability
  prerequisite. New public chain: bundled_records (pure seed read),
  RecordStore.put_records (atomic batch with idempotent/conflict semantics),
  compose_catalog/ComposedCatalog (explicit composition and ordered
  traversal, missing tool vs no-entry distinguished), plus a temporary
  read-only bridge (legacy_preparation_definitions) for the old preparation
  callers that #33 removes. See
  discovery contracts and the
  issue #32 delivery.
