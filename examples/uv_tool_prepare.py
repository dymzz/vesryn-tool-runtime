"""Prepare two real uv CLI versions, locate each, and describe a Linux lock.

Network use below is the explicit acquisition permission; running a tool needs the
host's separate admitted scope. Run: ``uv run python examples/uv_tool_prepare.py``.
Local Linux preparation uses the detected libc; an unknown libc is rejected.
The separate Linux lock describes an explicitly selected glibc container target.
"""

import json
import platform
import subprocess
import sys
import tempfile

from vesryn_tool_runtime import (
    AssetDefinition,
    AssetError,
    AssetIndex,
    AssetPolicy,
    AssetRelease,
    AssetTarget,
    Catalog,
    DiscoveryScope,
    ToolSpec,
    UvToolBackend,
)

FILES = "https://files.pythonhosted.org/packages/"
RELEASES = (
    (
        "2.16",
        FILES + "f5/be/f935130312330614811dae2ea9df3f395f6d63889eb6c2e68c14507152ee/"
        "vulture-2.16-py3-none-any.whl",
        "6e0f1c312cef1c87856957e5c2ca9608834a7c794c2180477f30bf0e4cc58eee",
    ),
    (
        "2.14",
        FILES + "a0/56/0cc15b8ff2613c1d5c3dc1f3f576ede1c43868c1bc2e5ccaa2d4bcd7974d/"
        "vulture-2.14-py2.py3-none-any.whl",
        "d9a90dba89607489548a49d557f8bac8112bd25d3cbc8aeef23e860811bd5ed9",
    ),
)
OS = {"win32": "windows", "linux": "linux", "darwin": "macos"}[sys.platform]
ARCH = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}[platform.machine().lower()]


def example():
    tools = Catalog()
    tools.register(ToolSpec("dead.code", {}, {}, effect="check"), None)
    tools.register_asset(
        AssetDefinition(
            "vulture",
            "example-1",
            tuple(
                AssetRelease(
                    version,
                    "python",
                    "uv",
                    url,
                    sha256,
                    "vulture",
                    package="vulture",
                    requires_python=">=3.8",
                )
                for version, url, sha256 in RELEASES
            ),
        ),
        tools=("dead.code",),
    )
    policy = AssetPolicy("example-approval-1")
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    abi = None
    if OS == "linux":
        abi = {"glibc": "gnu", "musl": "musl"}.get(platform.libc_ver()[0])
        if abi is None:
            raise AssetError("unsupported_target")
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    with tempfile.TemporaryDirectory() as root:
        backend = UvToolBackend(AssetIndex(root))
        for version, _, _ in RELEASES:
            selection = tools.select_asset(
                "dead.code",
                target=AssetTarget(OS, ARCH, abi=abi, python=python),
                policy=policy,
                version=version,
            )
            receipt = backend.prepare(selection, allow_network=True, policy=policy)
            command = backend.command(tools, selection, scope=scope, policy=policy)
            shown = subprocess.run(
                [*command, "--version"], capture_output=True, text=True, check=True
            ).stdout.strip()
            yield {
                "version": version,
                "outcome": receipt["outcome"],
                "environment_id": receipt["environment_id"],
                "tool_reports": shown,
            }
        linux = tools.select_asset(
            "dead.code",
            target=AssetTarget("linux", "x86_64", abi="gnu", python="3.14"),
            policy=policy,
            version="2.16",
        )
        lock = backend.lock(linux, allow_network=True, policy=policy).document()
        yield {
            "linux_lock": {**lock, "requirements": lock["requirements"].splitlines()}
        }


if __name__ == "__main__":
    for item in example():
        print(json.dumps(item, sort_keys=True))
