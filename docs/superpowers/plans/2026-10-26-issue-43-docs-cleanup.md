# Issue #43 Documentation Cleanup and Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up retired, obsolete, and redundant documentation in `vesryn-tool-runtime`, consolidate valid behavioral contracts into core docs, and align public documentation with the current codebase, schemas, and public API.

**Architecture:** Documentation restructuring with contract consolidation: migrate valid ABI/OCI and Host Tool lifecycle contracts into `tool-assets.md`, correct schema resource paths in `discovery-contracts.md`, modernize `python-api.md` and `consumers.md`, remove 26 retired/task/snapshot documents, and update root and index links with strict automated link verification.

**Tech Stack:** Markdown, Python 3.14+, pytest, ruff, git.

**Spec:** [`docs/superpowers/specs/2026-10-26-issue-43-docs-cleanup-design.md`](../specs/2026-10-26-issue-43-docs-cleanup-design.md)

## Global Constraints

- Never import Vesryn, engineering-ci, workflow scheduling/checkpoints or logging storage.
- Public technical documentation belongs under `docs/`.
- Relative links in markdown files must resolve to existing files; zero broken links allowed.
- Do NOT delete the raw Dagger execution evidence in `docs/verification/tr-asset-ci-01d-semgrep/`.
- Do NOT delete `docs/delivery/release-readiness.md` (authoritative C1–C8 criteria required by `AGENTS.md`).
- Do NOT generate a separate cleanup report file (reasons summarized in PR description).
- Leave exhaustive symbol-level API Reference generation to subsequent Sphinx AutoAPI integration.

## Review Focus

- Broken relative link in modified or remaining markdown documents: automated link audit script fails with non-zero exit code.
- Omission of `host_tools.py` operational realities (non-atomic SQLite/JSON, `registered_not_synced` recovery via `refresh_tools()`): review `tool-assets.md` against `src/vesryn_tool_runtime/host_tools.py`.
- Deletion of still-used compatibility functions: ensure `legacy_preparation_definitions()` remains documented as a compatibility bridge in `tool-assets.md` and `python-api.md`.
- Conflation of Dagger raw execution capture with summary JSON: ensure `tr-asset-ci-01d.json` is described as a distinct historical claim rather than raw evidence in `verification/`.
- Regressions in pytest test suite or ruff lint: `uv run --locked pytest` and `uv run --locked ruff check .` pass cleanly.

---

### Task 1: Consolidate Core Behavioral Contracts and Host Tool Lifecycle into `docs/tool-assets.md`

**Files:**
- Modify: `docs/tool-assets.md`

**Interfaces:**
- Consumes:
  - Contract semantics from `docs/assets/python-cli.md` (ABI glibc/musl constraints, manylinux)
  - Contract semantics from `docs/assets/oci.md` (Dagger container execution boundary, Linux target restriction, manifest vs. index digest)
  - Source facts from `src/vesryn_tool_runtime/host_tools.py` (`default_tools`, `prepare_tool`, `refresh_tools`, `uninstall_tool`, `user_data_root`, `tools.sqlite3`, `tools.json`, `HostToolError`)
  - Source facts from `src/vesryn_tool_runtime/record_sources.py` (`legacy_preparation_definitions`)
- Produces:
  - Consolidated section on Platform and ABI semantics
  - Consolidated section on OCI asset distribution and execution boundaries
  - Dedicated section on Host Tool lifecycle, operational persistence, and failure recovery
  - Section on compatibility bridge `legacy_preparation_definitions()`

- [ ] **Step 1: Check existing `docs/tool-assets.md` content and structure**

Read lines 1-100 of `docs/tool-assets.md` to identify insertion points for ABI semantics, OCI boundaries, Host Tools, and compatibility bridge.

- [ ] **Step 2: Update `docs/tool-assets.md` with consolidated contracts**

