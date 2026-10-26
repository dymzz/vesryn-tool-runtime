# Design Document: Issue #43 Documentation Cleanup and Reset

## 1. Intent and Why

Over successive feature deliveries (Issues #6, #7, #8, #16, #17, #18, #19, #20, #27, #29, #32, #33), `vesryn-tool-runtime` has significantly evolved its core architecture:
- Historical individual JSON asset definition documents (`shared_assets/*.json`) and the legacy loader (`shared_definitions.py`) were completely retired and replaced by bundled record seeds (`record_seed.sql` + `bundled_records()`) and SQLite-backed store persistence (`open_record_store`) in Issue #32.
- Host tool registration, synchronization, and local environments were formalized into `host_tools.py` with SQLite-backed facts and an Agent-facing `tools.json` list in Issue #33.
- Discovery models transitioned to a six-table normalized SQLite schema with strict DDL enforcement and progressive disclosure contracts.

However, `docs/` accumulated legacy documentation, retired API descriptions, redundant task delivery reports (`docs/tasks/vesryn-tool-runtime/*.md`), and outdated public API documentation (e.g., `docs/python-api.md` still marked as 0.1.0).

Issue #43 establishes a clean documentation baseline matching the actual codebase, public interfaces, and schemas. It ensures public docs are free of deprecated patterns, dead links, and redundant task logs without maintaining legacy artifacts as a migration burden.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Delete Retired Documents**:
  - Remove `docs/shared-definitions.md` (retired JSON declaration format and loader documentation).
  - Remove `docs/assets/` (`native-workflow.md`, `oci.md`, `python-cli.md`, `security.md`) after consolidating their valid behavioral contracts into core docs.
  - Remove all 12 historical task files in `docs/tasks/vesryn-tool-runtime/`.
  - Remove one-off historical delivery snapshots `docs/delivery/tool-runtime-0.1.0.md` and `docs/delivery/tr-001-binding-admission.md`.
  - Clean redundant derivative verification JSON files while preserving unique execution evidence.
- **Consolidate Valid Contracts**:
  - Consolidate platform and ABI semantics (glibc `gnu` vs. musl `musl`, manylinux compatibility, libc constraints) into `docs/tool-assets.md`. Tool versions and hashes defer to the authoritative bundled seed (`record_seed.sql`).
  - Consolidate OCI distribution boundaries (Dagger execution boundary, container runtimes, Linux target constraints) into `docs/tool-assets.md`.
  - Document the current host-tool lifecycle in `docs/tool-assets.md` or dedicated core section: `default_tools()`, `prepare_tool()`, `refresh_tools()`, `uninstall_tool()`, shared data-root resolution (`%LOCALAPPDATA%\vesryn\data` on Windows, `$XDG_DATA_HOME|~/.local/share/vesryn/data` elsewhere), SQLite registration facts (`tools.sqlite3`), and the generated Agent-facing list (`tools.json`).
  - Retain real operational behaviors of host tools: explicit invocation requirement, SQLite commit vs. `tools.json` update are not cross-file atomic, `registered_not_synced` status recoverable via `refresh_tools()`, and external tool reuse does not imply source verified.
  - Update `docs/discovery-contracts.md` with correct resource path references (`src/vesryn_tool_runtime/record_schema.sql` and `record_seed.sql`) and live seed registration semantics (`bundled_records()`, `open_record_store()`).
  - Document remaining compatibility entry points (specifically `legacy_preparation_definitions()`, which remains exported in `__all__` and used by `host_tools.py`) according to their actual current usage, without preserving retired documentation solely because a compatibility function exists.
- **Update Core Public Documentation**:
  - Update `docs/python-api.md` to describe the currently supported public API groups, essential behavioral contracts, failure semantics, and usage examples. Validate exported entry points against the current `__all__`. Leave exhaustive symbol-level API Reference generation to the subsequent Sphinx AutoAPI integration.
  - Update `docs/consumers.md` to remove obsolete 0.1.0 dependency assumptions and document current integration requirements.
  - Preserve `docs/delivery/release-readiness.md` as the authoritative C1–C8 acceptance criteria.
  - Preserve `docs/verification/tr-asset-ci-01d-semgrep/` as the original Dagger execution capture. Retain `tr-asset-ci-01d.json` only where its distinct historical verification claims remain necessary, without treating it as an equivalent raw execution record.
- **Maintain Link Integrity**:
  - Overhaul `README.md` and `docs/README.md` to link only to active, valid documents.
  - Verify that `AGENTS.md` references (`docs/README.md`, `docs/delivery/release-readiness.md`) remain fully valid.
  - Ensure zero broken relative markdown links across the entire repository.

### Non-Goals
- No changes to product code under `src/vesryn_tool_runtime/` or unit tests under `tests/`.
- No exhaustive manual symbol-by-symbol API reference writing in `docs/python-api.md` (Sphinx AutoAPI will generate symbol-level references in a follow-up phase).
- No introduction of external documentation generators in P0; documentation tooling integration will follow on top of this clean baseline in subsequent issues.
- No regeneration of verification evidence that already exists.

### Anti-Goals
- Do NOT delete the raw Dagger execution evidence in `docs/verification/tr-asset-ci-01d-semgrep/`.
- Do NOT treat `tr-asset-ci-01d.json` as equivalent to the raw execution capture in `tr-asset-ci-01d-semgrep/`.
- Do NOT delete `docs/delivery/release-readiness.md` (active governance standard).
- Do NOT create a `docs/archive/` folder; historical PR and delivery notes are permanently preserved in Git history and PR records.
- Do NOT create a separate cleanup report file (the PR description will succinctly summarize deletion and consolidation rationales).

---

## 3. Constraints

- Adhere strictly to the boundaries specified in `AGENTS.md` (contracts, generic tool runtime, no imports of Vesryn/engineering-ci).
- All relative file links in markdown documents must resolve to existing files.
- The work must be validated with an automated link verification check and test suite execution (`pytest`, `ruff`).

---

## 4. Approaches Considered

### Approach 1: Strict Cleanup & Core Consolidation (Selected)
- Delete all retired/redundant task notes and retired shared-definition files.
- Merge unique behavioral contracts (ABI tags, OCI constraints, host-tools lifecycle) into core documentation.
- Update `python-api.md` with supported API groups, contracts, and examples aligned with `__all__`.
- Clean up navigation in `README.md` and `docs/README.md`.
- *Rationale*: Directly meets Issue #43 criteria; leaves the documentation repository clean, maintainable, and free of obsolete clutter.

### Approach 2: Archive Segregation (Rejected)
- Move retired docs and task reports into `docs/archive/` with deprecation disclaimers.
- *Reason for Rejection*: Violates Issue #43 directive ("不把旧 docs/ 原样保留为后续迁移基线" and "直接删除：失效接口说明、冗余文档、一次性任务总结等不再承担现行职责的文件").

---

## 5. Detailed Specification of Changes

### 5.1 File Deletions
1. `docs/shared-definitions.md`
2. `docs/assets/native-workflow.md`
3. `docs/assets/oci.md`
4. `docs/assets/python-cli.md`
5. `docs/assets/security.md`
6. `docs/tasks/vesryn-tool-runtime/P0-aria2-native-assets.md`
7. `docs/tasks/vesryn-tool-runtime/P0-local-tool-assets.md`
8. `docs/tasks/vesryn-tool-runtime/P0-tool-asset-resolution.md`
9. `docs/tasks/vesryn-tool-runtime/P1-asset-selection-backend-migration.md`
10. `docs/tasks/vesryn-tool-runtime/P1-discovery-field-contract.md`
11. `docs/tasks/vesryn-tool-runtime/P1-native-workflow-shared-assets.md`
12. `docs/tasks/vesryn-tool-runtime/P1-oci-shared-assets.md`
13. `docs/tasks/vesryn-tool-runtime/P1-python-asset-platform-compatibility.md`
14. `docs/tasks/vesryn-tool-runtime/P1-python-cli-shared-assets.md`
15. `docs/tasks/vesryn-tool-runtime/P1-security-scanner-shared-assets.md`
16. `docs/tasks/vesryn-tool-runtime/P1-shared-asset-registration-foundation.md`
17. `docs/tasks/vesryn-tool-runtime/P1-unified-tool-registration.md`
18. `docs/delivery/tool-runtime-0.1.0.md`
19. `docs/delivery/tr-001-binding-admission.md`
20. `docs/verification/contract-hashes.json`
21. `docs/verification/results.json`
22. `docs/verification/tr-asset-01.json`
23. `docs/verification/tr-asset-01a.json`
24. `docs/verification/tr-asset-01b.json`
25. `docs/verification/tr-asset-01c.json`
26. `docs/verification/tr-asset-ci-01b.json`

### 5.2 Evidence Retained
1. `docs/verification/tr-asset-ci-01d-semgrep/`: Original native Dagger execution capture:
   - `README.md`
   - `dagger.stderr.log`
   - `dagger.stdout.json`
   - `process.json`
   - `query.graphql`
   - `sha256.json`
   - `.gitattributes`
2. `docs/verification/tr-asset-ci-01d.json`: Retained only for its distinct historical verification claims; distinguished from raw execution records.

### 5.3 File Updates and Consolidations

#### `docs/tool-assets.md`
- Incorporate platform & ABI semantics previously in `docs/assets/python-cli.md`:
  - Enforce `gnu` vs `musl` on Linux targets.
  - Explain why `manylinux` wheels require `abi: "gnu"` and `musllinux` wheels require `abi: "musl"`.
  - State that an unconstrained Linux target does not match libc-specific binaries.
- Incorporate OCI execution boundaries previously in `docs/assets/oci.md`:
  - Clarify that OCI distributions are declaration-only in `vesryn-tool-runtime`; container execution and layer caching remain natively with Dagger (`Container.from(image)`).
  - Pinned platform manifest digest vs. multi-arch index digest rules.
  - Linux-only restriction for OCI tools (`linux/x86_64`, `linux/aarch64`).
- Document Host Tool Lifecycle (from Issue #33):
  - `default_tools()`: bundled seed tool profiles.
  - `prepare_tool()`: explicit local tool preparation and installation.
  - `refresh_tools()`: rebuilds `tools.json` from SQLite facts.
  - `uninstall_tool()`: clean removal and unregistration.
  - User data-root resolution (`%LOCALAPPDATA%\vesryn\data` on Windows, `$XDG_DATA_HOME|~/.local/share/vesryn/data` elsewhere).
  - Two stores: `tools.sqlite3` (registration facts) and `tools.json` (Agent-facing list).
  - Operational semantics: non-cross-file atomic commits, `registered_not_synced` status and recovery via `refresh_tools()`, and external tool reuse not establishing verified source.
- Document compatibility entry points:
  - `legacy_preparation_definitions()`: retained compatibility bridge used by `host_tools.py` to bridge asset records to preparation format.

#### `docs/discovery-contracts.md`
- Fix path to schema DDL: clarify that schema DDL and record seed are shipped as package resources (`src/vesryn_tool_runtime/record_schema.sql` and `record_seed.sql`).
- Update live registration section: document the public loading flow (`bundled_records()`, `open_record_store()`, `compose_catalog()`).

#### `docs/python-api.md`
- Remove the "0.1.0" header and focus on currently supported public API groups, essential behavioral contracts, failure semantics, and usage examples.
- Validate all exported entry points against `__all__`:
  - Tool Contracts & Invocation (`ToolSpec`, `ToolResult`, `Invocation`, `ExecutionContext`, `ToolAdapter`, `ToolRuntime`, `invoke_tool`, `checked_result`, `DispatchReceipt`)
  - Catalog & Providers (`Catalog`, `compose`, `compose_catalog`, `ComposedCatalog`, `provider`, `DiscoveryScope`)
  - Selection Binding (`create_binding`, `verify_binding`, `canonical_binding`, `verify_document`, `SELECTION_BINDING`)
  - Discovery Records & Store (`ToolAsset`, `ToolGroup`, `ToolAccess`, `GroupMember`, `Platform`, `ToolAssetVersion`, `open_record_store`, `bundled_records`, `RecordError`, `DiscoveryQuery`, `DiscoveryPage`, `DiscoveryDiagnostic`, `DiscoveryErrorDocument`)
  - Asset Contracts & Backends (`AssetDefinition`, `AssetRelease`, `AssetTarget`, `AssetSelection`, `AssetPolicy`, `AssetIndex`, `AssetReceipt`, `AssetFile`, `asset_root`, `native_asset_directory`, `Aria2NativeBackend`, `Aria2Source`, `NativeAssetDelivery`, `UvToolBackend`, `UvLock`, `AssetError`)
  - Host Tools Management (`prepare_tool`, `refresh_tools`, `uninstall_tool`, `default_tools`, `user_data_root`, `HostToolError`)
  - Compatibility Bridge (`legacy_preparation_definitions`)
- Note that exhaustive symbol-level API Reference generation is left to the subsequent Sphinx AutoAPI integration.

#### `docs/consumers.md`
- Remove obsolete statement that "Vesryn depends on vesryn-tool-runtime==0.1.0".
- Document current consumption patterns for Vesryn and engineering-ci.

#### `README.md`
- Update document links to remove references to `docs/shared-definitions.md` and `docs/tasks/...`.
- Link to live discovery contracts, Python API, tool asset contracts, and release readiness.

#### `docs/README.md`
- Clean index listing only live documents:
  - Quickstart (`quickstart.md`)
  - Public Python API (`python-api.md`)
  - Architecture and Ownership (`architecture.md`)
  - Failure and Observation Semantics (`failure-semantics.md`)
  - Provider and Dagger Integration (`providers.md`)
  - Discovery Field Contracts (`discovery-contracts.md`)
  - CLI Asset Contracts & Host Tools (`tool-assets.md`)
  - Native Asset Acquisition (`native-assets.md`)
  - uv Tool Environments (`uv-tool-assets.md`)
  - Dagger Package Delivery (`dagger.md`)
  - Consumer Integration (`consumers.md`)
  - Release Readiness Criteria (`delivery/release-readiness.md`)
  - Changelog (`changelog.md`)
  - Verification Evidence (`verification/tr-asset-ci-01d-semgrep/README.md`)

---

## 6. What is Left to the Builder

- Exact sentence-level wording in the consolidated sections of `docs/tool-assets.md`, `docs/python-api.md`, `docs/discovery-contracts.md`, and `docs/consumers.md`.
- Formatting adjustments in tables and code snippets in the updated documentation files.
- Execution of link verification and test suite checks.
