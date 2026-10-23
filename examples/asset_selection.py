"""Resolve declared real CLI artifacts offline; no download, installation or invocation."""

import json
from pathlib import Path

from vesryn_tool_runtime import (
    AssetDefinition,
    AssetPolicy,
    AssetRelease,
    AssetTarget,
    Catalog,
    ToolSpec,
)


def example():
    definitions = json.loads(
        Path(__file__).with_name("asset-definitions.json").read_text(encoding="utf-8")
    )
    tools = Catalog()
    tools.provider_name = "example-cli-capabilities"
    for item in definitions["assets"]:
        tool_id = item["tool_id"]
        # Metadata example: a future consumer supplies its admitted ToolAdapter.
        tools.register(ToolSpec(tool_id, {}, {}, effect="check"), None)
        definition = item["definition"]
        tools.register_asset(
            AssetDefinition(
                definition["asset_id"],
                definition["catalog_revision"],
                tuple(AssetRelease(**release) for release in definition["releases"]),
            ),
            tools=(tool_id,),
        )
        target = AssetTarget(**item["target"])
        policy = AssetPolicy("example-approval-1")
        selection = tools.select_asset(tool_id, target=target, policy=policy)
        yield tools.asset_view(
            tool_id, target=target, policy=policy, selection=selection
        )


if __name__ == "__main__":
    for view in example():
        print(json.dumps(view, sort_keys=True))
