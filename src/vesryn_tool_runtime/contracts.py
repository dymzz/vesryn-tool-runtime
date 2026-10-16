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

    def register(self, spec: ToolSpec, adapter: ToolAdapter):
        spec = deepcopy(spec)
        spec.validate()
        if spec.tool_id in self._tools:
            raise WorkflowError("Duplicate tool registration")
        self._tools[spec.tool_id] = (spec, adapter)

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
        staged = {}
        for name, (spec, adapter) in provider._tools.items():
            spec = deepcopy(spec)
            spec.validate()
            staged[name] = (spec, adapter)
        identities = {name: provider.provider_for(name) for name in staged}
        self._tools.update(staged)
        self._providers.update(identities)

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
