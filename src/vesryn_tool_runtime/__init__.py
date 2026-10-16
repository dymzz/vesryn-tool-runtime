"""Public, independent registration, discovery, binding and invocation API."""

from .binding import (
    SELECTION_BINDING,
    canonical_binding,
    create_binding,
    verify_binding,
    verify_document,
)
from .contracts import (
    Catalog,
    ExecutionContext,
    Invocation,
    ToolAdapter,
    ToolResult,
    ToolSpec,
)
from .documents import ToolRuntimeError
from .invocation import DispatchReceipt, ToolRuntime, checked_result, invoke_tool
from .registry import compose, provider
from .scope import DiscoveryScope

__all__ = [
    "SELECTION_BINDING",
    "Catalog",
    "DiscoveryScope",
    "DispatchReceipt",
    "ExecutionContext",
    "Invocation",
    "ToolAdapter",
    "ToolResult",
    "ToolRuntime",
    "ToolRuntimeError",
    "ToolSpec",
    "canonical_binding",
    "checked_result",
    "compose",
    "create_binding",
    "invoke_tool",
    "provider",
    "verify_binding",
    "verify_document",
]
