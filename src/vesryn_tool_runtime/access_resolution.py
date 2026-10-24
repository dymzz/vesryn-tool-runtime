"""Scope-filtered access entry resolution with bounded, non-leaking diagnostics.

A tool id names an already registered tool; an access id names one of its
registered entries. Resolution reads registration facts only: no Dagger query,
download, install, health probe, binding write or backend switch happens here,
and a resolvable contract never means the backend is ready or the entry is
admitted for execution.
"""

from dataclasses import dataclass

from .contracts import Catalog
from .discovery_contracts import (
    MAX_LIMIT,
    MIN_LIMIT,
    AccessEntrySummary,
    ContractDetail,
    DiscoveryContractError,
    DiscoveryDiagnostic,
)
from .documents import WorkflowError
from .scope import DiscoveryScope


def _fail(code):
    raise DiscoveryContractError(code)


def _identifier(value):
    return isinstance(value, str) and 1 <= len(value) <= 256


def _page(offset, limit):
    if type(offset) is not int or offset < 0:
        _fail("invalid_query")
    if type(limit) is not int or not MIN_LIMIT <= limit <= MAX_LIMIT:
        _fail("invalid_query")


@dataclass(frozen=True)
class AccessResolution:
    """One bounded answer: disclosed entries, their contracts and diagnostics.

    ``total`` and ``next_offset`` count only disclosed entries, so paging never
    hides an undisclosed or scope-excluded entry behind an incomplete page.
    ``incomplete`` is stated when a requested contract could not be verified
    against the registered tool contract; it is never used to imply success.
    """

    tool_id: str | None
    access_id: str | None
    entries: tuple[AccessEntrySummary, ...]
    contracts: tuple[ContractDetail, ...]
    diagnostics: tuple[DiscoveryDiagnostic, ...]
    total: int
    offset: int
    limit: int
    next_offset: int | None = None
    incomplete: bool = False

    def document(self):
        value = {
            "tool_id": self.tool_id,
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "incomplete": self.incomplete,
            "entries": [entry.document() for entry in self.entries],
        }
        if self.access_id is not None:
            value["access_id"] = self.access_id
        if self.next_offset is not None:
            value["next_offset"] = self.next_offset
        if self.contracts:
            value["contracts"] = [contract.document() for contract in self.contracts]
        if self.diagnostics:
            value["diagnostics"] = [
                diagnostic.document() for diagnostic in self.diagnostics
            ]
        return value


def _contract(entry, spec):
    """Expand exactly the registered ToolSpec document; no second Schema."""
    return ContractDetail(
        entry.tool_id,
        entry.catalog_ref,
        entry.entry_key,
        {**spec.document(), "contract_sha256": spec.sha256},
        access_id=entry.access_id,
    )


def _entry_diagnostics(entries):
    """Facts already recorded on disclosed entries; ``ref`` names a disclosed id."""
    diagnostics = []
    for entry in entries:
        if entry.assembly == "missing":
            diagnostics.append(DiscoveryDiagnostic("unassembled", ref=entry.access_id))
        if entry.binding == "invalid":
            diagnostics.append(
                DiscoveryDiagnostic("binding_invalid", ref=entry.access_id)
            )
        if entry.availability == "unavailable":
            diagnostics.append(DiscoveryDiagnostic("unavailable", ref=entry.access_id))
    return diagnostics


def _spec_for(catalog, tool_id):
    """The registered ToolSpec, or ``None`` for an asset-only tool record."""
    try:
        return catalog.resolve(tool_id)[0]
    except WorkflowError:
        return None


def _empty(tool_id, access_id, diagnostics, *, offset=0, limit=1, incomplete=False):
    return AccessResolution(
        tool_id,
        access_id,
        (),
        (),
        tuple(diagnostics),
        0,
        offset,
        limit,
        None,
        incomplete,
    )


