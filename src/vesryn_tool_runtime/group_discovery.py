"""Progressive group discovery: bounded summaries, member matching and continuation.

Groups are read from the existing Catalog registration; members are filtered by
the same Scope judgement as entry resolution (#34) before ordering and paging.
This module never expands a contract, downloads, installs, binds or executes:
summaries carry references and facts only, and a selected ``tool_id`` is handed
to ``resolve_tool_access`` for its contracts.
"""

import re

from .assets import AssetError
from .contracts import Catalog
from .discovery_contracts import (
    MAX_LIMIT,
    MIN_LIMIT,
    CandidateSummary,
    DiscoveryContractError,
    DiscoveryDiagnostic,
    DiscoveryPage,
    DiscoveryQuery,
    GroupMember,
    GroupSummary,
)
from .documents import WorkflowError
from .scope import DiscoveryScope

DEFAULT_MEMBERS = 5
MAX_MEMBERS = 50


def _fail(code):
    raise DiscoveryContractError(code)


def _page(offset, limit):
    if type(offset) is not int or offset < 0:
        _fail("invalid_query")
    if type(limit) is not int or not MIN_LIMIT <= limit <= MAX_LIMIT:
        _fail("invalid_query")


def _members_limit(value):
    if type(value) is not int or not 1 <= value <= MAX_MEMBERS:
        _fail("invalid_query")


def _query(catalog_ref, query, offset, limit):
    return DiscoveryQuery(
        query=query or "", catalog_ref=catalog_ref, offset=offset, limit=limit
    )


def _tokens(value):
    return [item for item in re.split(r"[^a-z0-9]+", value.lower()) if item]


def _matches(query, *values):
    """Every query token appears in the offered group/member text."""
    wanted = _tokens(query)
    if not wanted:
        return False
    haystack = " ".join(text for text in values if text).lower()
    return all(token in haystack for token in wanted)


def _matched_alias(query, aliases):
    if not query:
        return None
    for alias in aliases:
        if _matches(query, alias):
            return alias
    return None


def _spec_for(catalog, tool_id):
    try:
        return catalog.resolve(tool_id)[0]
    except WorkflowError:
        return None


def _visible_members(catalog, group, scope):
    """Registered members, filtered by the caller Scope before any ordering.

    An explicit availability set applies to every member. An asset-only member
    has no environment/effect fact to judge beyond that, so it stays a visible
    reference; it still gets no fabricated callable contract later.
    """
    visible = []
    for tool_id in group.members:
        if (
            scope is not None
            and scope.available is not None
            and tool_id not in scope.available
        ):
            continue
        spec = _spec_for(catalog, tool_id)
        if spec is None or scope is None or scope.decision(spec).matched:
            visible.append(tool_id)
    return visible


def _summary(catalog, group, catalog_ref, scope, limit):
    visible = _visible_members(catalog, group, scope)
    if not visible:
        return None, False
    disclosed = visible[:limit]
    members = tuple(GroupMember(tool_id, catalog_ref) for tool_id in disclosed)
    summary = GroupSummary(
        group.group_id,
        catalog_ref,
        members,
        len(members),
        display_name=group.display_name,
        description=group.description,
        aliases=group.aliases,
    )
    return summary, len(visible) > len(disclosed)


def _group_matches(group, query):
    return _matches(
        query,
        group.group_id,
        group.display_name,
        group.description,
        *group.aliases,
    )


