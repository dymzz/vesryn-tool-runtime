"""Read bundled shared definitions and register them directly; offline only."""

import json

from vesryn_tool_runtime import (
    AssetPolicy,
    AssetTarget,
    Catalog,
    load_shared_definitions,
    register_shared_definitions,
    shared_definition_documents,
)


def example():
    names = shared_definition_documents()
    # Reading needs no Catalog, adapter, ECI checkout or consumer environment.
    assert "examples.json" in names
    # Other groups describe tools this example does not implement.
    # Read and register only this example's document.
    records = load_shared_definitions("examples.json")
    # Tools register directly by their bare primary keys (#32): no empty
    # ToolSpec, no placeholder capability, and no execution permission. A
    # registered tool without a real contract stays explicitly unselectable.
    tools = Catalog()
    register_shared_definitions(tools, records)
    target = AssetTarget("windows", "x86_64", abi="msvc")
    policy = AssetPolicy("example-approval-1")
    for tool_id in ("ripgrep", "hyperfine"):
        yield tools.asset_view(tool_id, target=target, policy=policy)


if __name__ == "__main__":
    for view in example():
        print(json.dumps(view, sort_keys=True))
