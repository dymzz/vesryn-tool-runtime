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
from .discovery_contracts import (
    AccessEntrySummary,
    CandidateSummary,
    ContractDetail,
    DiscoveryContractError,
    DiscoveryDiagnostic,
    DiscoveryErrorDocument,
    DiscoveryPage,
    DiscoveryQuery,
    GroupMember,
    GroupSummary,
    compose_access_id,
)
from .documents import ToolRuntimeError
from .invocation import DispatchReceipt, ToolRuntime, checked_result, invoke_tool
from .native_assets import Aria2NativeBackend, Aria2Source, NativeAssetDelivery
from .registry import compose, provider
from .scope import DiscoveryScope
from .shared_definitions import (
    SharedAssetDefinition,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)
from .tool_registration import ToolAsset, ToolGroup
from .uv_assets import UvLock, UvToolBackend

__all__ = [
    "SELECTION_BINDING",
    "AccessEntrySummary",
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
    "CandidateSummary",
    "Catalog",
    "ContractDetail",
    "DiscoveryContractError",
    "DiscoveryDiagnostic",
    "DiscoveryErrorDocument",
    "DiscoveryPage",
    "DiscoveryQuery",
    "DiscoveryScope",
    "DispatchReceipt",
    "ExecutionContext",
    "GroupMember",
    "GroupSummary",
    "Invocation",
    "NativeAssetDelivery",
    "SharedAssetDefinition",
    "ToolAdapter",
    "ToolAsset",
    "ToolGroup",
    "ToolResult",
    "ToolRuntime",
    "ToolRuntimeError",
    "ToolSpec",
    "UvLock",
    "UvToolBackend",
    "asset_root",
    "canonical_binding",
    "checked_result",
    "compose",
    "compose_access_id",
    "create_binding",
    "invoke_tool",
    "load_shared_definitions",
    "native_asset_directory",
    "provider",
    "register_shared_definitions",
    "shared_definition_documents",
    "verify_binding",
    "verify_document",
]
