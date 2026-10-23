"""Public, independent registration, discovery, binding and invocation API."""

from .asset_index import (
    AssetFile,
    AssetIndex,
    AssetReceipt,
    asset_root,
    native_asset_directory,
)
from .assets import (
    AssetDefinition,
    AssetError,
    AssetPolicy,
    AssetRelease,
    AssetSelection,
    AssetTarget,
)
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
from .native_assets import Aria2NativeBackend, Aria2Source, NativeAssetDelivery
from .registry import compose, provider
from .scope import DiscoveryScope

__all__ = [
    "SELECTION_BINDING",
    "Aria2NativeBackend",
    "Aria2Source",
    "AssetDefinition",
    "AssetError",
    "AssetFile",
    "AssetIndex",
    "AssetPolicy",
    "AssetReceipt",
    "AssetRelease",
    "AssetSelection",
    "AssetTarget",
    "Catalog",
    "DiscoveryScope",
    "DispatchReceipt",
    "ExecutionContext",
    "Invocation",
    "NativeAssetDelivery",
    "ToolAdapter",
    "ToolResult",
    "ToolRuntime",
    "ToolRuntimeError",
    "ToolSpec",
    "asset_root",
    "canonical_binding",
    "checked_result",
    "compose",
    "create_binding",
    "invoke_tool",
    "native_asset_directory",
    "provider",
    "verify_binding",
    "verify_document",
]