def resolve_tool_access(
    catalog, tool_id, *, scope, offset=0, limit=10, include_contracts=True
):
    """Entries of one registered tool that the caller's Scope may see.

    The host-declared ``discovery_scope`` and the caller's live Scope are
    applied before ordering and paging. Entries the host did not disclose, and
    entries the caller's Scope excludes, are never named in diagnostics; only
    an aggregate reason is stated. A registered tool with no entry, an
    asset-only tool and a contract whose digest no longer matches each keep an
    explicit, non-invented answer.
    """
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Access resolution needs the existing Catalog contract")
    if not _identifier(tool_id):
        _fail("invalid_query")
    _page(offset, limit)
    if scope is not None and not isinstance(scope, DiscoveryScope):
        _fail("invalid_query")
    if type(include_contracts) is not bool:
        _fail("invalid_query")
    if not catalog.has_tool(tool_id):
        raise DiscoveryContractError("unknown_reference")

    registered = catalog.accesses_for(tool_id)
    disclosed = tuple(
        entry for entry in registered if entry.discovery_scope == "matched"
    )
    hidden = len(registered) - len(disclosed)
    diagnostics = []
    if hidden:
        diagnostics.append(
            DiscoveryDiagnostic(
                "undisclosed", detail="this tool has entries the host did not disclose"
            )
        )
    if not registered:
        return _empty(
            tool_id,
            None,
            [
                DiscoveryDiagnostic(
                    "unregistered", detail="no access entry is registered"
                )
            ],
            offset=offset,
            limit=limit,
        )
    if not disclosed:
        return _empty(tool_id, None, diagnostics, offset=offset, limit=limit)

    spec = _spec_for(catalog, tool_id)
    if spec is None:
        entries = disclosed[offset : offset + limit]
        return AccessResolution(
            tool_id,
            None,
            entries,
            (),
            (
                *diagnostics,
                DiscoveryDiagnostic(
                    "unknown",
                    detail="the tool has no registered contract to compare entries with",
                ),
            ),
            len(disclosed),
            offset,
            limit,
            offset + limit if offset + limit < len(disclosed) else None,
            True,
        )

    decision = scope.decision(spec) if scope is not None else None
    if decision is not None and not decision.matched:
        return _empty(
            tool_id,
            None,
            [
                DiscoveryDiagnostic(
                    "scope_excluded",
                    detail="the tool entries are outside the caller scope"
                    + (f" ({decision.reason})" if decision.reason else ""),
                )
            ],
            offset=offset,
            limit=limit,
        )

    entries = disclosed[offset : offset + limit]
    contracts = []
    incomplete = False
    for entry in entries:
        if not include_contracts:
            continue
        if entry.contract_sha256 != spec.sha256:
            incomplete = True
            diagnostics.append(
                DiscoveryDiagnostic(
                    "unknown",
                    detail="the entry contract does not match the registered tool contract",
                    ref=entry.access_id,
                )
            )
            continue
        contracts.append(_contract(entry, spec))
    diagnostics.extend(_entry_diagnostics(entries))
    next_offset = offset + limit if offset + limit < len(disclosed) else None
    return AccessResolution(
        tool_id,
        None,
        entries,
        tuple(contracts),
        tuple(diagnostics),
        len(disclosed),
        offset,
        limit,
        next_offset,
        incomplete,
    )


def resolve_access(catalog, access_id, *, scope, include_contracts=True):
    """One registered entry by its access identity, with the same Scope facts."""
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Access resolution needs the existing Catalog contract")
    if not _identifier(access_id):
        _fail("invalid_query")
    if scope is not None and not isinstance(scope, DiscoveryScope):
        _fail("invalid_query")
    if type(include_contracts) is not bool:
        _fail("invalid_query")
    try:
        entry = catalog.access_for(access_id)
    except WorkflowError:
        raise DiscoveryContractError("unknown_reference") from None
    if entry.discovery_scope != "matched":
        return _empty(
            entry.tool_id,
            access_id,
            [
                DiscoveryDiagnostic(
                    "undisclosed", detail="the host did not disclose this entry"
                )
            ],
        )

    spec = _spec_for(catalog, entry.tool_id)
    if spec is None:
        return AccessResolution(
            entry.tool_id,
            access_id,
            (entry,),
            (),
            (
                DiscoveryDiagnostic(
                    "unknown",
                    detail="the tool has no registered contract to compare the entry with",
                ),
            ),
            1,
            0,
            1,
            None,
            True,
        )
    decision = scope.decision(spec) if scope is not None else None
    if decision is not None and not decision.matched:
        return _empty(
            entry.tool_id,
            access_id,
            [
                DiscoveryDiagnostic(
                    "scope_excluded",
                    detail="the entry is outside the caller scope"
                    + (f" ({decision.reason})" if decision.reason else ""),
                )
            ],
        )
    if include_contracts and entry.contract_sha256 != spec.sha256:
        return AccessResolution(
            entry.tool_id,
            access_id,
            (entry,),
            (),
            (
                DiscoveryDiagnostic(
                    "unknown",
                    detail="the entry contract does not match the registered tool contract",
                    ref=entry.access_id,
                ),
            ),
            1,
            0,
            1,
            None,
            True,
        )
    contracts = (_contract(entry, spec),) if include_contracts else ()
    return AccessResolution(
        entry.tool_id,
        access_id,
        (entry,),
        contracts,
        tuple(_entry_diagnostics((entry,))),
        1,
        0,
        1,
        None,
        False,
    )
