"""One registration source for descriptors and replaceable tool implementations."""

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .documents import WorkflowError, digest
from .schemas import TOOL_DESCRIPTOR, check_schema, validate


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    input_schema: dict
    output_schema: dict
    contract_version: str = "1"
    effect: str = "check"
    recovery: str = "restartable"
    reuse: str = "verified_identity"
    environments: tuple[str, ...] = ("host",)
    description: str = ""
    domain: str = ""
    use_when: tuple[str, ...] = ()
    not_for: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    source: dict | None = None
    display_name: str = ""

    def document(self):
        value = {**asdict(self), "environments": list(self.environments)}
        for name in (
            "description",
            "domain",
            "use_when",
            "not_for",
            "tags",
            "source",
            "display_name",
        ):
            default = (
                None
                if name == "source"
                else ()
                if name in {"use_when", "not_for", "tags"}
                else ""
            )
            if value[name] == default:
                del value[name]
            elif isinstance(value[name], tuple):
                value[name] = list(value[name])
        return value

    @property
    def sha256(self):
        value = self.document()
        for name in (
            "description",
            "domain",
            "use_when",
            "not_for",
            "tags",
            "display_name",
        ):
            value.pop(name, None)
        return digest(value)

    def validate(self):
        validate(self.document(), TOOL_DESCRIPTOR, label="tool descriptor")
        if self.effect == "write" and self.recovery != "manual":
            raise WorkflowError("Write tools require domain-owned manual recovery")
        check_schema(self.input_schema)
        check_schema(self.output_schema)

    def summary(self):
        """First disclosure level: bounded purpose and identity, without Schemas."""
        return {
            "tool_id": self.tool_id,
            **({"display_name": self.display_name} if self.display_name else {}),
            "description": " ".join(self.description.split())[:240],
            "domain": self.domain,
            "effect": self.effect,
            "contract_version": self.contract_version,
            "contract_sha256": self.sha256,
        }


@dataclass
class ToolResult:
    status: str
    exit_code: int | None
    outputs: dict = field(default_factory=dict)
    executed: bool = False
    complete: bool = False
    current: bool = False
    reused: bool = False
    report_generated: bool = False
    reason: str | None = None
    summary: str | None = None

    def document(self):
        value = asdict(self)
        if self.summary is None:
            del value["summary"]
        return value


@dataclass(frozen=True)
class Invocation:
    step_id: str
    tool_id: str
    inputs: Any
    attempt: int
    previous: dict | None = None


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    generation_id: str
    definition_id: str
    run_dir: Path
    predecessors: Mapping


class ToolAdapter(Protocol):
    def invoke(
        self, calls: tuple[Invocation, ...], context: ExecutionContext
    ) -> dict[str, ToolResult]:
        """Execute an admitted ready batch; independently verify any previous evidence."""
        ...


