# Discovery field contracts (single field authority)

This is the public handoff for
[issue #27](https://github.com/dymzz/vesryn-tool-runtime/issues/27)
(TR-DISC-01A / 14-A, child of [#14](https://github.com/dymzz/vesryn-tool-runtime/issues/14)),
baseline v0.3.0 (`3902efcb2154c82caf95c8d7d449f7268d68f6d1`).
`src/vesryn_tool_runtime/discovery_contracts.py` is the **single canonical
definition** of every field below; this document describes it and never
redefines it. Later #14 tasks reuse these documents, enums, schemas and
identity rules instead of copying them.

The module implements fields, thin validation and serialization only. It
implements **no** group retrieval, alias scoring, ranking, entry selection,
Scope decision or diagnosis algorithms, Binding management, permission
verification, Provider loading, Dagger live discovery, installation or
invocation. A field can *represent* a fact without that fact being verified:
constructing any document here grants no permission and asserts no readiness,
and field-layer validation passing is not evidence that any query or admission
algorithm exists.

## Public signatures

```python
from vesryn_tool_runtime import (
    AccessEntrySummary,      # one logical access entry with separated facts
    CandidateSummary,        # ToolSpec.summary()-derived candidate
    ContractDetail,          # selected contract, schemas expanded only here
    DiscoveryContractError,  # stable reason code, never a tool status
    DiscoveryDiagnostic,     # structured query-layer fact
    DiscoveryErrorDocument,  # query error shape, apart from ToolResult
    DiscoveryPage,           # result envelope with paging/diagnostics
    DiscoveryQuery,          # caller-side filter facts
    GroupMember,             # capability reference inside a group
    GroupSummary,            # disclosure-bounded group summary
    compose_access_id,       # "<catalog_ref>:<tool_id>@<entry_key>"
)
CandidateSummary.from_spec(spec, *, provider, catalog_ref, environments=None,
                           group_id=None, matched_alias=None, asset_id=None)
X.document() -> dict        # canonical bounded JSON object
X.from_document(value)      # strict parse; raises DiscoveryContractError(.code)
```

Enums and JSON Schemas are module constants (`EFFECTS`, `ASSEMBLY_STATES`,
`BINDING_STATES`, `SCOPE_STATES`, `ADMISSION_STATES`, `AVAILABILITY_STATES`,
`DIAGNOSTIC_CODES`, `ERROR_CODES`, `ITEM_KINDS`, `*_SCHEMA`) — import them from
`vesryn_tool_runtime.discovery_contracts` rather than restating them.

## Envelope, versioning and value rules

Every document is `{"schema_version": 1, "kind": <kind>, …}` with `kind` one of
`discovery-query`, `discovery-page`, `group-summary`, `candidate-summary`,
`access-entry-summary`, `contract-detail`, `discovery-diagnostic`,
`discovery-error`.

- **Unknown fields are rejected** (JSON Schema `additionalProperties: false`
  plus strict-key construction). There are no old callers today; a future field
  set ships as a new `schema_version` with an explicit migration, never as a
  silent addition.
- **Null is never used.** Not-applicable facts are *omitted*; unknown facts are
  *explicit enum values*. Empty lists occur only where "genuinely empty" is
  meaningful (a result page with zero items); `aliases`, `diagnostics`,
  `next_offset` and optional match facts are omitted when absent.
- **Unknown never means success.** Defaults are the safe states:
  `assembly="unknown"`, `binding="not_provided"`,
  `execution_admission="not_evaluated"`, `availability="unknown"`.
  `discovery_scope` has **no** default — a disclosure claim must be stated.
- **No identity is generated here.** `discovery_id` only passes through a
  caller-provided correlation string; documents carry no content-derived IDs.
- Documents are finite bounded JSON; use the existing `documents` helpers for
  canonical bytes/digests.

## Identity decisions

**`catalog_ref`** — a NAME (`^[a-z][a-z0-9-]*$`) the trusted host gives to one
explicitly composed Catalog. Source: host naming its own inputs. Lifecycle:
host-owned, stable for as long as the host keeps using that Catalog; resolution
scope: only Catalogs the host explicitly supplies to a query. It names actual
inputs — there is no global registry and no entry registration service.

**`group_id`** — the `domain.group` tool-ID grammar (e.g. `python.quality`),
unique within a `catalog_ref`. The same `group_id` with a different definition
is a conflict (`conflicting_identity`); version, membership or alias changes
never reassign it. Aliases never create capability identities.

**`entry_key`** — a NAME the host gives to one logical entry of a capability
within a Catalog (e.g. `default`, `dagger-native`). Source and lifecycle:
host-owned and stable across version, contract-digest, binding, address,
path and install-location changes — those live in separate fields.

**`access_id`** — exactly `compose_access_id(catalog_ref, tool_id, entry_key)` =
`"<catalog_ref>:<tool_id>@<entry_key>"` (e.g. `ci:python.dead-code@default`).
Unique within a page/result set; duplicates are `conflicting_identity`. It is
never derived from a parameterized `binding_id`, a query-generated ID, an
Adapter object address, an absolute path or an install directory. Stability
example: bumping `contract_version` or `interface_sha256` never changes
`access_id`; renaming `entry_key` or `catalog_ref` is a host-decision identity
change. When a host cannot supply these names, the entry stays **unreported**
until it can — the field layer never guesses a mapping.

## Field dictionary

### DiscoveryQuery (`discovery-query`)

| Field | Type | Presence | Domain / rule |
| --- | --- | --- | --- |
| `query` | str ≤256 | optional | Free filter words; no permission effect. |
| `operation` | str ≤256 | optional | Operation keyword; matches existing `use_when`/`not_for` semantics. |
| `domain`, `environment` | NAME | optional | Exact labels, as in existing search. |
| `effect` | enum | optional | `read`/`check`/`write`. |
| `group_id` | `domain.group` | optional | Only when querying within a group. |
| `catalog_ref` | NAME | optional | Explicit catalog selection. |
| `offset` | int ≥0 | required (default 0) | |
| `limit` | int 1–50 | required (default 10) | Reuses the existing page bounds. |
| `discovery_id` | str ≤256 | optional | Passthrough of a caller-provided correlation only. |

### DiscoveryPage (`discovery-page`)

| Field | Type | Presence | Domain / rule |
| --- | --- | --- | --- |
| `item_kind` | enum | required | `candidate-summary` / `group-summary` / `access-entry-summary`; items are homogeneous. |
| `disclosure` | const | required | `summary`; details come from `ContractDetail`. |
| `offset`, `limit` | as query | required | Envelope slice facts. |
| `total` | int ≥0 | required | **Disclosable results only.** |
| `next_offset` | int ≥0 | optional | Omitted when no next page; must equal `offset+len(items)` when more exist. |
| `items` | list | required | Exactly `min(max(total−offset,0), limit)` items; unique identity per kind (`(catalog_ref, tool_id)` for candidates, `(catalog_ref, group_id)` for groups, `access_id` for entries); same `tool_id` under different `catalog_ref`s coexists. |
| `query` | document | required | The query this page answers. |
| `diagnostics` | list | optional | See below. |

### GroupSummary (`group-summary`)

| Field | Type | Presence | Domain / rule |
| --- | --- | --- | --- |
| `group_id`, `catalog_ref` | identity | required | See identity decisions. |
| `members` | list ≥1 | required | `GroupMember{tool_id, catalog_ref}` references only — no contracts, Adapters or schemas copied. Unique within the group. |
| `member_count` | int | required | Equals `len(members)`: only disclosable members appear, in list and count alike. |
| `display_name` ≤120, `description` ≤4096 | str | optional | |
| `aliases` | list of str ≤128, unique, ≤64 | optional | Match aids only; no new identity. |

### CandidateSummary (`candidate-summary`)

Every field of the existing `ToolSpec.summary()` — `tool_id`, optional
`display_name` (≤120), `description` (≤240), `domain`, `effect`,
`contract_version`, `contract_sha256` — plus:

| Field | Type | Presence | Domain / rule |
| --- | --- | --- | --- |
| `provider` | NAME | required | Existing `Catalog.provider_for` identity. |
| `catalog_ref` | NAME | required | Naming the actual input. |
| `environments` | list of NAME ≥1 | required | Applicable environments from the spec. |
| `group_id` | `domain.group` | conditional | Only when actually matched via that group path. |
| `matched_alias` | str ≤128 | conditional | Only when actually matched via that alias. |
| `asset_id` | token | conditional | Only when an asset is actually associated; pure-API capabilities have none. |

`CandidateSummary.from_spec` derives the summary fields from `ToolSpec.summary()`
itself — there is no second summary authority — and summaries never contain
`input_schema`/`output_schema`/`source`.

### AccessEntrySummary (`access-entry-summary`)

| Field | Type | Presence | Domain / rule |
| --- | --- | --- | --- |
| `access_id` | composed | required | See identity decisions; auto-composed when omitted. |
| `catalog_ref`, `tool_id`, `entry_key` | identity | required | Must compose to `access_id`. |
| `provider` | NAME | required | |
| `environment` | NAME | required | Actual execution environment. |
| `purpose` | str ≤1024 | required | Bounded purpose summary. |
| `contract_version`, `contract_sha256` | existing domains | required | Unchanged original semantics. |
| `source` | object | optional | Exactly `ToolSpec.source`: `{kind, identity, interface_sha256}`. |
| `discovery_scope` | `matched`/`excluded` | required | No default: a disclosure claim must be stated. Discoverability ≠ admission. |
| `assembly` | enum | required (default `unknown`) | `assembled` / `missing` / `unknown` — Adapter fact only. |
| `binding` | enum | required (default `not_provided`) | `not_provided`/`known_absent`/`pending_validation`/`valid`/`invalid`/`not_required`. |
| `binding_id` | token | conditional | Required exactly when `binding∈{pending_validation, valid, invalid}`; forbidden otherwise. A binding ID is never an entry identity. |
| `execution_admission` | enum | required (default `not_evaluated`) | `not_evaluated`/`admitted`/`rejected`; only an authority may state more. |
| `availability` | enum | required (default `unknown`) | `unknown`/`available`/`unavailable`; health is never probed here. |
| `reason_code` | diagnostic enum | conditional | Required exactly when `discovery_scope=excluded`, `execution_admission=rejected`, `binding=invalid` or `availability=unavailable`; forbidden otherwise. |

There is deliberately **no** combined `ready`/`callable`/`allowed` flag.

### ContractDetail (`contract-detail`)

`access_id`/`catalog_ref`/`tool_id`/`entry_key` plus `contract`: exactly the
existing `ToolSpec.document()` with `contract_sha256`, reconstructed through
`ToolSpec` itself so the digest and schema stay single-sourced. Input/output
schemas are expanded **only** at this level. A contract whose digest or
`tool_id` does not match, or that carries unknown keys, is `invalid_document`.

### DiscoveryDiagnostic / DiscoveryErrorDocument

`DiscoveryDiagnostic{code, detail?, ref?}` with `code` from `DIAGNOSTIC_CODES`
(`unregistered`, `undisclosed`, `scope_excluded`, `unassembled`,
`binding_invalid`, `binding_unverified`, `unavailable`, `unknown_input`,
`unknown`). `detail` (≤512) and `ref` (≤256) must never disclose hidden items —
no identifiers, reasons, totals or member lists of anything absent from the
same result; `ref` may only name an already-disclosed item.
`DiscoveryErrorDocument{code, detail?}` with `code` from `ERROR_CODES`
distinguishes query errors from `ToolResult` business statuses; raised
field-contract failures carry the same codes on `DiscoveryContractError.code`.

## Fact sources and permission boundaries

| Fact | Authority | When absent |
| --- | --- | --- |
| Candidate/contract fields | the actual `ToolSpec` | not representable — no invention |
| `provider` | `Catalog.provider_for` | required |
| `assembly` | the host's registration knowledge | `unknown` |
| `binding*` | an actual binding document supplied by the caller | `not_provided` |
| `discovery_scope` | the host's disclosure decision | must be stated |
| `execution_admission` | the existing Scope admission authority | `not_evaluated` |
| `availability` | the execution/backend authority | `unknown` |
| asset/selection facts | real `AssetSelection`/asset views | omitted |
| trusted security decisions | #13's policy system (not `AssetPolicy.enabled`) | omitted |

Filters, field constructors and schema reads never widen Scope or produce
admission proof; `total` counts only disclosable results.

## Ownership for later #14 tasks

This task uniquely owns `src/vesryn_tool_runtime/discovery_contracts.py`,
`tests/test_discovery_contracts.py`, `docs/discovery-contracts.md`, the new
exports in `__init__.py` and this documentation link. Later #14 sub-tasks
(group retrieval, scope diagnostics, entry queries) own only their own new
modules/tests/docs and reference this contract instead of copying it; changes
to the shared fields go back through this task/#14 once.
