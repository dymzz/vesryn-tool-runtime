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
