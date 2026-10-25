"""Load the bundled live declaration and read it through public interfaces."""

import json

from vesryn_tool_runtime import bundled_records, compose_catalog


def example():
    # Pure read of the package resource — no store, no database, no ToolSpec.
    records = bundled_records()
    catalog = compose_catalog(records)
    for tool_id in ("trivy", "vulture"):
        asset = catalog.asset(tool_id)
        entries = catalog.accesses_for(tool_id)
        yield {
            "tool_id": tool_id,
            "provider": asset.provider,
            "versions": [
                {
                    "version": item.version,
                    "platform": None
                    if item.platform is None
                    else {
                        "os": item.platform.os,
                        "arch": item.platform.arch,
                        "abi": item.platform.abi,
                    },
                    "python": item.python,
                    "digest": item.digest[:16] + "…",
                }
                for item in asset.versions
            ],
            "groups": [
                group.group_id
                for group in catalog.groups()
                if any(member.tool_id == tool_id for member in group.members)
            ],
            "entries": [entry.access_id for entry in entries],
        }


if __name__ == "__main__":
    for view in example():
        print(json.dumps(view, sort_keys=True))
