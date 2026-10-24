"""Issue #5 acceptance through installed public APIs, with optional Dagger delivery.

Run explicitly with --root, a prepared/pinned aria2, and --allow-network.
--with-dagger additionally requires Linux, dagger-io==1.0.0b16 and Dagger
v1.0.0-beta.16. All CLI calls are version probes in this example's ToolAdapter.
"""

import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
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
    DiscoveryScope,
    Invocation,
    ToolResult,
    ToolRuntime,
    ToolSpec,
    UvToolBackend,
)


class VersionAdapter:
    """An example consumer Adapter; it receives one admitted batch."""

    def __init__(self):
        self.commands = {}

    def invoke(self, calls, context):
        results = {}
        for call in calls:
            command, expected = self.commands[call.step_id]
            result = subprocess.run(
                [*command, "--version"],
                executable=command[0],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            shown = result.stdout.strip()
            passed = result.returncode == 0 and expected in shown
            results[call.step_id] = ToolResult(
                "passed" if passed else "failed",
                0 if passed else result.returncode or 1,
                outputs={"version": shown[:1024]},
                executed=True,
                complete=True,
                current=True,
            )
        return results


def example_module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).with_name(name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def dagger_delivery(deliveries, locked):
    import dagger
    from dagger import dag

    native = example_module("native_asset_delivery")
    outputs = {}
    async with dagger.connection():
        base = dag.container().from_("ghcr.io/astral-sh/uv:python3.14-trixie-slim")
        for position, delivery in enumerate(deliveries):
            expected = delivery.receipt.selection.release.version
            if position == 0:
                container = base.with_file(
                    "/opt/hyperfine",
                    native.dagger_file(dag, delivery),
                    permissions=0o755,
                )
                executable = "/opt/hyperfine"
                kind = "File"
            else:
                container = base.with_directory(
                    "/opt/native", native.dagger_directory(dag, delivery)
                )
                executable = "/opt/native/" + delivery.entry
                kind = "Directory"
            shown = (
                await container.with_exec([executable, "--version"]).stdout()
            ).strip()
            assert shown == "hyperfine " + expected, shown
            outputs[kind] = shown
        python = (
            base.with_new_file("/locks/vulture.txt", locked.requirements)
            .with_exec(["uv", "venv", "/tool-env", "--python", "3.14", "--no-project"])
            .with_exec(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    "/tool-env/bin/python",
                    "--require-hashes",
                    "--no-deps",
                    "-r",
                    "/locks/vulture.txt",
                ]
            )
        )
        shown = (
            await python.with_exec(["/tool-env/bin/vulture", "--version"]).stdout()
        ).strip()
        assert shown == "vulture 2.16", shown
        outputs["uv_lock"] = shown
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--aria2", required=True)
    parser.add_argument("--aria2-version", required=True)
    parser.add_argument("--aria2-sha256", required=True)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--with-dagger", action="store_true")
    args = parser.parse_args()
    os_name = {"win32": "windows", "linux": "linux", "darwin": "macos"}[sys.platform]
    arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }[platform.machine().lower()]
    if args.with_dagger and os_name != "linux":
        parser.error("--with-dagger requires the declared Linux acceptance host")
    index = AssetIndex(args.root)
    policy = AssetPolicy("acceptance-2026-10-23")
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    adapter = VersionAdapter()
    catalog = Catalog()
    catalog.provider_name = "asset-acceptance-example"
    native = Aria2NativeBackend(
        index, aria2=Aria2Source(args.aria2, args.aria2_version, args.aria2_sha256)
    )
    uv = UvToolBackend(index)
    catalog.register(ToolSpec("hyperfine.version", {}, {}, effect="check"), adapter)
    definitions = json.loads(
        Path(__file__).with_name("native-assets.json").read_text(encoding="utf-8")
    )
    value = next(
        item for item in definitions["definitions"] if item["asset_id"] == "hyperfine"
    )
    catalog.register_asset(
        AssetDefinition(
            value["asset_id"],
            value["catalog_revision"],
            tuple(AssetRelease(**release) for release in value["releases"]),
        ),
        tools=("hyperfine.version",),
    )
    catalog.register(ToolSpec("vulture.version", {}, {}, effect="check"), adapter)
    catalog.register_asset(
        AssetDefinition(
            "vulture",
            "official-2026-10-23",
            tuple(
                AssetRelease(
                    version,
                    "python",
                    "uv",
                    url,
                    checksum,
                    "vulture",
                    package="vulture",
                    requires_python=">=3.8",
                )
                for version, url, checksum in example_module("uv_tool_prepare").RELEASES
            ),
        ),
        tools=("vulture.version",),
    )
    evidence, calls, deliveries = [], [], []
    for tool, versions, target, backend in [
        (
            "hyperfine.version",
            ("2.0.0", "1.20.0"),
            AssetTarget(os_name, arch, abi="msvc" if os_name == "windows" else "gnu"),
            native,
        ),
        (
            "vulture.version",
            ("2.16", "2.14"),
            AssetTarget(
                os_name,
                arch,
                abi="gnu" if os_name == "linux" else None,
                python=f"{sys.version_info.major}.{sys.version_info.minor}",
            ),
            uv,
        ),
    ]:
        for version in versions:
            selection = catalog.select_asset(
                tool, target=target, policy=policy, version=version
            )
            first = backend.prepare(
                selection, policy=policy, allow_network=args.allow_network
            )
            document = first.document() if hasattr(first, "document") else first
            assert document["outcome"]["status"] == "passed", document["outcome"]
            again = backend.prepare(selection, policy=policy)
            reused = again.document() if hasattr(again, "document") else again
            assert reused["outcome"]["status"] == "passed", reused["outcome"]
            if backend is native:
                delivery = native.delivery(selection, policy=policy)
                deliveries.append(delivery)
                scope.admit(catalog.resolve(tool)[0])
                command = (str(delivery.executable),)
            else:
                command = uv.command(catalog, selection, scope=scope, policy=policy)
            step = tool + "-" + version
            adapter.commands[step] = command, version
            calls.append(Invocation(step, tool, {}, 1))
            evidence.append(
                {
                    "selection": selection.document(),
                    "receipt": document,
                    "offline_reuse": True,
                }
            )
    receipt = ToolRuntime(catalog, scope=scope).dispatch(calls)
    assert all(result["status"] == "passed" for result in receipt.results.values()), (
        receipt.results
    )
    selection = catalog.select_asset(
        "vulture.version",
        target=AssetTarget("linux", "x86_64", abi="gnu", python="3.14"),
        policy=policy,
        version="2.16",
    )
    locked = uv.lock(selection, policy=policy, allow_network=args.allow_network)
    output = {
        "python": sys.version,
        "host": os_name,
        "uv_version": uv.uv_version(),
        "aria2_version": args.aria2_version,
        "aria2_sha256": args.aria2_sha256,
        "assets": evidence,
        "version_calls": receipt.results,
        "linux_lock": locked.document(),
        "dagger": None,
    }
    if args.with_dagger:
        import anyio

        output["dagger"] = anyio.run(dagger_delivery, deliveries, locked)
    content = json.dumps(output, indent=2) + "\n"
    (args.root / "acceptance.json").write_text(content, encoding="utf-8")
    print(
        json.dumps(
            {
                "version_calls": len(receipt.results),
                "offline_assets": len(evidence),
                "linux_lock_sha256": hashlib.sha256(
                    locked.requirements.encode()
                ).hexdigest(),
                "dagger": output["dagger"],
            }
        )
    )


if __name__ == "__main__":
    main()
