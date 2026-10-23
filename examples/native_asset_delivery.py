"""Explicit native acquisition; use ordinary Dagger File/Directory when needed."""

import argparse
import json
from pathlib import Path

from vesryn_tool_runtime import (
    Aria2NativeBackend,
    Aria2Source,
    AssetDefinition,
    AssetIndex,
    AssetPolicy,
    AssetRelease,
    AssetTarget,
    Catalog,
    ToolSpec,
)


def example_catalog():
    definitions = json.loads(
        Path(__file__).with_name("native-assets.json").read_text(encoding="utf-8")
    )
    catalog = Catalog()
    catalog.provider_name = "native-delivery-example"
    for value in definitions["definitions"]:
        tool_id = value["asset_id"] + ".example"
        # Consumers supply the actual execution Adapter and capability contract.
        catalog.register(ToolSpec(tool_id, {}, {}), None)
        catalog.register_asset(
            AssetDefinition(
                value["asset_id"],
                value["catalog_revision"],
                tuple(AssetRelease(**release) for release in value["releases"]),
            ),
            tools=(tool_id,),
        )
    return catalog


def dagger_directory(dag, delivery):
    """Import only the verified payload files, never a shared writable root."""
    return dag.host().directory(
        str(delivery.directory), include=[item.path for item in delivery.receipt.files]
    )


def dagger_file(dag, delivery):
    return dagger_directory(dag, delivery).file(delivery.entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=("hyperfine", "osv-scanner"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--os", choices=("linux", "windows"), required=True)
    parser.add_argument("--arch", default="x86_64")
    parser.add_argument("--abi")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--aria2", required=True)
    parser.add_argument("--aria2-version", required=True)
    parser.add_argument("--aria2-sha256", required=True)
    parser.add_argument("--policy-revision", required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--source-artifact", type=Path)
    args = parser.parse_args()
    policy = AssetPolicy(args.policy_revision)
    selection = example_catalog().select_asset(
        args.asset + ".example",
        target=AssetTarget(args.os, args.arch, abi=args.abi),
        policy=policy,
        version=args.version,
    )
    backend = Aria2NativeBackend(
        AssetIndex(args.root),
        aria2=Aria2Source(args.aria2, args.aria2_version, args.aria2_sha256),
    )
    receipt = backend.prepare(
        selection,
        policy=policy,
        allow_network=args.allow_network,
        source_artifact=args.source_artifact,
    )
    value = {"receipt": receipt.document(), "reason": receipt.outcome.reason}
    if receipt.outcome.status == "passed":
        value["delivery"] = backend.delivery(selection, policy=policy).document()
    print(json.dumps(value, indent=2))
    return 0 if receipt.outcome.status == "passed" else receipt.outcome.exit_code or 1


if __name__ == "__main__":
    raise SystemExit(main())
