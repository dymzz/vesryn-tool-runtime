# TR-DISC-01A — issue #27 delivery record (redo)

Source: [issue #27](https://github.com/dymzz/vesryn-tool-runtime/issues/27),
reopened: the merged PR #28 did not satisfy the three record types and the
issue was restored to incomplete ("合并实现仍未满足下述三类记录……由后续
提交替换偏差,不改写已合并历史"). This record replaces the PR #28 delivery
record for this task; merged history itself is not rewritten.

Baseline: main `adc1194`. Branch `zcode-27-record-foundation`, delivered in
three owner-directed stages. Git identity: `zcode <zcode@local>` (the owner
rejected the issue's suggested `codex` attribution; the redo is signed by the
same identity that owns the earlier work).

## What is delivered

**Stage 1 — six-table constrained SQLite foundation** (`a4d7485`):
`data/record_schema.sql` (the frozen DDL, single authority), `data/seed.sql`
(the issue's literal examples), `data/records.sqlite3` (the committed library
built from both — `data/` is the database home; `open_record_store()` opens
it by default); `discovery_records.py` (records only, zero I/O),
`record_store.py` (per-record gateways over one connection,
`PRAGMA foreign_keys=ON`). Constraints live in the tables: enum CHECKs
(provider `uv|github-release|oci`, method `dagger|uv|native|api`, digest
`sha256`), NOT NULL on every required field, `(tool_id, version, platform)`
uniqueness, member PK `(group_id, tool_id)`, alias PK `(group_id, tool_id,
alias)`, JSON-object contracts, digest shape checks — and **no `asset_id`
column anywhere**.

**Stage 2 — serialization and deviation replacement** (`9392a8a`):
`record_document`/`record_from_document` strict round trips; the query layer
(`DiscoveryQuery`/`DiscoveryPage`/diagnostics/errors) carries the records'
own documents — the five PR #28 deviations are replaced: member records carry
their own summary and aliases; entries carry method/target/their own
contract; `compose_access_id` and the forced `catalog_ref:tool_id@entry_key`
composition are deleted (access_id is used as registered); bare tool
identities are valid tool primary keys; the entry contract is no longer
forced equal to an old ToolSpec capability ID. Old-format handling exists
only in `legacy_convert.py` — an explicitly **temporary outermost** module
(only transition tests import it; deleted once adaptation completes) that
converts old group documents (dropping `catalog_ref`) and returns an explicit
`unsupported` conclusion for old access summaries, which lack method/target.

**Stage 3 — this record and the field dictionary**
([discovery contracts](../../discovery-contracts.md)): every issue field
mapped word-for-word to its record field and column, the six-table layout,
identity rules and the migration boundary.

## Acceptance mapping

| Requirement | Result |
| --- | --- |
| 三类记录及 versions/members 子记录字段均有公共定义、序列化、校验;准确 Python 签名、字段类型、缺省规则及 JSON 示例 | `discovery_records.py` + `record_document`/`record_from_document`; dictionary doc lists each field's type and default; `data/seed.sql` is the JSON/SQL example set. |
| 原文 trivy、ci-security、ci-release、trivy.scan、trivy.sbom、trivy.cli 完成往返;同一工具跨分组、版本、平台和入口保持同一 tool_id | Seeded in the committed library; `test_round_trip_with_the_issues_literal_examples` and `test_committed_library_round_trips_the_seeded_examples` read them back through the gateways. |
| 两个分组中的成员用途摘要和别名保持各自内容;Access 的 method、target 和真实契约可以取得 | ci-security vs ci-release member records differ and stay per-group; three trivy entries each return their own method/target/contract. |
| 重复主键冲突、无效外键及字段非法形态明确校验;不以额外目录身份替代全局工具身份 | Duplicate PK/FK/shape tests at both record and raw-SQL levels; the only identity is tool_id (no asset_id column; schema parity enforced). |
| ToolSpec/Dagger 原生契约仍可准确引用,实际参数契约只有一个权威来源;旧能力身份与新工具身份不同的情况有明确迁移或映射依据 | `ToolAccess.contract` carries the ToolSpec/Dagger object per entry; the migration boundary (old capability IDs and asset_id stay in historical data; `legacy_convert` is temporary and outermost) is documented above. |
| 明确现有资产、Binding/API 和消费者的受影响范围;定向验证,不冻结旧格式也不静默重解释 | Below. |
| #14 回填提交/制品、公共接口、迁移说明、定向证据及后续模块边界 | This record; the dictionary doc's "后续任务" section names #32–#35 as consumers of this handoff. |

## Impact scope (what is and is not affected)

- **Replaced in this branch**: PR #28's public types
  (`AccessEntrySummary`, `CandidateSummary`, `ContractDetail`,
  `GroupSummary`, its `GroupMember`) and `compose_access_id` are gone from
  `discovery_contracts.py` and the package exports. Existing
  `ToolSpec`/`Catalog`/Binding/Scope semantics are untouched.
- **Unmerged downstream branches** (PRs #36/#37 for issues #32/#33, PR #41
  for #13) referenced the replaced types; per the issue they rebuild on this
  root — their published texts are not rewritten here.
- **Old data**: nothing on main persisted these documents outside tests and
  examples, so no stored record is silently reinterpreted; the temporary
  converter covers the only real old shapes (PR #28 test fixtures).

## Verification (2026-10-24, CPython 3.14.8, locked env)

| Evidence | Result |
| --- | --- |
| Record foundation tests | 12 passed — round trips on the literal examples, duplicate PKs, FK refusals (record and raw-SQL), platform/digest/enum CHECKs, schema parity and drift refusal, frozen-`.sql` execution lock, committed-library read-back. |
| Query-layer tests | 8 passed — paging bounds, envelope/unknown-field rejection, pages carrying record documents, off-page facts, diagnostics vs ToolResult, temporary-converter conclusions. |
| Full suite | 198 passed, 1 skipped — no regression (the pre-existing #8 concurrency case still flakes only on this Windows host; isolated runs pass). |
| Lint / format | `ruff check` clean; `ruff format --check` clean. |

Not delivered here (by boundary): group search/ranking, entry selection,
install/download, execution scheduling, #15 event fields; no Vesryn/ECI/host
changes; no release.

## 2026-10-24 review fixes (second commit series)

Six review findings, fixed in order on this same branch:

1. **P1 — packaging**: the frozen DDL and seed now ship as **package
   resources** (`vesryn_tool_runtime/record_schema.sql`,
   `record_seed.sql`) read via `importlib.resources`; verified from the
   built wheel and sdist by extracting and importing with no source
   checkout (`open_record_store(":memory:")` + seed read + a full
   put/get), and the CI installed-wheel step now exercises this entry.
   No absolute paths, no checkout requirement.
2. **P1 — writable location**: `open_record_store(path)` requires an
   explicit path; the default that resolved into the Python installation
   directory is deleted. Writable stores live where the caller puts them
   (the repo demo library stays at `data/records.sqlite3`, opened by
   explicit path).
3. **P2 — schema authority**: primary-key columns are NOT NULL (three
   NULL-PK inserts now rejected), `tool_group_member_alias` carries a
   composite foreign key to the membership (aliases cannot outlive or
   bypass their member; deletion cascades), sha256 digests must be
   lowercase hex (`'g'×64` rejected at both record and SQL level), and
   the drift check now compares the **full DDL** (`sqlite_master` vs the
   frozen file, whitespace-normalized) — a same-columns/no-constraints
   database is refused as `schema_drift`.
4. **P2 — release semantics**: `Platform` gains `abi` and the version
   record gains `python` (interpreter requirement, independent of
   platform presence); uniqueness covers platform+abi+python, so deptry's
   abi `gnu`/`>=3.10` release is representable and a same-version musl
   build coexists instead of conflicting. The seed demonstrates a
   universal wheel (`vulture`, no platform, `>=3.9`).
5. **P2 — page typing**: `DiscoveryPage` validates every record's actual
   type against `record_kind`; a tool-group page carrying a ToolAccess
   document is rejected.
6. **P2 — legacy honesty**: the temporary converter and its fabricated
   test inputs are deleted; the documented conclusion is that PR #28-era
   documents **cannot convert** (members lack group-local summary/aliases,
   accesses lack method/target) and no compatibility layer is delivered.

Schema version bumped to 2; `data/records.sqlite3` rebuilt from the new
frozen schema and seed.

## 2026-10-24 second review fixes (third commit series)

1. **P2 — single home for the interpreter constraint**: `Platform.python`
   is deleted (a second definition silently lost through document and
   database round trips). The platform keeps os/arch/abi only; the
   interpreter requirement lives solely on `ToolAssetVersion.python`,
   asserted by a TypeError test for the platform kwarg and a full
   document + store round trip on the version.
2. **P2 — seed URLs from official metadata**: Hypothesis 6.170.9's wheel
   and sdist sources (previously derived from the digest and 404ing) are
   replaced with the official `urls[].url` values for the same digests;
   the `package` field carries the plain package name (`hypothesis` —
   extras like `[cli]` are not part of the package name and broke
   metadata lookups). All five uv seed entries (hypothesis,
   import-linter, mutmut, schemathesis, vulture) re-verified against
   live PyPI metadata: URL and SHA-256 all match.
3. **Delivery state made honest**: the four newly registered tools
   (import-linter 2.15, hypothesis 6.170.9, mutmut 3.8.0,
   schemathesis 4.32.4) existed only as uncommitted local diffs during
   review; they are now committed with this series — seed SQL, rebuilt
   `data/records.sqlite3` and the round-trip/package-name tests — so the
   PR's package actually delivers them. Tool installation, Binding and
   execution remain outside this acceptance, as stated.
