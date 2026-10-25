"""TR-DISC-01B — issue #32 delivery record (redo on the #27 root)

Source: [issue #32](https://github.com/dymzz/vesryn-tool-runtime/issues/32)
(rewritten task book), stage B of
[#14](https://github.com/dymzz/vesryn-tool-runtime/issues/14). Baseline: the
accepted #27 record foundation — PR #42, merged as `f40f47d` (issue-verified
head `616a162`). This PR replaces the old PR #36 candidate implementation on
the same branch per the task book ("在 #27 的实际基线上更新现有 PR,替换上述
模型和依赖"); the old parallel `tool_registration.py` model, the
`AccessEntrySummary` reuse and the restricted group grammar are gone. Git
identity: `zcode <zcode@local>` (the owner rejected the suggested `codex`
attribution for this agent's commits; the issue's suggestion is not applied).

## The single live declaration

`src/vesryn_tool_runtime/record_seed.sql` is the **only** maintained live
declaration. This PR migrates every tool from the retired
`shared_assets/*.json` documents into it and deletes those documents
together with their loader (`shared_definitions.py`): they are no longer
generated outputs or views — they are retired historical inputs, and the
temporary bridge for old preparation callers derives from the seed instead
(see below). `data/records.sqlite3` is rebuilt from schema+seed and matches
it exactly (asserted by test).

| migration fact | detail |
| --- | --- |
| tools added | ripgrep 15.2.0 (windows aarch64 msvc), hyperfine 2.0.0/1.20.0 × linux-gnu/windows-msvc (all four artifacts), osv-scanner 2.6.0, actionlint 1.7.12, shellcheck 0.11.0, zizmor 1.31.1 (linux x86_64, zizmor gnu), semgrep 1.99.0 + lychee 0.18.0 (oci, linux x86_64+aarch64 digest refs), pyright 1.1.414 (universal, `>=3.7`), deptry 0.25.1 (linux gnu, `>=3.10`), pylint 4.1.3 (universal, `>=3.10.0`) |
| vulture merge | the seed asset gains the still-used 2.14 release (official PyPI url/digest, `>=3.8`) beside 2.16 (`>=3.9`) — per-release interpreter floors preserved |
| provider mapping | uv→uv; github releases→github-release; oci digest refs→oci |
| old `asset_id` | never a second tool primary key: bare canonical names are used (`cli.ripgrep`→`ripgrep`); the historical capability mapping (`python.dead-code`→vulture, `python.typecheck`→pyright, `python.dependency-hygiene`→deptry, `python.duplicate-code`→pylint, `dependency.vulnerability-scan`→osv-scanner, `code.pattern-scan`→semgrep, `docs.link-check`→lychee) is recorded here, not encoded as fake entries |
| placeholders | none: no empty ToolSpec, no example.* capability, no fabricated Adapter/Binding/entry — asset-only registration is used where no real call contract exists |
| pytest-timeout / pytest-randomly / pytest-xdist / beartype / pytest-cov / typeguard / memray / py-spy | registered by the owner's parallel session onto the seed during this task; each URL/SHA re-verified against PyPI here (all match) and carried in the delivered declaration |

Known unexpressed detail (listed per task book): the per-OS entrypoint
suffix (hyperfine's Windows `hyperfine.exe`) is not a record field — the
canonical `hyperfine` is registered and the native backend's existing
entrypoint/`.exe` variant matching covers it; consumer: #33.

## Public chain (names as implemented)

```python
from vesryn_tool_runtime import (
    bundled_records,  # seed → records, pure read, no store
    compose_catalog,
    ComposedCatalog,
    legacy_preparation_definitions,  # TEMPORARY old-caller bridge (#33 removes)
    open_record_store,
)

store.put_records(records)  # atomic batch registration
store.assets / store.groups / store.accesses  # per-record gateways
gateway.get(pk) / gateway.all() / accesses.for_tool(tool_id)
catalog.asset / group / access(pk)
catalog.accesses_for(tool_id)
catalog.tools() / groups() / accesses()  # ordered traversal
```

- **Loading** (`bundled_records`): reads the package seed resource through an
  in-memory database; importing, composing or missing reads create no
  persistent store, migrate nothing and register nothing.
- **Registration** (`RecordStore.put_records`): one transaction; assets →
  groups → accesses so in-batch references resolve; identical
  re-registration is idempotent (no duplicate entry), the same primary key
  with different content is an explicit `duplicate_*` conflict and the whole
  batch rolls back — a failed batch never yields a partial catalog. Unknown
  references surface the schema's foreign-key refusal as `unknown_tool`.
- **Composition** (`compose_catalog`): combines only the sources the caller
  names (record iterables and/or opened stores); identical records collapse
  to one entry, conflicting content raises — load order never silently wins.
- **Reading**: by primary key; `accesses_for` distinguishes a registered
  tool without entries (`()`) from an unregistered tool (`unknown_tool`) —
  registration absence is never reported as an execution failure. Traversal
  is ordered by primary key. Downstream uses these interfaces, never
  `store._db`, SQL copies or identity rules.
- **Catalog interop**: `Catalog.register_asset` now registers tool keys
  directly — no capability ToolSpec/Adapter/Binding prerequisite — and
  `asset_for` reads by key (scope filtering still applies where a capability
  exists). The legacy selection surface stays functional for #33's backend
  migration.

## Temporary bridge (explicit removal list for #33)

`legacy_preparation_definitions()` derives read-only `AssetDefinition`s from
the live records for the old preparation callers — it writes nothing and is
not a second authority. Callers (all old-path, removed by #33):
`examples/native_asset_delivery.py` (switched to the bridge in this PR),
`examples/asset_acceptance.py`, the uv/aria2 selection path, plus
`examples/uv_tool_prepare.py`'s hardcoded RELEASES table (never part of the
json chain; retires with #33) and `examples/native-assets.json` /
`examples/asset-definitions.json` (self-contained sample inputs). #33 also
deletes the bridge itself.

## Acceptance mapping

| Requirement | Result |
| --- | --- |
| Load/register real ToolAsset directly; no placeholders; one tool_id across groups/entries | `test_registration_needs_no_capability…`, `test_same_tool_id_across_groups_and_entries…`; CI offline step registers the whole declaration with zero ToolSpecs. |
| Six seed tools + shared definitions migrated; vulture/hyperfine multi-version/platform preserved; duplicate sources merged by evidence | `EXPECTED_TOOLS` (25 live tools) + `test_migration_kept_the_real_preparation_facts`; trivy/vulture exist once each (seed is the merged declaration). |
| Public compose/traverse/read; member summaries/aliases and entry method/target/contract preserved; no private DB use | `ComposedCatalog` tests; traversal tests; downstream tests use public names only. |
| No duplicates; conflicts/invalid FK/failed batches deterministic; read-only queries create nothing | `test_composition_dedups…`, `test_batch_registration_is_atomic…`, `test_reads_never_touch_persistent_state`. |
| CI no placeholder-capability self-proof; sample contracts honestly scoped | rewritten CI step: `placeholders: none`, `execution: not_performed`; the three trivy entries remain clearly sample contracts, no binding/execution claimed. |
| Installed candidate package loads from bundled resources | CI runs `examples/shared_definitions.py` and the declaration check from the installed wheel (package resources; no checkout). |
| Unique source, actual signatures, artifact identity, affected interfaces, C/D/E samples, removal list | this record; candidate artifact built and verified below. |

## Verification (2026-10-25, CPython 3.14.8, locked env)

| Evidence | Result |
| --- | --- |
| New suite `tests/test_record_sources.py` | 10 passed (25-tool declaration) |
| Full suite | 211 passed, 1 skipped — no regression |
| Wheel | `vesryn_tool_runtime-0.3.1-py3-none-any.whl` rebuilt; seed resource
  carries the 19-tool declaration; extracted-wheel run of
  `examples/shared_definitions.py` + composition OK |
| Lint / format | clean |

Out of scope (per task book): backend consumption migration (#33), entry
resolution and scope diagnostics (#34), group discovery/matching (#35),
Binding/invocation/events (#15); no new Registry service/runner/installer;
no release.

## 2026-10-25 review fixes (fourth commit, on top of 0d68941)

1. **P1 — composed references validated after merge**: `ComposedCatalog`
   now checks every group member and every access against the MERGED asset
   set — cross-source references resolve, a tool missing from every named
   source is an explicit `unknown_tool` refusal (ghost groups/entries can
   no longer pass through to D/E).
2. **P2 — one canonical alias order**: member aliases are an unordered
   match set canonicalized (sorted) once at construction; storage rows,
   documents, equality and idempotent re-registration all share that
   order, so re-submitting the same member in any input order is stable,
   while a genuinely different alias set still conflicts.
3. **P1 — Native CLI entry regression**: `native_asset_delivery.py`
   declared `--source-artifact` but read `args.source_art` (AttributeError
   before any backend call); it reads the declared attribute again, with a
   stub-backend regression test that runs the CLI past the argument site.
