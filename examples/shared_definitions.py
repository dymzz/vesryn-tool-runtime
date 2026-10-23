"""Read bundled shared definitions and assemble them explicitly; offline only."""

import json

from vesryn_tool_runtime import (
    AssetPolicy,
    AssetTarget,
    Catalog,
    ToolResult,
    ToolSpec,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)


class ExampleAdapter:
    """Consumer-supplied execution; shared definitions never install or execute."""

    def invoke(self, calls, context):
        return {call.step_id: ToolResult("unavailable", None) for call in calls}


def example():
    names = shared_definition_documents()
    # Reading needs no Catalog, adapter, ECI checkout or consumer environment.
    records = [record for name in names for record in load_shared_definitions(name)]
    tools = Catalog()
    tools.provider_name = "example-cli-capabilities"
    # A real consumer registers its actual capabilities first. The bundled seed
    # declares example capabilities only; association with a capability that a
    # consumer has not implemented is rejected as an unregistered tool.
    for tool_id in ("example.search", "example.benchmark"):
        tools.register(ToolSpec(tool_id, {}, {}, effect="check"), ExampleAdapter())
    register_shared_definitions(tools, records)
    target = AssetTarget("windows", "x86_64", abi="msvc")
    policy = AssetPolicy("example-approval-1")
    for tool_id in ("example.search", "example.benchmark"):
        yield tools.asset_view(tool_id, target=target, policy=policy)


if __name__ == "__main__":
    for view in example():
        print(json.dumps(view, sort_keys=True))
