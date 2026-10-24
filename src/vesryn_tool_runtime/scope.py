"""Host-supplied discovery constraints; repository names never grant permission."""

from collections.abc import Callable
from dataclasses import dataclass

from .documents import WorkflowError


@dataclass(frozen=True)
class ScopeDecision:
    """One Scope judgement, stated as a fact for callers to consume.

    ``reason`` names the caller's own constraint that excluded the tool — never
    a hidden registration or another caller's data. ``matched`` is the only
    positive claim; a decision alone grants no execution admission.
    """

    matched: bool
    reason: str | None = None

    def __post_init__(self):
        if type(self.matched) is not bool:
            raise WorkflowError("Scope decision requires an explicit match fact")
        if self.matched is (self.reason is not None):
            raise WorkflowError("Scope decision states one reason only when excluded")

    @property
    def state(self):
        return "matched" if self.matched else "excluded"


@dataclass(frozen=True)
class DiscoveryScope:
    repository: str = ""
    task: str = ""
    environment: str | None = None
    permissions: frozenset[str] | None = None
    available: frozenset[str] | None = None
    constraint: Callable | None = None

    def decision(self, spec):
        """The single Scope judgement: what matched, or the constraint that did not."""
        if self.environment is not None and self.environment not in spec.environments:
            return ScopeDecision(False, "environment")
        if self.permissions is not None and spec.effect not in self.permissions:
            return ScopeDecision(False, "effect")
        if self.available is not None and spec.tool_id not in self.available:
            return ScopeDecision(False, "availability")
        if self.constraint is not None and self.constraint(spec, self) is not True:
            return ScopeDecision(False, "constraint")
        return ScopeDecision(True)

    def matches(self, spec):
        return self.decision(spec).matched

    def admit(self, spec):
        if self.permissions is None or not self.matches(spec):
            raise WorkflowError("Tool is outside the host's admitted scope")