class Catalog:
    def __init__(self):
        self._tools = {}
        self._providers = {}
        self._assets = {}
        self._tool_assets = {}
        self._groups = {}
        self._accesses = {}

    def register(self, spec: ToolSpec, adapter: ToolAdapter):
        spec = deepcopy(spec)
        spec.validate()
        if spec.tool_id in self._tools:
            raise WorkflowError("Duplicate tool registration")
        self._tools[spec.tool_id] = (spec, adapter)

    def _known_tools(self):
        return self._tools.keys() | self._tool_assets.keys()

    def register_asset(self, definition, *, tools):
        """Register one immutable CLI release definition under tool primary keys.

        Tools are registered directly by their primary keys; a capability
        contract (ToolSpec/adapter) is no longer a prerequisite. Registering
        an asset grants no installation, binding or execution; acquisition
        through a frozen selection still requires a registered capability.
        """
        from .assets import AssetDefinition, AssetError, _token

        tools = tuple(tools)
        if not isinstance(definition, AssetDefinition) or not tools:
            raise AssetError("invalid_definition")
        for tool_id in tools:
            _token(tool_id)
        existing = self._assets.get(definition.asset_id)
        if (existing is not None and existing != definition) or any(
            tool_id in self._tool_assets
            and self._tool_assets[tool_id] != definition.asset_id
            for tool_id in tools
        ):
            raise AssetError("conflicting_asset")
        self._assets[definition.asset_id] = definition
        self._tool_assets.update({tool_id: definition.asset_id for tool_id in tools})

    def register_tool(self, asset):
        """Register one ToolAsset record: a single tool primary key and its definition."""
        from .tool_registration import ToolAsset

        if not isinstance(asset, ToolAsset):
            raise WorkflowError("Tool assets register as ToolAsset records")
        self.register_asset(asset.definition, tools=(asset.tool_id,))

    def register_group(self, group):
        """Register a ToolGroup whose members reference tools by primary key."""
        from .tool_registration import ToolGroup

        if not isinstance(group, ToolGroup):
            raise WorkflowError("Tool groups register as ToolGroup records")
        unknown = [
            member for member in group.members if member not in self._known_tools()
        ]
        if unknown:
            raise WorkflowError(f"Tool group references unregistered tools: {unknown}")
        existing = self._groups.get(group.group_id)
        if existing is not None:
            if existing != group:
                raise WorkflowError("Duplicate tool group registration")
            return
        self._groups[group.group_id] = group

    def group_for(self, group_id):
        if group_id not in self._groups:
            raise WorkflowError(f"Tool group is not registered: {group_id}")
        return self._groups[group_id]

    def groups(self):
        """Registered group records in group-id order; a read, never a disclosure."""
        return tuple(self._groups[group_id] for group_id in sorted(self._groups))

    def register_access(self, access):
        """Register an access entry record (the #27 AccessEntrySummary)."""
        from .discovery_contracts import AccessEntrySummary

        if not isinstance(access, AccessEntrySummary):
            raise WorkflowError("Access entries register as AccessEntrySummary")
        if access.tool_id not in self._known_tools():
            raise WorkflowError(
                f"Access entry references an unregistered tool: {access.tool_id}"
            )
        existing = self._accesses.get(access.access_id)
        if existing is not None:
            if existing != access:
                raise WorkflowError("Duplicate access entry registration")
            return
        self._accesses[access.access_id] = access

    def access_for(self, access_id):
        if access_id not in self._accesses:
            raise WorkflowError(f"Access entry is not registered: {access_id}")
        return self._accesses[access_id]

    def has_tool(self, tool_id):
        """Whether a primary key names a registered capability or asset record."""
        return tool_id in self._known_tools()

    def accesses_for(self, tool_id):
        """Every registered access entry for one tool, in access-identity order.

        A read of registration facts only: it filters nothing, discloses nothing
        and never probes an adapter, backend or binding.
        """
        return tuple(
            self._accesses[access_id]
            for access_id in sorted(self._accesses)
            if self._accesses[access_id].tool_id == tool_id
        )

    def asset_for(self, tool_id, *, scope=None):
        """Read asset metadata by tool primary key; no acquisition is implied.

        The lookup no longer depends on an old capability ID: a tool registered
        only as an asset is readable by its primary key. Scope filtering still
        applies when a capability exists; without one there is nothing to match.
        """
        from .assets import AssetError, _token

        _token(tool_id)
        if tool_id not in self._tool_assets:
            if tool_id in self._tools:
                raise AssetError("unregistered_asset")
            raise AssetError("unregistered_tool")
        if scope is not None or tool_id in self._tools:
            self.resolve(tool_id, scope=scope)
        return self._assets[self._tool_assets[tool_id]]

    def select_asset(
        self, tool_id, *, target, policy, version=None, specifier="", scope=None
    ):
        from .assets import select_asset

        return select_asset(
            self,
            tool_id,
            target=target,
            policy=policy,
            version=version,
            specifier=specifier,
            scope=scope,
        )

    def asset_view(
        self, tool_id, *, target, policy, selection=None, index=None, scope=None
    ):
        from .assets import asset_view

        return asset_view(
            self,
            tool_id,
            target=target,
            policy=policy,
            selection=selection,
            index=index,
            scope=scope,
        )

    def provider_for(self, tool_id):
        """Host-declared provider identity, retained when explicit catalogs compose."""
        self.resolve(tool_id)
        return self._providers.get(tool_id, getattr(self, "provider_name", None))

    def resolve(self, tool_id, *, scope=None):
        if tool_id not in self._tools:
            raise WorkflowError(f"Tool is not registered: {tool_id}")
        value = self._tools[tool_id]
        if scope is not None and not scope.matches(value[0]):
            raise WorkflowError("Tool is outside the discovery scope")
        return value

    def merge(self, provider):
        """Compose an explicit provider atomically; duplicate ownership is an error."""
        if not isinstance(provider, Catalog):
            raise WorkflowError("Provider must return the existing Catalog contract")
        if self._tools.keys() & provider._tools.keys():
            raise WorkflowError("Duplicate tool registration across providers")
        if self._groups.keys() & provider._groups.keys():
            raise WorkflowError("Duplicate tool group registration across providers")
        if self._accesses.keys() & provider._accesses.keys():
            raise WorkflowError("Duplicate access entry registration across providers")
        staged = {}
        for name, (spec, adapter) in provider._tools.items():
            spec = deepcopy(spec)
            spec.validate()
            staged[name] = (spec, adapter)
        identities = {name: provider.provider_for(name) for name in staged}
        if any(
            name in self._assets and self._assets[name] != definition
            for name, definition in provider._assets.items()
        ):
            from .assets import AssetError

            raise AssetError("conflicting_asset")
        self._tools.update(staged)
        self._providers.update(identities)
        self._assets.update(provider._assets)
        self._tool_assets.update(provider._tool_assets)
        self._groups.update(provider._groups)
        self._accesses.update(provider._accesses)

    def documents(self):
        return [
            {**spec.document(), "contract_sha256": spec.sha256}
            for spec, _ in self._tools.values()
        ]

    def page(self, *, offset=0, limit=10, details=False, scope=None):
        """Progressively disclose a stable page; full contracts require opt-in."""
        if type(offset) is not int or offset < 0:
            raise WorkflowError("Tool page offset must be a nonnegative integer")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise WorkflowError("Tool page limit must be between 1 and 50")
        specs = [
            self._tools[name][0]
            for name in sorted(self._tools)
            if scope is None or scope.matches(self._tools[name][0])
        ]
        selected = specs[offset : offset + limit]
        return {
            "total": len(specs),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(specs) else None,
            "disclosure": "details" if details else "summary",
            "tools": [
                {**spec.document(), "contract_sha256": spec.sha256}
                if details
                else spec.summary()
                for spec in selected
            ],
        }

    def search(
        self,
        *,
        operation=None,
        query=None,
        domain=None,
        environment=None,
        effect=None,
        limit=10,
        scope=None,
    ):
        """Return bounded, deterministic candidates; selection never grants admission."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise WorkflowError("Tool search limit must be between 1 and 50")
        if effect is not None and effect not in {"read", "check", "write"}:
            raise WorkflowError("Unsupported tool search effect")
        words = set(re.findall(r"\w+", (query or "").casefold()))
        candidates = []
        for spec, _ in self._tools.values():
            if (
                (scope is not None and not scope.matches(spec))
                or (operation is not None and operation in spec.not_for)
                or (domain is not None and domain != spec.domain)
                or (environment is not None and environment not in spec.environments)
                or (effect is not None and effect != spec.effect)
            ):
                continue
            exact = operation is not None and operation in spec.use_when
            text = " ".join(
                (
                    spec.tool_id,
                    spec.description,
                    spec.domain,
                    *spec.tags,
                    *spec.use_when,
                )
            )
            matches = words & set(re.findall(r"\w+", text.casefold()))
            if operation is not None and not exact:
                continue
            if words and not matches:
                continue
            candidates.append(((-int(exact), -len(matches), spec.tool_id), spec))
        return [
            spec.summary()
            for _, spec in sorted(candidates, key=lambda item: item[0])[:limit]
        ]
