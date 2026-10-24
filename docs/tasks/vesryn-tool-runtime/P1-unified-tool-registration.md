# TR-DISC-01B — issue #32 delivery record

Source: [issue #32](https://github.com/dymzz/vesryn-tool-runtime/issues/32), stage B of
[issue #14](https://github.com/dymzz/vesryn-tool-runtime/issues/14). The issue's local
task-book path does not exist in this checkout; this record is created from the fetched
issue #32 body.

Baseline: main `7ef87b3` (v0.3.0 + #30 docs + the merged #27 field contracts, PR #28).
This branch is independent of the still-open PR #31 (#29); where they touch the same
files (`shared_assets/python.json`, `tests/test_shared_assets_python.py`,
`docs/verification/tr-asset-ci-01b.json`, `docs/tool-assets.md`) they must merge
serially per the issue's rule — merge #31 first and rebase this branch, or resolve at
merge. Git identity: `zcode <zcode@local>`. Handoff identity: [PR #36](https://github.com/dymzz/vesryn-tool-runtime/pull/36) (branch
`codex/issue-32-unified-tool-registration`); submitted for review without
merging.

## Unified registration (the public model)

- **`ToolAsset(tool_id, definition, display_name="", description="")`** —
  `src/vesryn_tool_runtime/tool_registration.py`. `tool_id` is the tool primary
  key: a bare program identity (`trivy`) or a real, source-backed capability ID
  (`python.dead-code`); the old capability grammar is no longer imposed on
  registration.
- **`ToolGroup(group_id, members, display_name, description, aliases)`** — same
  module; `group_id` keeps the delivered #27 `domain.group` grammar, members
  reference tools by primary key (unique, non-empty).
- **Access entries reuse the delivered #27 `AccessEntrySummary` unchanged** as
  the registration record (identity `access_id =
  <catalog_ref>:<tool_id>@<entry_key>`, facts and validation single-sourced
  there). Accordingly, #27's tool-id grammar on entries/candidates/group
  members was relaxed from the capability grammar to the token grammar so bare
  keys can be referenced; group identities are unchanged.

`Catalog` (contracts.py) now provides the registration, read and composition
surface:

```python
Catalog.register_asset(definition, *, tools)   # direct tool-key registration
Catalog.register_tool(asset: ToolAsset)        # single tool record
Catalog.register_group(group: ToolGroup)       # FK: members must be registered
Catalog.register_access(access: AccessEntrySummary)  # FK: tool must be registered
Catalog.group_for(group_id) / Catalog.access_for(access_id)   # PK reads
Catalog.asset_for(tool_id)                     # PK read, no capability needed
```

Semantics: duplicate primary keys with different definitions are explicit
errors (`conflicting_asset` / `Duplicate … registration`); identical
re-registration is idempotent; unknown foreign keys are rejected by name;
`merge`/`scoped_catalog` carry groups and entries and reject duplicate
ownership across providers. **Registration is not installation, binding or
execution**: `select_asset` requires a registered capability contract and
refuses with `unregistered_tool` for a contract-less tool (no fabricated
contract hash or callable entry ever exists). Import and query persist
nothing and initialize no database; the single write source for shared
definitions remains the `shared_assets/*.json` documents in this repository
and package.

## Data migration (single active source)

| Document | Change | New tool primary keys |
| --- | --- | --- |
| `examples.json` | placeholder keys removed | `ripgrep`, `hyperfine` (bare) |
| `native.json` | placeholder keys removed | `osv-scanner` keeps the real `dependency.vulnerability-scan` (ECI #51 source); `actionlint`, `shellcheck`, `zizmor` bare |
| `security.json` | placeholder key removed | `trivy` (bare) |
| `oci.json` | source-less capability-style IDs replaced | `semgrep`, `lychee` (bare) |
| `python.json` | vulture gains the still-used 2.14 release (PyPI-verified Requires-Python `>=3.8`; 2.16 keeps `>=3.9` — the old path flattened both to `>=3.8`); keys unchanged (real ECI capabilities) | `python.dead-code`, `python.typecheck`, `python.dependency-hygiene`, `python.duplicate-code` |

Hyperﬁne 2.0.0 (Linux) and 1.20.0 (Windows) — still used by the old
preparation path — are all present in `examples.json`; nothing is lost or
downgraded. Old capability IDs were kept only where a real source contract
exists (the python.* set and `dependency.vulnerability-scan`).

## Old callers and C's removal list (#33)

The unified source is authoritative now; these old paths still carry
duplicate definitions or the placeholder pattern and are **C's** to migrate
(no new hardcoded definitions were added by this task):

1. `examples/uv_tool_prepare.py` — hardcoded `RELEASES` (vulture 2.16/2.14) consumed
   by `examples/asset_acceptance.py`; consume `python.json` instead and retire the
   tuple.
2. `examples/native-assets.json` — local hyperfine definitions beside the already
   migrated osv/actionlint/shellcheck/zizmor references; reference `examples.json`
   (tool key `hyperfine`) instead.
3. `examples/native_asset_delivery.py` — the `<asset_id>.example` empty-ToolSpec
   catalog pattern; register directly under bare keys with no ToolSpec/`None`
   adapter.
4. `examples/asset_acceptance.py` — builds definitions from the two old paths; derive
   them from the unified documents (its `hyperfine.version`/`vulture.version`
   ToolSpecs are legitimate test capabilities for acquisition and may stay).

`examples/asset-definitions.json` is the self-contained #6-era standalone demo,
not a shared source, and stays as history.

## CI

The `Verify combined shared definitions offline` step no longer generates empty
ToolSpecs to self-prove association: it registers every bundled record into a
bare `Catalog` (no ToolSpec, no adapter), checks asset/tool primary-key
uniqueness, registers a group spanning all tool keys (exercising the FK path
from the installed wheel) and records registration-only evidence
(`execution: not_performed`). `examples/shared_definitions.py` now
demonstrates direct registration without any ToolSpec.

## Directed acceptance

| Requirement | Result |
| --- | --- |
| trivy ToolAsset registers directly in a catalog with no empty ToolSpec/example.*; the same tool_id spans two groups and multiple entries | `test_unified_registration_supports_groups_entries_and_key_conflicts`. |
| Group metadata/aliases and entry facts preserved via public records; unknown FKs and conflicting PKs explicitly rejected | same test + `ToolGroup`/`ToolAsset` validation and `group_for`/`access_for` misses. |
| All current shared definitions and still-used versions migrated; single active source plus the C handover list | table above; vulture 2.14 migrated with verified metadata; hyperfine coverage complete. |
| Registration is not install/binding/execution; no fabricated callable entries | `select_asset` refuses contract-less tools with `unregistered_tool`; asset views state `unregistered_tool`; CI records registration-only evidence. |
| Placeholder/old-regex/synonymous-ID assertions replaced with real integrity checks | rewritten across `test_shared_definitions`, `test_assets`, `test_shared_assets_{native,security,oci,python}`; new unified-registration coverage; CI check replaced. |
| Reading registration records verified from an installed candidate package | wheel extracted and imported from the extraction path only: all five documents load, all tools register into a bare catalog, `group_for`/`access_for` work (below). |
| Actual public signatures, candidate commit/package, migration notes and C/D/E samples | this record, the updated docs, and the PR; parent #14 backfill follows this handoff. |

## Verification (2026-10-24, CPython 3.14.8, locked env)

| Evidence | Result |
| --- | --- |
| Full suite | 194 passed, 1 skipped — no regression. |
| Unified-registration cases | `test_shared_definitions.py` 25 passed, including group/entry FK+PK conflicts and `merge`/`scoped_catalog` carriage. |
| Rewritten group suites | native 8, security 3, oci 7, python 5 passed. |
| Lint / format | `ruff check` clean; `ruff format --check` clean repo-wide; `ci.yml` parses as valid YAML. |
| Installed-package read | candidate wheel (0.3.0, module-directory data rule) extracted and imported from the extracted location: `shared_definition_documents()` lists all five documents; every record loads and registers into a bare `Catalog`; a `ToolGroup` over all 13 tool keys registers and reads back. This proves registration and package data only; no tool was run. |
| Verification record | `docs/verification/tr-asset-ci-01b.json` vulture entry regenerated through `load_shared_definitions` with a revision-history entry. |
