"""TEMPORARY outermost converter from PR #28-era documents to the records.

This module exists only while the PR #28 deviation types are being replaced
(issue #27, reopened). It converts at the outermost boundary — the record
layer itself carries no compatibility. Once the affected tests and consumers
are adapted, THIS FILE IS DELETED; nothing else may import it except the
transition tests.

Conclusions it produces (per the acceptance requirement):
- old group-member documents convert: catalog_ref is dropped (namespace
  fact, not a record field), the member keeps tool_id and gains the
  summary text it already carried under another name where present;
- old access-summary documents DO NOT convert: they lack method and target,
  which the ToolAccess field table requires — the explicit conclusion is
  "unsupported", never a lossy guess.
"""

from .discovery_records import GroupMember, RecordError, ToolGroup

LEGACY_UNSUPPORTED = "unsupported"


def convert_legacy_group(document):
    """PR #28 group summary → ToolGroup; catalog_ref dropped with a note."""
    try:
        members = []
        for member in document["members"]:
            members.append(
                GroupMember(
                    member["tool_id"],
                    member.get("summary", "(legacy member without summary)"),
                    tuple(member.get("aliases", ())),
                )
            )
        return ToolGroup(
            document["group_id"], document.get("summary", ""), tuple(members)
        )
    except KeyError, TypeError, RecordError:
        return LEGACY_UNSUPPORTED


def convert_legacy_access(document):
    """PR #28 access summary → ToolAccess is impossible: no method/target."""
    if "method" not in document or "target" not in document:
        return LEGACY_UNSUPPORTED
    return LEGACY_UNSUPPORTED
