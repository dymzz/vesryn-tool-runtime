"""ToolAsset / ToolGroup / ToolAccess field contracts (issue #27, reopened).

Every field of the issue's field tables is defined exactly once here: the
three records, their sub-records, the public enums and the SQLite DDL whose
columns and constraints carry the same fields — enums are CHECK constraints,
required fields are NOT NULL, the primary keys are tool_id / group_id /
access_id, versions form their own table keyed by tool identity, and group
members reference tools by foreign key. Storage I/O lives in record_store.py;
this module defines and validates records only.

tool_id is the global tool identity used as registered: renaming, new
versions, new platforms, new groups and new entries never allocate another
identity, and a local install path never becomes one. Registration states a
fact about tooling — not installation, authorization or execution.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from .documents import ToolRuntimeError, canonical

PROVIDERS = ("uv", "github-release", "oci")
DIGEST_TYPES = ("sha256",)
METHODS = ("dagger", "uv", "native", "api")


class RecordError(ToolRuntimeError):
    """A stable record reason: conflicts, missing keys or invalid fields."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Tool record: {code}")


def _name(value, code, limit=256):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise RecordError(code)
    return value


def _enum(value, values, code):
    if value not in values:
        raise RecordError(code)
    return value


@dataclass(frozen=True)
class Platform:
    """The explicit os/arch representation of a platform-specific asset."""

    os: str
    arch: str

    def __post_init__(self):
        _name(self.os, "invalid_record", 64)
        _name(self.arch, "invalid_record", 64)


@dataclass(frozen=True)
class ToolAssetVersion:
    """One versioned artifact of a tool: never a new tool identity."""

    version: str
    source: str
    digest_type: str
    digest: str
    platform: Platform | None = None

    def __post_init__(self):
        _name(self.version, "invalid_record", 128)
        _name(self.source, "invalid_record", 2048)
        _enum(self.digest_type, DIGEST_TYPES, "invalid_record")
        _name(self.digest, "invalid_record", 256)
        if self.digest_type == "sha256" and len(self.digest) != 64:
            raise RecordError("invalid_record")
        if self.platform is not None and not isinstance(self.platform, Platform):
            raise RecordError("invalid_record")


@dataclass(frozen=True)
class ToolAsset:
    """Tool registration and asset source, keyed by the global tool identity."""

    tool_id: str
    name: str
    provider: str
    versions: tuple[ToolAssetVersion, ...]
    entrypoint: str
    package: str | None = None

    def __post_init__(self):
        _name(self.tool_id, "invalid_record", 256)
        _name(self.name, "invalid_record", 256)
        _enum(self.provider, PROVIDERS, "invalid_record")
        if (
            not isinstance(self.versions, tuple)
            or not self.versions
            or any(not isinstance(item, ToolAssetVersion) for item in self.versions)
        ):
            raise RecordError("invalid_record")
        identities = {
            (item.version, item.platform or ("", "")) for item in self.versions
        }
        if len(identities) != len(self.versions):
            raise RecordError("duplicate_version")
        _name(self.entrypoint, "invalid_record", 256)
        if self.package is not None:
            _name(self.package, "invalid_record", 256)


@dataclass(frozen=True)
class GroupMember:
    """One tool's place in one group; its summary and aliases live here."""

    tool_id: str
    summary: str
    aliases: tuple[str, ...] = ()

    def __post_init__(self):
        _name(self.tool_id, "invalid_record", 256)
        _name(self.summary, "invalid_record", 2048)
        if (
            not isinstance(self.aliases, tuple)
            or any(not isinstance(item, str) or not item for item in self.aliases)
            or len(set(self.aliases)) != len(self.aliases)
        ):
            raise RecordError("invalid_record")


@dataclass(frozen=True)
class ToolGroup:
    """An agent-facing discovery entry listing member tools."""

    group_id: str
    summary: str
    members: tuple[GroupMember, ...]

    def __post_init__(self):
        _name(self.group_id, "invalid_record", 256)
        _name(self.summary, "invalid_record", 4096)
        if (
            not isinstance(self.members, tuple)
            or not self.members
            or any(not isinstance(item, GroupMember) for item in self.members)
        ):
            raise RecordError("invalid_record")
        if len({item.tool_id for item in self.members}) != len(self.members):
            raise RecordError("duplicate_member")


@dataclass(frozen=True)
class ToolAccess:
    """One callable entry of a tool; a tool may have several."""

    access_id: str
    tool_id: str
    method: str
    target: str
    contract: Mapping
    summary: str

    def __post_init__(self):
        _name(self.access_id, "invalid_record", 256)
        _name(self.tool_id, "invalid_record", 256)
        _enum(self.method, METHODS, "invalid_record")
        _name(self.target, "invalid_record", 2048)
        if not isinstance(self.contract, Mapping):
            raise RecordError("invalid_record")
        canonical(dict(self.contract))
        _name(self.summary, "invalid_record", 2048)


