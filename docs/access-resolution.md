# Access entry resolution and Scope facts (TR-DISC-01D)

Public handoff for [issue #34](https://github.com/dymzz/vesryn-tool-runtime/issues/34)
(TR-DISC-01D / 14-D, child of [#14](https://github.com/dymzz/vesryn-tool-runtime/issues/14)),
built on the field contracts of [#27](https://github.com/dymzz/vesryn-tool-runtime/issues/27)
and the unified registration of [#32](https://github.com/dymzz/vesryn-tool-runtime/issues/32).
It reads registration and contract facts; it never executes, installs, probes,
binds or loads a Dagger module.

## Public signatures

```python
ScopeDecision(matched, reason=None)          # .state -> "matched" | "excluded"
DiscoveryScope.decision(spec) -> ScopeDecision
Catalog.has_tool(tool_id) -> bool
Catalog.accesses_for(tool_id) -> tuple[AccessEntrySummary, ...]
AccessResolution.document() -> dict
resolve_tool_access(catalog, tool_id, *, scope, offset=0, limit=10,
                    include_contracts=True) -> AccessResolution
resolve_access(catalog, access_id, *, scope,
               include_contracts=True) -> AccessResolution
```

`scope` is the host's existing `DiscoveryScope`; `None` means "no caller filter",
not "everything is allowed". `offset` is ≥ 0 and `limit` is 1–50, the existing
discovery bounds.

## What a resolution states

- `entries` — registered `AccessEntrySummary` records the host disclosed
  (`discovery_scope="matched"`) and the caller's Scope includes. Ordering is by
  access identity, so paging is stable.
- `contracts` — one `ContractDetail` per returned entry, expanded from the
  **registered** `ToolSpec` document plus its digest. There is no second Schema,
  no renamed tool and no copied parameter type. Requesting contracts is explicit
  (`include_contracts=True` by default).
- `total`/`next_offset` — count and continuation over disclosed entries only.
  Hidden or scope-excluded entries never inflate a page or its count.
- `incomplete` — `True` only when a requested contract could not be verified
  against the registered tool contract. It never means "ready".
- `diagnostics` — `DiscoveryDiagnostic` records: `undisclosed` (the tool has
  entries the host did not disclose), `scope_excluded` (the caller's own
  constraint, with the constraint name), `unregistered` (registered tool with no
  access entry), `unknown` (missing or stale contract fact) and the recorded entry
  facts `unassembled`, `binding_invalid`, `unavailable`. A `ref` may only name an
  entry already present in the same result; hidden identifiers are never included.

Unknown `tool_id` or `access_id` raises `DiscoveryContractError("unknown_reference")`;
invalid paging or non-Catalog input raises the existing explicit codes. No new
error family or "ready" flag is introduced.

## Scope is one judgement

`DiscoveryScope.decision(spec)` is now the single Scope authority: it returns
`ScopeDecision(matched, reason)` where `reason` is one of `environment`, `effect`,
`availability` or `constraint`. `DiscoveryScope.matches` delegates to it, and
later group discovery (#35) and invocation evidence (#15) consume the same
decision instead of re-implementing qualification or parsing exception text.
A matched decision is still not admission; `admit` keeps its existing rule.

## Access identity

`access_id` is the host-registered identity of one entry. The composed default
`compose_access_id(catalog_ref, tool_id, entry_key)` is still used when a host
omits it, but it is no longer the only accepted shape: a host may register its
own bounded identity such as `trivy.scan` (the shape #34 asks for). Existing
composed identities stay valid; this is an additive relaxation of the #27 field
rule, not a new identity family. The `catalog_ref`/`tool_id`/`entry_key` fields
stay recorded as provenance and are never recomputed from paths or parameters.

One tool keeps one `ToolSpec` contract: entries are access paths to that same
contract (for example two entry keys or two catalogs). Two entries do not create
two tool identities, and an entry whose recorded `contract_sha256` differs from
the registered contract is reported as `unknown`, never silently expanded.

## Real contract evidence

The resolution tests use a saved, unmodified Dagger introspection snapshot of the
engineering-ci module:

- Module revision `github.com/dymzz/engineering-ci@9949e22dc03e4361bb46540ca5a4d51c1cefd3ae`
  (branch `codex/eci-056-trusted-policy`), function
  `EngineeringCi.repositoryTestArtifacts` (`main.py:122`), recorded with Dagger
  `1.0.0-beta.16`.
- Snapshot kept as `tests/fixtures/dagger/engineering-ci-9949e22.schema.json.gz`;
  the canonical JSON SHA-256 and the exposures document are recorded in
  [the verification record](../verification/tr-disc-01d.json).
- The mapped contract digest and interface digest are produced by the existing
  `dagger_discovery.discover`, so the test proves entry/contract mapping, not
  execution. The tool is registered under the real capability-style id
  `pytest.artifacts`; no bare tool id is renamed into a contract.

## Boundaries

- Queries perform no subprocess, Dagger call, download, install, binding write,
  health probe or backend switch. A test patches `subprocess.run` to fail and
  still resolves entries.
- A registered asset-only tool (for example `trivy`) resolves to zero entries and
  an `unregistered` diagnostic: it reports the absence instead of inventing an
  empty ToolSpec or a callable contract.
- `binding`, `execution_admission` and `availability` are returned exactly as
  recorded by the host; this task neither verifies a binding nor claims backend
  health. Missing facts stay `unknown`/`not_provided`/`not_evaluated`.
- Group matching, ranking and alias search stay with #35; Binding creation,
  admission and dispatch stay with #15. This module is their shared read path.

## Consumer handoff

- #35: after a group or direct query selects a `tool_id`, call
  `resolve_tool_access(catalog, tool_id, scope=scope)` once — the entries and
  contracts are returned together; no extra asset read is required.
- #15: call `resolve_access(catalog, access_id, scope=scope)` for a known entry,
  then create/verify the binding with the existing binding module. A resolvable
  contract grants no invocation right.
- Vesryn #31 maps the returned states (including diagnostics and `incomplete`)
  to its MCP protocol statuses; it must not re-derive Scope or parse messages.

Up: [Discovery field contracts](discovery-contracts.md) · [Documentation](README.md).
