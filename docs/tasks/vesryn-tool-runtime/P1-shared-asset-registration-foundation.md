# TR-ASSET-CI-01A — issue #16 delivery record

Source: [issue #16](https://github.com/dymzz/vesryn-tool-runtime/issues/16), stage A of
[issue #12](https://github.com/dymzz/vesryn-tool-runtime/issues/12). The issue's local
task-book path does not exist in this checkout; this record is created from the fetched
issue #16 body, not an inferred copy of an external task book (same handling as the
issue #6 record).

Baseline verified locally: source `306912152545e442a698b8b0c1f3188ce0fc09c1`, released
version 0.2.0. The package version stays 0.2.0; no release, tag or publication is
performed by this task. Existing user changes to `AGENTS.md`, `.gitignore`, `.codex/`
and `unregistered/` remain outside this implementation.

Handoff identity for B/C/D/E: [PR #21](https://github.com/dymzz/vesryn-tool-runtime/pull/21)
(branch `codex/issue-16-shared-asset-foundation`).

## Handoff

Public signatures, the document format, identity mapping rules, the packaging rule
and the per-group path ownership table are in
[Shared asset definitions](../../shared-definitions.md). Summary:

```python
from vesryn_tool_runtime import (
    SharedAssetDefinition,        # frozen record: definition + tools
    load_shared_definitions,      # bundled name or filesystem path -> records
    register_shared_definitions,  # records -> existing Catalog, via register_asset
    shared_definition_documents,  # bundled document names, sorted, nothing loaded
)
```

- Consumers: `load_shared_definitions` needs no ECI checkout, adapter or consumer
  project environment, performs no install/network/write, and grants nothing.
  `register_shared_definitions` requires every associated capability to already be
  registered with a real ToolSpec and adapter; example IDs or `Adapter=None` cannot
  masquerade as callable capabilities.
- B/C/D/E add only their exclusive `src/vesryn_tool_runtime/shared_assets/<group>.json`
  data file, `tests/test_shared_assets_<group>.py` test file and `docs/assets/<group>.md`
  document (full table in the shared doc). No manifest, `__init__`, `pyproject` or
  common-test edit is needed to add definitions; required common-entry changes go
  through this task/#12 once.
- Inputs/outputs sample: `examples/shared_definitions.py` (offline read → explicit
  assembly → `asset_view`; prints one `unsupported_target` and one `selectable` view,
  `installed: not_configured`).
- The bundled seed is `shared_assets/examples.json`: ripgrep 15.2.0 and hyperfine
  2.0.0/1.20.0, as verified on 2026-10-23 by the #6 and #8 deliveries, associated
  with example capabilities only.

## Directed acceptance

`tests/test_shared_definitions.py` (the common compatibility test) exercises the
issue's acceptance:

- Shared definitions read independently (no Catalog/adapter/consumer environment),
  assembled only by explicit selection; ordinary reads have no install, network or
  filesystem side effects; bundled names take precedence over local files.
- One asset associates multiple existing capabilities (`artifact_id` shared across
  them); pure capabilities remain without assets (`unregistered_asset`); existing
  IDs, Provider identity and Scope/Binding semantics are unchanged.
- Conflicts, unknown definitions and unregistered capabilities keep their existing
  explicit reasons (`conflicting_asset`, `invalid_definition`, `unregistered_tool`,
  release-level codes); no unknown-definition fallback exists.
- In-package data ships with the wheel; one installed-artifact read proves it.

Verified on 2026-10-24 with CPython 3.14.8 (this checkout's locked environment):

| Directed evidence | Result |
| --- | --- |
| New common compatibility cases | 21 passed. |
| Full existing suite | 152 passed, 1 skipped — no regression from the new exports/data. |
| Lint | `ruff check src tests examples` clean. |
| Candidate wheel | `vesryn_tool_runtime-0.2.0-py3-none-any.whl`, SHA-256 `4723b6ce575dfc21397a3e0c3a2f42a2ba5aac100006d89bdaefe45a97e8f5ab`; contains `shared_definitions.py` and `shared_assets/examples.json`. Candidate sdist SHA-256 `7e2430d9eed721e9148664a8d1a44e75e8ad62c1d8008b71ada0ab553d46b85f` also contains both and all test files (sdist `source-include` now takes `tests/**`, so group test files ship without further `pyproject` edits). |
| Installed-artifact read (single) | Wheel extracted and imported from the extracted location only: `shared_definition_documents() == ("examples.json",)`, both seed records loaded, hyperfine 2.0.0 selected offline after explicit assembly. No installation matrix run. |

The candidate wheel is stored under `.test-tools/issue-16/dist/`; it does not replace
the released 0.2.0 artifact. Actual B/C/D/E definition content (Vulture, Pyright,
deptry, Pylint, OSV, actionlint, ShellCheck, zizmor, Semgrep, Lychee, Trivy and
conditional Gitleaks) is not authored here — those belong to the group files above.
ToolGroup/Access queries remain #14, event association #15, trusted policy #13.
