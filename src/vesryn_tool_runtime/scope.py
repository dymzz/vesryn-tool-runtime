"""Host-supplied discovery constraints; repository names never grant permission."""

from collections.abc import Callable
from dataclasses import dataclass

from .documents import WorkflowError


@dataclass(frozen=True)
class DiscoveryScope:
    repository: str = ""
    task: str = ""
    environment: str | None = None
    permissions: frozenset[str] | None = None
    available: frozenset[str] | None = None
    constraint: Callable | None = None

    def matches(self, spec):
        return (
            (self.environment is None or self.environment in spec.environments)
            and (self.permissions is None or spec.effect in self.permissions)
            and (self.available is None or spec.tool_id in self.available)
            and (self.constraint is None or self.constraint(spec, self) is True)
        )

    def admit(self, spec):
        if self.permissions is None or not self.matches(spec):
            raise WorkflowError("Tool is outside the host's admitted scope")