# -- serialization ------------------------------------------------------------
#
# The records serialize themselves; the query layer carries these documents
# without inventing parallel summary types (single field source).


def _require(condition):
    if not condition:
        raise RecordError("invalid_record")


def _document_mapping(value):
    if not isinstance(value, Mapping):
        raise RecordError("invalid_record")
    return dict(value)


def _document_platform(value):
    if value is None:
        return None
    value = _document_mapping(value)
    _require(set(value) == {"os", "arch"})
    return Platform(value["os"], value["arch"])


def platform_document(platform):
    return None if platform is None else {"os": platform.os, "arch": platform.arch}


class _RecordDocument:
    """Shared document()/from_document plumbing for the three records."""

    def document(self):
        raise NotImplementedError

    @classmethod
    def from_document(cls, document):
        raise NotImplementedError


def _asset_version_document(item):
    return {
        "version": item.version,
        "platform": platform_document(item.platform),
        "source": item.source,
        "digest_type": item.digest_type,
        "digest": item.digest,
    }


def _asset_version_from_document(value):
    value = _document_mapping(value)
    _require(set(value) == {"version", "platform", "source", "digest_type", "digest"})
    return ToolAssetVersion(
        value["version"],
        value["source"],
        value["digest_type"],
        value["digest"],
        _document_platform(value["platform"]),
    )


def _tool_asset_document(asset):
    value = {
        "tool_id": asset.tool_id,
        "name": asset.name,
        "provider": asset.provider,
        "versions": [_asset_version_document(item) for item in asset.versions],
        "entrypoint": asset.entrypoint,
    }
    if asset.package is not None:
        value["package"] = asset.package
    return value


def _tool_asset_from_document(value):
    value = _document_mapping(value)
    fields = {"tool_id", "name", "provider", "versions", "entrypoint", "package"}
    _require(
        set(value) <= fields
        and {"tool_id", "name", "provider", "versions", "entrypoint"} <= set(value)
    )
    versions = value["versions"]
    _require(isinstance(versions, list) and versions)
    return ToolAsset(
        value["tool_id"],
        value["name"],
        value["provider"],
        tuple(_asset_version_from_document(item) for item in versions),
        value["entrypoint"],
        package=value.get("package"),
    )


def _group_member_document(member):
    return {
        "tool_id": member.tool_id,
        "summary": member.summary,
        "aliases": list(member.aliases),
    }


def _group_member_from_document(value):
    value = _document_mapping(value)
    _require(set(value) == {"tool_id", "summary", "aliases"})
    aliases = value["aliases"]
    _require(isinstance(aliases, list))
    return GroupMember(value["tool_id"], value["summary"], tuple(aliases))


def _tool_group_document(group):
    return {
        "group_id": group.group_id,
        "summary": group.summary,
        "members": [_group_member_document(item) for item in group.members],
    }


def _tool_group_from_document(value):
    value = _document_mapping(value)
    _require(set(value) == {"group_id", "summary", "members"})
    members = value["members"]
    _require(isinstance(members, list) and members)
    return ToolGroup(
        value["group_id"],
        value["summary"],
        tuple(_group_member_from_document(item) for item in members),
    )


def _tool_access_document(access):
    return {
        "access_id": access.access_id,
        "tool_id": access.tool_id,
        "method": access.method,
        "target": access.target,
        "contract": dict(access.contract),
        "summary": access.summary,
    }


def _tool_access_from_document(value):
    value = _document_mapping(value)
    _require(
        set(value)
        == {"access_id", "tool_id", "method", "target", "contract", "summary"}
    )
    return ToolAccess(
        value["access_id"],
        value["tool_id"],
        value["method"],
        value["target"],
        _document_mapping(value["contract"]),
        value["summary"],
    )


def record_document(record):
    """Serialize one of the three records to its bounded JSON object."""
    if isinstance(record, ToolAsset):
        return _tool_asset_document(record)
    if isinstance(record, ToolGroup):
        return _tool_group_document(record)
    if isinstance(record, ToolAccess):
        return _tool_access_document(record)
    raise RecordError("invalid_record")


def record_from_document(document):
    """Parse one record document back into its record (strict round trip)."""
    value = _document_mapping(document)
    kinds = (
        (
            _tool_asset_from_document,
            {"tool_id", "name", "provider", "versions", "entrypoint"},
        ),
        (_tool_group_from_document, {"group_id", "summary", "members"}),
        (
            _tool_access_from_document,
            {"access_id", "tool_id", "method", "target", "contract", "summary"},
        ),
    )
    for parser, required in kinds:
        if required <= set(value):
            return parser(value)
    raise RecordError("invalid_record")