Add:
1. **Platform and ABI Semantics**: Explicitly state that on Linux, `abi: "gnu"` designates glibc and `abi: "musl"` designates musl. Explain that `manylinux` wheels require `abi: "gnu"`, `musllinux` requires `abi: "musl"`, and an unspecified target ABI is rejected for libc-constrained artifacts rather than matched unconstrained. Pinned digests and versions defer to `record_seed.sql`.
2. **OCI Distribution and Execution Boundaries**: Clarify that `vesryn-tool-runtime` does not pull, unpack, or execute OCI containers directly. OCI preparation and container execution remain with Dagger (`dag.container().from_(image)`). Releases pin immutable platform manifest digests; multi-arch index digests are provenance only. Targets are restricted to `linux/x86_64` and `linux/aarch64`; non-Linux targets yield `unsupported_target`.
3. **Host Tool Lifecycle and Local Stores (Issue #33)**:
   - Functions: `default_tools()`, `prepare_tool()`, `refresh_tools()`, `uninstall_tool()`, `user_data_root()`.
   - Data root resolution: `%LOCALAPPDATA%\vesryn\data` on Windows, `$XDG_DATA_HOME|~/.local/share/vesryn/data` on Linux/macOS.
   - Dual-store architecture: `tools.sqlite3` records authoritative registration facts (tool, version, owner, verification status); `tools.json` provides the Agent-facing command-and-description list.
   - Operational realities: SQLite commit and `tools.json` publication are not cross-file atomic. If JSON writing fails, `registered_not_synced` is reported; the state can be recovered at any time via `refresh_tools()`. Preparing an external tool reuses it without claiming verified provenance.
4. **Compatibility Entry Points**:
   - `legacy_preparation_definitions()`: Document that this function remains exported as a read-only compatibility bridge used by `host_tools.py` to translate asset records into the legacy preparation structures.

- [ ] **Step 3: Verify content of `docs/tool-assets.md`**

Ensure all sections are clearly formatted, free of dead links, and accurate against `src/vesryn_tool_runtime/host_tools.py`.

- [ ] **Step 4: Commit**

```bash
git add docs/tool-assets.md
git commit -m "docs: consolidate ABI, OCI and host tool lifecycle into tool-assets.md"
```

---

### Task 2: Update `docs/discovery-contracts.md` and `docs/consumers.md`

**Files:**
- Modify: `docs/discovery-contracts.md`
- Modify: `docs/consumers.md`

**Interfaces:**
- Consumes:
  - Source location of `src/vesryn_tool_runtime/record_schema.sql` and `record_seed.sql`
  - Record store API: `bundled_records()`, `open_record_store()`, `compose_catalog()`
  - Current dependency and consumption rules from `pyproject.toml`
- Produces:
  - Accurate schema DDL path and live seed registration documentation in `discovery-contracts.md`
  - Modernized consumer integration documentation in `consumers.md` (no 0.1.0 version constraint)

- [ ] **Step 1: Update `docs/discovery-contracts.md`**

1. Line 5 and physical layout: Replace outdated reference to `data/record_schema.sql` with package resources `src/vesryn_tool_runtime/record_schema.sql` and `record_seed.sql` (accessed via `importlib.resources`).
2. Live Record Declaration and Composition: Document the canonical public loading workflow:
   ```python
   from vesryn_tool_runtime import (
       bundled_records,
       compose_catalog,
       open_record_store,
   )

   store = open_record_store(db_path)
   store.put_records(bundled_records())
   catalog = compose_catalog(store)
   ```
   Note that atomic batch registration via `put_records()` provides idempotent / conflict detection semantics.

- [ ] **Step 2: Update `docs/consumers.md`**

1. Line 3: Remove the obsolete statement "Vesryn depends on vesryn-tool-runtime==0.1.0". Replace with general version requirement matching current releases (`>=0.3.1`).
2. Retain authoritative consumer boundary rules: Vesryn owns DAG/FSM/workflow state/recovery; engineering-ci owns checks and Dagger execution pipelines; Tool Runtime owns tool contracts, discovery, binding, admission, and batch invocation.
3. Keep development `tool.uv.sources` override guidance and production immutable reference requirements.

- [ ] **Step 3: Verify changes in `discovery-contracts.md` and `consumers.md`**

Ensure relative links are intact and terminology matches current exports.

- [ ] **Step 4: Commit**

```bash
git add docs/discovery-contracts.md docs/consumers.md
git commit -m "docs: correct schema resource paths and update consumer integration guidelines"
```

---

### Task 3: Restructure and Update `docs/python-api.md`

**Files:**
- Modify: `docs/python-api.md`

**Interfaces:**
- Consumes:
  - Full `__all__` list in `src/vesryn_tool_runtime/__init__.py`
  - Core contracts from `contracts.py`, `scope.py`, `binding.py`, `invocation.py`, `host_tools.py`, `record_store.py`, `discovery_records.py`, `native_assets.py`, `uv_assets.py`
- Produces:
  - High-level public API guide organized into logical groups with behavioral contracts and usage examples
  - Explicit disclaimer that exhaustive symbol-level API reference will be generated by Sphinx AutoAPI

- [ ] **Step 1: Draft structured content for `docs/python-api.md`**

Organize the document into:
1. **Overview & Principles**:
   - Scope: Generic tool contracts, discovery, selection binding, admission, batch dispatch, result validation, and host tool lifecycle.
   - Note: Exhaustive symbol-level API reference is generated by Sphinx AutoAPI; this document details public API groups, essential behavioral contracts, failure semantics, and usage examples.
2. **Public API Groups (mapped to `__all__`)**:
   - **Tool Contracts & Invocation**: `ToolSpec`, `ToolResult`, `Invocation`, `ExecutionContext`, `ToolAdapter`, `ToolRuntime`, `invoke_tool`, `checked_result`, `DispatchReceipt`, `ToolRuntimeError`.
   - **Catalog & Providers**: `Catalog`, `compose`, `compose_catalog`, `ComposedCatalog`, `provider`, `DiscoveryScope`.
   - **Selection Binding**: `create_binding`, `verify_binding`, `canonical_binding`, `verify_document`, `SELECTION_BINDING`.
   - **Discovery Records & Store**: `ToolAsset`, `ToolGroup`, `ToolAccess`, `GroupMember`, `Platform`, `ToolAssetVersion`, `open_record_store`, `bundled_records`, `RecordError`, `DiscoveryQuery`, `DiscoveryPage`, `DiscoveryDiagnostic`, `DiscoveryErrorDocument`, `DiscoveryContractError`.
   - **Asset Contracts & Backends**: `AssetDefinition`, `AssetRelease`, `AssetTarget`, `AssetSelection`, `AssetPolicy`, `AssetIndex`, `AssetReceipt`, `AssetFile`, `asset_root`, `native_asset_directory`, `Aria2NativeBackend`, `Aria2Source`, `NativeAssetDelivery`, `UvToolBackend`, `UvLock`, `AssetError`.
   - **Host Tools Lifecycle**: `prepare_tool`, `refresh_tools`, `uninstall_tool`, `default_tools`, `user_data_root`, `HostToolError`.
   - **Compatibility Bridge**: `legacy_preparation_definitions`.
3. **Core Behavioral & Failure Semantics**:
   - Admission vs. execution errors.
   - Strict output validation via `checked_result`.
   - Safe event emission via `vesryn_log.EventSink` (no raw parameters or diagnostics).
4. **Representative Usage Examples**:
   - Example 1: Direct Tool Invocation.
   - Example 2: Bundled Record Loading and Catalog Composition.
   - Example 3: Host Tool Preparation and Refresh.

- [ ] **Step 2: Apply updates to `docs/python-api.md`**

Replace outdated 0.1.0 content with the modernized guide.

- [ ] **Step 3: Verify all exported symbols in `src/vesryn_tool_runtime/__init__.py` are represented in the guide groups**

Run a quick Python check verifying every name in `__all__` is mentioned in `docs/python-api.md`.

- [ ] **Step 4: Commit**

```bash
git add docs/python-api.md
git commit -m "docs: restructure python-api.md around current public API groups and contracts"
```

---

### Task 4: Remove Retired Documents, Historical Task Logs, and Redundant Verification Files

**Files:**
- Delete:
  - `docs/shared-definitions.md`
  - `docs/assets/native-workflow.md`
  - `docs/assets/oci.md`
  - `docs/assets/python-cli.md`
  - `docs/assets/security.md`
  - `docs/tasks/vesryn-tool-runtime/P0-aria2-native-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P0-local-tool-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P0-tool-asset-resolution.md`
  - `docs/tasks/vesryn-tool-runtime/P1-asset-selection-backend-migration.md`
  - `docs/tasks/vesryn-tool-runtime/P1-discovery-field-contract.md`
  - `docs/tasks/vesryn-tool-runtime/P1-native-workflow-shared-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P1-oci-shared-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P1-python-asset-platform-compatibility.md`
  - `docs/tasks/vesryn-tool-runtime/P1-python-cli-shared-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P1-security-scanner-shared-assets.md`
  - `docs/tasks/vesryn-tool-runtime/P1-shared-asset-registration-foundation.md`
  - `docs/tasks/vesryn-tool-runtime/P1-unified-tool-registration.md`
  - `docs/delivery/tool-runtime-0.1.0.md`
  - `docs/delivery/tr-001-binding-admission.md`
  - `docs/verification/contract-hashes.json`
  - `docs/verification/results.json`
  - `docs/verification/tr-asset-01.json`
  - `docs/verification/tr-asset-01a.json`
  - `docs/verification/tr-asset-01b.json`
  - `docs/verification/tr-asset-01c.json`
  - `docs/verification/tr-asset-ci-01b.json`
- Preserve:
  - `docs/delivery/release-readiness.md`
  - `docs/verification/tr-asset-ci-01d.json`
  - `docs/verification/tr-asset-ci-01d-semgrep/**`

- [ ] **Step 1: Check git rm targets**

Verify that `docs/verification/tr-asset-ci-01d-semgrep/` and `docs/delivery/release-readiness.md` are NOT in the deletion list.

- [ ] **Step 2: Execute deletions**

```bash
git rm docs/shared-definitions.md
git rm docs/assets/*.md
git rm docs/tasks/vesryn-tool-runtime/*.md
git rm docs/delivery/tool-runtime-0.1.0.md docs/delivery/tr-001-binding-admission.md
git rm docs/verification/contract-hashes.json docs/verification/results.json docs/verification/tr-asset-01*.json docs/verification/tr-asset-ci-01b.json
```

- [ ] **Step 3: Remove empty directories if any remain**

Ensure `docs/assets/` and `docs/tasks/vesryn-tool-runtime/` directories are cleanly removed from the working tree.

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: remove retired shared definitions, historical task logs and redundant verification records"
```

---

### Task 5: Update Root and Documentation Indexes (`README.md`, `docs/README.md`)

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Inspect: `AGENTS.md`

**Interfaces:**
- Consumes:
  - Exact list of live documents in `docs/`
- Produces:
  - Updated `README.md` pointing to live documentation
  - Updated `docs/README.md` table of contents free of broken links
  - Verified `AGENTS.md` entry point validity

- [ ] **Step 1: Update root `README.md`**

Replace links to `docs/shared-definitions.md` and `docs/tasks/...` with links to `docs/discovery-contracts.md`, `docs/tool-assets.md`, and `docs/delivery/release-readiness.md`. Ensure package description and workflow references are accurate.

- [ ] **Step 2: Update `docs/README.md`**

Rewrite the documentation table of contents to list all active documents:
- [Quickstart](../../quickstart.md): installation, complete public chain, runnable example.
- [Public Python API](../../python-api.md): contracts, discovery, binding, batch dispatch, host tools, and usage examples.
- [Architecture and Ownership](../../architecture.md): migrated code and consumer boundaries.
- [Failure and Observation Semantics](../../failure-semantics.md): outcomes, validation, and EventSink.
- [Provider and Dagger Integration](../../providers.md): explicit loading and execution boundaries.
- [Discovery Field Contracts](../../discovery-contracts.md): ToolAsset/ToolGroup/ToolAccess field dictionary and SQLite schema.
- [CLI Asset Contracts & Host Tools](../../tool-assets.md): definitions, frozen selections, ABI/OCI constraints, and host tools lifecycle.
- [Native Asset Acquisition](../../native-assets.md): explicit aria2 preparation, verification, and File/Directory delivery.
- [uv Tool Environments](../../uv-tool-assets.md): thin uv adapter, per-artifact environments, and Linux lock description.
- [Dagger Package Delivery](../../dagger.md): fixed-revision wheel delivery for executors.
- [Consumer Migration](../../consumers.md): compatibility paths and development source inputs.
- [Release Readiness Criteria](../../delivery/release-readiness.md): authoritative C1–C8 acceptance standards.
- [Changelog](../../changelog.md): versioned changes and compatibility notes.
- [Semgrep OCI Execution Evidence](../../verification/tr-asset-ci-01d-semgrep/README.md): unabridged Dagger native execution capture.

- [ ] **Step 3: Verify `AGENTS.md`**

Check lines in `AGENTS.md` referencing `docs/README.md` and `docs/delivery/release-readiness.md`. Confirm both paths are valid and intact.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/README.md
git commit -m "docs: update root and docs indexes with clean navigation"
```

---

### Task 6: Repository-Wide Link Verification, Code Formatting, and Test Execution

**Files:**
- Read/Audit: All `.md` files in the repository

- [ ] **Step 1: Run comprehensive markdown link verification script**

Execute Python script scanning all markdown files (`docs/**/*.md`, `README.md`, `AGENTS.md`) for relative file links and verifying that each target file exists on disk.
Expected: Zero broken links.

- [ ] **Step 2: Run ruff check and format checks**

Run: `uv run --locked ruff check .`
Run: `uv run --locked ruff format --check .`
Expected: Clean pass with zero errors.

- [ ] **Step 3: Run pytest test suite**

Run: `uv run --locked pytest`
Expected: 200 passed, 1 skipped (pre-existing Windows concurrency skip).

- [ ] **Step 4: Final commit and status check**

```bash
git status
```
Ensure working tree is completely clean.