def discover_groups(
    catalog,
    *,
    catalog_ref,
    scope,
    query="",
    offset=0,
    limit=10,
    members_limit=DEFAULT_MEMBERS,
):
    """Enumerate groups the caller may see; each summary carries a bounded member list.

    Groups whose members the caller Scope excludes are not disclosed at all, and
    their existence is not named in diagnostics or totals. A summary whose member
    list is bounded states that boundary through an ``undisclosed`` diagnostic
    naming the disclosed group; the rest is reachable through
    ``discover_group_members``.
    """
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Group discovery needs the existing Catalog contract")
    _page(offset, limit)
    _members_limit(members_limit)
    if scope is not None and not isinstance(scope, DiscoveryScope):
        _fail("invalid_query")
    requested = _query(catalog_ref, query, offset, limit)

    summaries = []
    truncated = {}
    for group in catalog.groups():
        if query and not _group_matches(group, query):
            continue
        summary, bounded = _summary(catalog, group, catalog_ref, scope, members_limit)
        if summary is None:
            continue
        summaries.append(summary)
        truncated[summary.group_id] = bounded
    summaries.sort(key=lambda item: item.group_id)

    selected = tuple(summaries[offset : offset + limit])
    diagnostics = tuple(
        DiscoveryDiagnostic(
            "undisclosed",
            detail="member list is bounded; use group member discovery for the rest",
            ref=item.group_id,
        )
        for item in selected
        if truncated[item.group_id]
    )
    next_offset = offset + limit if offset + limit < len(summaries) else None
    return DiscoveryPage(
        "group-summary",
        offset,
        limit,
        len(summaries),
        requested,
        selected,
        diagnostics,
        next_offset,
    )


def group_summary(catalog, group_id, *, catalog_ref, scope, members_limit=MAX_MEMBERS):
    """One known group by identity, with its visible members in registration order."""
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Group discovery needs the existing Catalog contract")
    _members_limit(members_limit)
    if scope is not None and not isinstance(scope, DiscoveryScope):
        _fail("invalid_query")
    _query(catalog_ref, "", 0, MIN_LIMIT)
    try:
        group = catalog.group_for(group_id)
    except WorkflowError:
        raise DiscoveryContractError("unknown_reference") from None
    summary, _bounded = _summary(catalog, group, catalog_ref, scope, members_limit)
    if summary is None:
        raise DiscoveryContractError("unknown_reference")
    return summary


def discover_group_members(
    catalog,
    group_id,
    *,
    catalog_ref,
    scope,
    query="",
    offset=0,
    limit=10,
):
    """Bounded member candidates of one known group, matched by purpose or alias.

    The returned items are the existing #27 ``CandidateSummary`` documents: they
    carry the tool id, the group context and the matched alias instead of any
    parameter Schema. Members without a registered callable contract are counted
    out with an aggregate diagnostic and never named.
    """
    if not isinstance(catalog, Catalog):
        raise WorkflowError("Group discovery needs the existing Catalog contract")
    _page(offset, limit)
    if scope is not None and not isinstance(scope, DiscoveryScope):
        _fail("invalid_query")
    requested = _query(catalog_ref, query, offset, limit)
    try:
        group = catalog.group_for(group_id)
    except WorkflowError:
        raise DiscoveryContractError("unknown_reference") from None

    candidates = []
    missing = 0
    for tool_id in group.members:
        spec = _spec_for(catalog, tool_id)
        if spec is None:
            missing += 1
            continue
        if scope is not None and not scope.decision(spec).matched:
            continue
        provider = catalog.provider_for(tool_id)
        if provider is None:
            missing += 1
            continue
        asset_id = None
        try:
            asset_id = catalog.asset_for(tool_id).asset_id
        except AssetError:
            pass
        matched_alias = _matched_alias(query, group.aliases)
        candidate = CandidateSummary.from_spec(
            spec,
            provider=provider,
            catalog_ref=catalog_ref,
            group_id=group.group_id,
            matched_alias=matched_alias,
            asset_id=asset_id or None,
        )
        if query and not _matches(
            query,
            candidate.tool_id,
            candidate.description,
            candidate.domain,
            candidate.display_name,
            group.description,
            *group.aliases,
        ):
            continue
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.tool_id)
    selected = tuple(candidates[offset : offset + limit])
    diagnostics = ()
    if missing:
        diagnostics = (
            DiscoveryDiagnostic(
                "unregistered",
                detail="some group members have no registered callable contract",
            ),
        )
    next_offset = offset + limit if offset + limit < len(candidates) else None
    return DiscoveryPage(
        "candidate-summary",
        offset,
        limit,
        len(candidates),
        requested,
        selected,
        diagnostics,
        next_offset,
    )
