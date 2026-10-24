"""Immutable CLI distribution definitions and deterministic, side-effect-free choices."""

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .documents import ToolRuntimeError, digest
from .schemas import NAME, TOOL, validate


class AssetError(ToolRuntimeError):
    """A stable asset reason code, independent of execution or backend readiness."""

    def __init__(self, code):
        self.code = code
        super().__init__(f"Tool asset: {code}")


def _token(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", value
    ):
        raise AssetError("invalid_definition")


def _sha256(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AssetError("invalid_digest")


def _specifier(value):
    if not isinstance(value, str) or len(value) > 512:
        raise AssetError("invalid_requirement")
    try:
        return SpecifierSet(value)
    except InvalidSpecifier:
        raise AssetError("invalid_requirement") from None


def _contains(specifier, version):
    if not specifier:
        return True
    try:
        return _specifier(specifier).contains(version, prereleases=True)
    except InvalidVersion:
        return False


@dataclass(frozen=True)
class AssetTarget:
    os: str
    arch: str
    abi: str | None = None
    python: str | None = None

    def __post_init__(self):
        for value in (self.os, self.arch):
            _token(value)
            if value == "any":
                raise AssetError("invalid_target")
        if self.abi is not None:
            _token(self.abi)
        if self.python is not None:
            try:
                Version(self.python)
            except InvalidVersion, TypeError:
                raise AssetError("invalid_target") from None

    def document(self):
        return asdict(self)


@dataclass(frozen=True)
class AssetRelease:
    """One publisher-declared artifact; version is separate from tool contracts."""

    version: str
    distribution: str
    backend: str
    source: str
    sha256: str
    entrypoint: str
    os: str = "any"
    arch: str = "any"
    abi: str | None = None
    requires_python: str | None = None
    package: str | None = None
    lock_ref: str | None = None

    def __post_init__(self):
        for value in (self.version, self.entrypoint, self.os, self.arch):
            _token(value)
        if self.version.casefold() in {"latest", "stable", "default", "current"}:
            raise AssetError("mutable_version")
        _sha256(self.sha256)
        if not isinstance(self.distribution, str) or not isinstance(self.backend, str):
            raise AssetError("invalid_backend")
        if {"python": "uv", "native": "aria2", "oci": "oci"}.get(
            self.distribution
        ) != self.backend:
            raise AssetError("invalid_backend")
        if not isinstance(self.source, str) or not 1 <= len(self.source) <= 2048:
            raise AssetError("invalid_source")
        if self.distribution == "oci":
            if not self.source.endswith("@sha256:" + self.sha256):
                raise AssetError("mutable_source")
        else:
            try:
                source = urlsplit(self.source)
            except ValueError:
                raise AssetError("invalid_source") from None
            if (
                source.scheme not in {"https", "file"}
                or (source.scheme == "https" and not source.netloc)
                or source.username is not None
                or source.password is not None
                or source.query
                or source.fragment
            ):
                raise AssetError("invalid_source")
        if self.distribution != "python" and "any" in (self.os, self.arch):
            raise AssetError("invalid_target")
        if self.abi is not None:
            _token(self.abi)
        if self.distribution == "python":
            if self.package is None or self.requires_python is None:
                raise AssetError("invalid_definition")
            _token(self.package)
            _specifier(self.requires_python)
        elif self.package is not None or self.requires_python is not None:
            raise AssetError("invalid_definition")
        if self.lock_ref is not None and (
            not isinstance(self.lock_ref, str) or not 1 <= len(self.lock_ref) <= 512
        ):
            raise AssetError("invalid_definition")

    def matches(self, target):
        return (
            self.os in {"any", target.os}
            and self.arch in {"any", target.arch}
            and (self.abi is None or self.abi == target.abi)
            and (
                self.requires_python is None
                or (
                    target.python is not None
                    and _contains(self.requires_python, target.python)
                )
            )
        )

    def document(self):
        return asdict(self)


@dataclass(frozen=True)
class AssetDefinition:
    asset_id: str
    catalog_revision: str
    releases: tuple[AssetRelease, ...]

    def __post_init__(self):
        _token(self.asset_id)
        _token(self.catalog_revision)
        if (
            not isinstance(self.releases, tuple)
            or not self.releases
            or any(not isinstance(item, AssetRelease) for item in self.releases)
            or len({digest(item.document()) for item in self.releases})
            != len(self.releases)
        ):
            raise AssetError("invalid_definition")

    def document(self):
        return {
            "asset_id": self.asset_id,
            "catalog_revision": self.catalog_revision,
            "releases": [item.document() for item in self.releases],
        }

    @property
    def sha256(self):
        return digest(self.document())


@dataclass(frozen=True)
class AssetPolicy:
    revision: str
    enabled: bool = True
    specifier: str = ""

    def __post_init__(self):
        _token(self.revision)
        if type(self.enabled) is not bool:
            raise AssetError("invalid_policy")
        _specifier(self.specifier)

    def document(self):
        return asdict(self)


@dataclass(frozen=True)
class AssetSelection:
    tool_id: str
    provider: str | None
    tool_contract_sha256: str
    asset_id: str
    catalog_revision: str
    definition_sha256: str
    target: AssetTarget
    policy: AssetPolicy
    release: AssetRelease
    version: str | None = None
    specifier: str = ""

    def __post_init__(self):
        validate(self.tool_id, TOOL, label="asset capability")
        for value in (self.asset_id, self.catalog_revision):
            _token(value)
        if self.provider is not None:
            validate(self.provider, NAME, label="asset capability Provider")
        _sha256(self.tool_contract_sha256)
        _sha256(self.definition_sha256)
        if not isinstance(self.target, AssetTarget) or not isinstance(
            self.policy, AssetPolicy
        ):
            raise AssetError("invalid_selection")
        if not isinstance(self.release, AssetRelease):
            raise AssetError("invalid_selection")
        if self.version is not None:
            _token(self.version)
        _specifier(self.specifier)
        if (
            not self.policy.enabled
            or not self.release.matches(self.target)
            or (self.version is not None and self.release.version != self.version)
            or not _contains(self.specifier, self.release.version)
            or not _contains(self.policy.specifier, self.release.version)
        ):
            raise AssetError("invalid_selection")

    @property
    def artifact_id(self):
        """Installed content can be shared across consumers and policy revisions."""
        return digest(
            {
                "asset_id": self.asset_id,
                "target": self.target.document(),
                "release": self.release.document(),
            }
        )

    def document(self):
        value = {"schema_version": 1, "kind": "tool-asset-selection", **asdict(self)}
        value["selection_id"] = digest(value)
        return value

    @property
    def selection_id(self):
        return self.document()["selection_id"]

    @classmethod
    def from_document(cls, value):
        """Read a frozen old choice without consulting today's default or index."""
        try:
            value = dict(value)
            identity = value.pop("selection_id")
            if (
                type(value.get("schema_version")) is not int
                or value.pop("schema_version") != 1
                or value.pop("kind") != "tool-asset-selection"
                or digest(
                    {"schema_version": 1, "kind": "tool-asset-selection", **value}
                )
                != identity
            ):
                raise AssetError("invalid_selection")
            return cls(
                **{
                    **value,
                    "target": AssetTarget(**value["target"]),
                    "policy": AssetPolicy(**value["policy"]),
                    "release": AssetRelease(**value["release"]),
                }
            )
        except TypeError, KeyError, ValueError:
            raise AssetError("invalid_selection") from None


def select_asset(
    catalog, tool_id, *, target, policy, version=None, specifier="", scope=None
):
    """Choose in publisher order; approval remains a policy, never a latest alias."""
    if not isinstance(target, AssetTarget) or not isinstance(policy, AssetPolicy):
        raise AssetError("invalid_selection")
    if version is not None:
        _token(version)
    _specifier(specifier)
    definition = catalog.asset_for(tool_id, scope=scope)
    if tool_id not in catalog._tools:
        # A frozen selection embeds a real contract hash and Provider; a tool
        # registered only as an asset has neither, and none may be invented.
        raise AssetError("unregistered_tool")
    if not policy.enabled:
        raise AssetError("selection_disabled")
    releases = [item for item in definition.releases if item.matches(target)]
    if not releases:
        raise AssetError("unsupported_target")
    for release in releases:
        if (
            (version is None or release.version == version)
            and _contains(specifier, release.version)
            and _contains(policy.specifier, release.version)
        ):
            return AssetSelection(
                tool_id,
                catalog.provider_for(tool_id),
                catalog.resolve(tool_id)[0].sha256,
                definition.asset_id,
                definition.catalog_revision,
                definition.sha256,
                target,
                policy,
                release,
                version,
                specifier,
            )
    raise AssetError("no_matching_version")


def asset_view(
    catalog, tool_id, *, target, policy, selection=None, index=None, scope=None
):
    """Available, Installed and caller-owned Selected are independent facts."""
    if not isinstance(target, AssetTarget) or not isinstance(policy, AssetPolicy):
        raise AssetError("invalid_selection")
    value = {
        "available": [],
        "installed": {
            "status": "not_selected" if index is not None else "not_configured"
        },
        "selected": None,
    }
    try:
        definition = catalog.asset_for(tool_id, scope=scope)
        value["available"] = [
            item.document() for item in definition.releases if item.matches(target)
        ]
        current = select_asset(
            catalog, tool_id, target=target, policy=policy, scope=scope
        )
        value["selection_status"] = "selectable"
    except AssetError as error:
        value["selection_status"] = error.code
        current = None
    if selection is not None:
        if not isinstance(selection, AssetSelection) or selection.tool_id != tool_id:
            raise AssetError("invalid_selection")
        if selection.target != target:
            raise AssetError("selection_target_mismatch")
        value["selected"] = selection.document()
    if index is not None and (selection is not None or current is not None):
        value["installed"] = index.installed(selection or current)
    value["policy"] = policy.document()
    return value
