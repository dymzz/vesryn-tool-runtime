"""Run with Python after installing the wheel; no consumer repository is needed."""

from vesryn_tool_runtime import (
    Catalog,
    DiscoveryScope,
    ToolResult,
    ToolSpec,
    create_binding,
    invoke_tool,
)


class Increment:
    def invoke(self, calls, context):
        return {
            call.step_id: ToolResult(
                "passed",
                0,
                {"value": call.inputs["value"] + 1},
                executed=True,
                complete=True,
                current=True,
            )
            for call in calls
        }


def main():
    number = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    tools = Catalog()
    tools.provider_name = "example"
    tools.register(
        ToolSpec("math.increment", number, number, use_when=("increment",)), Increment()
    )
    scope = DiscoveryScope(environment="host", permissions=frozenset({"check"}))
    selected = tools.search(operation="increment", scope=scope)[0]
    binding = create_binding(
        tools,
        selected["tool_id"],
        provider="example",
        parameters={"value": 3},
        scope=scope,
    )
    receipt = invoke_tool(
        selected["tool_id"], {"value": 3}, catalog=tools, scope=scope, binding=binding
    )
    result = receipt.results["call"]
    assert result["outputs"] == {"value": 4}
    print(result)
    print("observation:", receipt.observation_status)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
