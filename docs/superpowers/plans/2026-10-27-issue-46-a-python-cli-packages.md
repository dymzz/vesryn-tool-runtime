# Issue #46 A Python CLI Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare one declared Sphinx tool with pinned MyST/Needs plugins through Runtime's existing uv chain, with truthful environment and reuse evidence.

**Architecture:** `prepare_tool` accepts an optional explicit package set; the existing `_uv_install` remains the only Python tool installer. A small private read-only helper module normalizes pins and inspects uv's public tool view plus the actual environment Python. Existing asset declarations, source-proof columns and registration remain the authorities; no schema or state service is added.

**Tech Stack:** Python >=3.14, uv 0.12.23, existing packaging/pytest/SQLite, Sphinx 9.2.0, myst-parser 5.1.0, sphinx-needs 9.1.0.

**Spec:** [A design](../specs/2026-10-27-issue-46-a-python-cli-packages-design.md), [issue #46](https://github.com/dymzz/vesryn-tool-runtime/issues/46), and the user's instruction to complete one stage at a time.

## Global Constraints

- Baseline is `98c8c27c4528fa0e65095d5a5192ed959e0d7d8e`; use the default managed worktree, preserve the original checkout's changes.
- `with_packages=None` preserves legacy behavior; explicit `()` reconciles an empty additional-requirement set.
- Only canonical exact `name==version` requirements are accepted; no URL/path/marker/extras/wildcard/range or main-package override.
- Main wheel selection, download and SHA-256 verification stay in the existing chain. Plugin/transitive installation is not whole-environment supply-chain proof.
- No independent plugin Agent tools, installer, registry, environment manager, private uv receipt/cache parser or SQLite schema migration.
- All actual tool/cache/Runtime roots stay under `.tmp/issue-46-a/` in the worktree. No global installation or PATH/configuration edits.
- A stops before B lifecycle acceptance and C HTML/Needs configuration. No CI documentation integration, Release, merge or issue closure.
- Keep verification in PR A/B/C notes and temporary evidence; do not add another task delivery report.

## Review Focus

- Same main version with changed, reordered, removed or missing plugins must not reuse solely on `--version`; Task 2 covers these.
- Invalid requirements and a main-package override must fail before download, uv or persistent writes; Task 2 covers these.
- A shadowing or externally owned command must remain a conflict, even if another uv environment has valid plugins; Task 2 covers this.
- Offline permission and caller-selected UV/Runtime roots must reach every invoked uv process; Task 2 covers this.
- Inspection or a uv no-op must not promote unknown main source provenance, and post-install verification failures must not register success; Task 2 covers these.

---

### Task 1: Declare the main Sphinx artifact

**Files:** Modify `src/vesryn_tool_runtime/record_seed.sql`, derived `data/records.sqlite3`, `tests/test_record_sources.py`, `docs/tool-assets.md`.

**Interfaces:** Consumes `bundled_records()`, `ToolAsset`, `ToolAssetVersion`, `RecordStore.put_records`; produces one declared `sphinx` uv asset with package `sphinx`, command `sphinx-build`, version `9.2.0`, Python `>=3.13` and the exact source/SHA from the design. Existing record types/schema and default tool list remain unchanged.

- [ ] Add `test_bundled_sphinx_is_one_declared_cli_with_pinned_main_wheel`: assert those fields, exactly one Sphinx asset, and no MyST/Needs standalone tool assets.
- [ ] Run that new test and confirm it fails because Sphinx is absent.
- [ ] Add the seed declaration; synchronize only the derived demo library through the existing record-store operations, preserving existing facts. Add a short usage/dependency-boundary paragraph to the current host-tool documentation.
- [ ] Run the new test and existing seed/demo consistency cases in `tests/test_record_sources.py` and `tests/test_discovery_records.py`; require no failures. No full-suite rerun.
- [ ] Review the exact staged files and commit the self-contained declaration change.

### Task 2: Extend the existing uv preparation/reuse path

**Files:** Modify `src/vesryn_tool_runtime/host_tools.py`, `docs/python-api.md`, `docs/tool-assets.md`; create `src/vesryn_tool_runtime/_uv_tool_packages.py` and `tests/test_host_tool_packages.py`. Update `tests/test_host_tools.py` only where an existing affected interface requires it.

**Interfaces:** Extend `prepare_tool(..., with_packages=None)` without changing old callers. Private helper `normalize_with_packages(value, main_package)` returns `None` or a sorted tuple of pinned requirement strings. `inspect_uv_tool(uv, package, *, environ, runner)` returns `None` or a document with `package`, `version`, `entrypoints` and `environment`; the latter's keys are exactly `python`, `prefix`, `python_version`, `with_packages`, `packages` (sorted `{name, version}` records), and `dependencies_consistent`. The helper does not install or persist anything. `_uv_install(..., interpreter=None, with_packages=(), environ=None, reinstall_main=False)` remains the installation operation. `prepare_tool` exposes the observed `environment` on explicit-package success; helper validation/inspection failures map to `HostToolError` with `invalid_input` / `environment_unverified`, without a second public error family.

- [ ] Add behavioral tests for canonical/reordered/duplicate pins, conflicting pins, rejected requirement forms, unsupported providers and main-package override. Assert invalid input invokes neither runner/download nor store creation. Run and observe the missing-interface failures.
- [ ] Add tests against uv 0.12.23 public text fixtures and actual interpreter JSON: correct tool/entry association, Windows paths with spaces/parentheses, unrelated tool blocks, malformed/missing output, incorrect prefix and package versions. Never use project imports as tool-environment evidence.
- [ ] Add preparation tests: matching CLI with missing plugins reaches uv; complete equal requests reuse without install; changed pin/removal/explicit empty reach uv; `None` preserves old reuse. A foreign entry remains `conflict`.
- [ ] Add failure/provenance tests: offline/effective env reaches uv, main verified wheel remains the positional install input, required source-proof recovery uses only `--reinstall-package <main>`, uv failures keep their real failure, dependency/prefix/shadowing failures do not register success, and source inspection alone never sets main source proof. Run the new cases and observe their expected failures before implementation.
- [ ] Implement normalization with existing `packaging`; narrow public-output parsing and isolated environment inspection in the private helper. Validate pins before preparation side effects. Keep existing legacy/native flows intact.
- [ ] Implement explicit-package coordination in the existing preparation path. A known uv environment is inspected before reuse and after reconciliation; use package-specific main reinstall only when needed to establish source proof. Preserve strict `tools.json` shape and existing `registered_not_synced` handling.
- [ ] Run `pytest tests/test_host_tool_packages.py tests/test_host_tools.py` with all temporary paths under `.tmp/issue-46-a/`; require no failures. Run Ruff check/format for touched Python files.
- [ ] Document `None` versus empty, the additional environment evidence, uv 0.12.23 text-interface limitation, conflict behavior, and the main-artifact-only meaning of `source_verified`. Review and commit only Task 2 files.

### Task 3: Verify A through the real Runtime chain and stop

**Files:** Temporary harness/evidence only under `.tmp/issue-46-a/`; refine the same current API/host-tool docs if actual behavior requires a correction. No `docs/conf.py`, Need directives or generated HTML/JSON are added in A.

**Interfaces:** Call actual `prepare_tool("sphinx", version="9.2.0", command="sphinx-build", description=..., with_packages=("myst-parser==5.1.0", "sphinx-needs==9.1.0"), root=<temporary root>, allow_network=True, uv=<approved uv>, environ=<isolated roots and PATH>)`. Runtime must consume the declared main artifact. Do not substitute a manual Sphinx `uv tool install`.

- [ ] Prepare an isolated Runtime test environment using the approved Python/uv, locked project dependencies and temporary caches; do not use the original checkout's free-threaded `.venv` or change global configuration.
- [ ] Perform one real Runtime preparation. Retain its actual outcome and main artifact SHA, uv version, tool environment identity, canonical request, distribution inventory and dependency check. A failure is a failure, not a registration success.
- [ ] Run the returned `sphinx-build --version`, then that tool environment's Python with `-I -B` to import `sphinx`, `myst_parser`, `sphinx_needs` and check distribution versions `9.2.0`, `5.1.0`, `9.1.0`.
- [ ] Repeat the same Runtime request offline once to establish actual supported reuse. Exercise plugin-set changes with focused local-wheel tests from Task 2 rather than redownloading more Sphinx environments solely for coverage.
- [ ] Request an independent read-only branch review; resolve material A findings and rerun only newly affected checks. Record A's evidence in the PR description, with B/C explicitly pending. Do not merge or close #46.
- [ ] Return the A result for stage acceptance; do not start B or C automatically.

## Baseline evidence and self-review

[Main CI 40367029284](https://github.com/dymzz/vesryn-tool-runtime/actions/runs/40367029284) is successful for the exact baseline. Reuse it; current implementation must still pass its affected directed tests. Task 1 covers the live declaration; Task 2 covers the generic gap, changed-set/ownership/failure semantics and evidence; Task 3 covers actual same-environment compatibility. Task 2's tests map every Review Focus line. Public signatures and result fields match the design. Publication and downstream document checks remain out of scope.
