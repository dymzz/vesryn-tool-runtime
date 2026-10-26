"""Host CLI preparation, registration and the shared Agent list (issue #33)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    HostToolError,
    default_tools,
    prepare_tool,
    refresh_tools,
    uninstall_tool,
    user_data_root,
)
from vesryn_tool_runtime.host_tools import tools_database, tools_json


def run_fake_uv(argv, **kwargs):
    return subprocess.CompletedProcess(argv, 0, "", "")


def run_real(argv, check=False, **kwargs):
    """Actually execute (the probe target is a fake .bat/.sh in tmp)."""
    return subprocess.run(argv, check=check, **kwargs)


@pytest.fixture
def env(tmp_path):
    """A hermetic user-data root and PATH; nothing global is touched."""
    root = tmp_path / "vesryn-data"
    binroot = tmp_path / "fakebin"
    binroot.mkdir()
    return {
        "root": root,
        "bin": binroot,
        "environ": {
            "PATH": str(binroot),
            "VESRYN_TOOLS_HOME": str(root),
            "VESRYN_BIN_HOME": str(binroot / "exposed"),
        },
    }


def make_command(binroot, name, output, system=None):
    """A resolvable fake CLI that prints a version line."""
    if (system or sys.platform).startswith("win"):
        path = binroot / f"{name}.bat"
        path.write_text(f"@echo {output}\n", encoding="utf-8")
    else:
        path = binroot / name
        path.write_text(f"#!/bin/sh\necho '{output}'\n", encoding="utf-8")
        path.chmod(0o755)
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_default_list_is_a_pure_read(env):
    items = default_tools()
    assert [item["tool_id"] for item in items] == ["vulture", "hyperfine"]
    for item in items:
        assert set(item) == {"tool_id", "version", "command", "description"}
    assert not tools_database(env["root"]).exists()
    assert not tools_json(env["root"]).exists()


def test_user_data_root_override_and_defaults(tmp_path):
    assert (
        user_data_root(environ={"VESRYN_TOOLS_HOME": str(tmp_path / "custom")})
        == tmp_path / "custom"
    )
    assert (
        user_data_root(
            environ={"LOCALAPPDATA": str(tmp_path / "la"), "PATH": ""},
            platform="windows",
        )
        == tmp_path / "la" / "vesryn" / "data"
    )
    assert (
        user_data_root(
            environ={"XDG_DATA_HOME": str(tmp_path / "xd"), "PATH": ""},
            platform="linux",
        )
        == tmp_path / "xd" / "vesryn" / "data"
    )


def test_existing_matching_entry_is_reused_without_reinstall(env):
    make_command(env["bin"], "vulture", "vulture 2.16")
    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "reused"
    assert outcome["reused"] is True
    assert outcome["source_verified"] is False
    # Registration + list both updated by the one operation.
    rows = read_json(tools_json(env["root"]))
    assert rows == [{"command": "vulture", "description": "检测 Python 无用代码"}]
    store_outcome = outcome["entry"]
    assert store_outcome  # resolved path recorded


def test_version_conflict_is_reported_not_overwritten(env):
    make_command(env["bin"], "vulture", "vulture 1.9")
    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "conflict"
    assert "1.9" in outcome["detail"]
    # Nothing registered, nothing listed.
    assert not tools_json(env["root"]).exists()


def test_missing_python_cli_installed_via_uv_and_registered(env):
    calls = []

    def installing_uv(argv, **kwargs):
        if len(argv) >= 3 and argv[1] == "tool":
            calls.append(argv)
            # The install makes the command resolvable.
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        # The version probe really runs.
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert outcome["status"] == "installed"
    assert outcome["source_verified"] is True
    assert calls and calls[0][1:4] == ["tool", "install", "vulture==2.16"]
    assert read_json(tools_json(env["root"])) == [
        {"command": "vulture", "description": "检测 Python 无用代码"}
    ]


def test_native_install_needs_pinned_backend(env):
    with pytest.raises(HostToolError, match="backend_required"):
        prepare_tool(
            "hyperfine",
            root=env["root"],
            environ=env["environ"],
            runner=run_fake_uv,
            platform="windows",
        )


def test_list_sync_failure_reports_registration_saved(env, monkeypatch):
    make_command(env["bin"], "vulture", "vulture 2.16")

    # Make the JSON location unwritable after SQLite commit succeeds.
    def broken_refresh(root=None, environ=None):
        raise HostToolError("list_not_written", "simulated")

    from vesryn_tool_runtime import host_tools

    monkeypatch.setattr(host_tools, "refresh_tools", broken_refresh)
    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "registered_not_synced"


def test_registered_not_synced_and_explicit_rebuild(env, monkeypatch):
    make_command(env["bin"], "vulture", "vulture 2.16")
    from vesryn_tool_runtime import host_tools

    real_atomic = host_tools._atomic_write_json
    monkeypatch.setattr(host_tools, "_atomic_write_json", lambda path, entries: False)
    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    monkeypatch.setattr(host_tools, "_atomic_write_json", real_atomic)
    assert outcome["status"] == "registered_not_synced"
    assert not tools_json(env["root"]).exists()
    # Registration survived; an explicit rebuild syncs the list.
    assert refresh_tools(root=env["root"], environ=env["environ"]) == 1
    assert read_json(tools_json(env["root"])) == [
        {"command": "vulture", "description": "检测 Python 无用代码"}
    ]


def test_uninstall_removes_registration_and_refreshes_list(env):
    make_command(env["bin"], "vulture", "vulture 2.16")
    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    calls = []

    def fake_uv(argv, **kwargs):
        calls.append(argv)
        # Uninstall removes the resolvable command.
        (env["bin"] / "vulture.bat").unlink(missing_ok=True)
        (env["bin"] / "vulture").unlink(missing_ok=True)
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = uninstall_tool("vulture", root=env["root"], runner=fake_uv)
    assert result["status"] == "uninstalled"
    # Reused-external registrations are not uv-owned: uninstall removes the
    # registration and the list entry, and leaves the command alone.
    assert calls == []
    assert read_json(tools_json(env["root"])) == []


def test_tools_json_shape_is_strict_and_unlisted_when_not_resolvable(env):
    make_command(env["bin"], "vulture", "vulture 2.16")
    # hyperfine: registered via a stub aria2 path (entry recorded), but its
    # command does not resolve in this shell — stays out of the list.
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset

    # Register hyperfine directly through the internal registrar to avoid a
    # real download here; the fact shape is what matters for the list.
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "hyperfine"
    )
    # The recorded entry is the artifact the shell must end up resolving.
    entry = env["bin"] / (
        "hyperfine.bat" if sys.platform.startswith("win") else "hyperfine"
    )
    host_tools._register(
        env["root"],
        asset,
        "hyperfine",
        "2.0.0",
        str(entry),
        "命令行基准测试计时",
        "aria2",
        reused=False,
        source_verified=True,
        status="installed",
    )
    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    entries = read_json(tools_json(env["root"]))
    assert entries == [{"command": "vulture", "description": "检测 Python 无用代码"}]
    # Entry-not-ready native tool stays registered but unlisted; once its
    # command resolves (PATH prepared by the host), a refresh lists it.
    make_command(env["bin"], "hyperfine", "hyperfine 2.0.0")
    refresh_tools(root=env["root"], environ=env["environ"])
    entries = read_json(tools_json(env["root"]))
    assert [item["command"] for item in entries] == ["hyperfine", "vulture"]
    for item in entries:
        assert set(item) == {"command", "description"}


def test_selected_version_mismatch_is_a_conflict(env):
    """Reuse needs the SELECTED version, not any declared one (issue #33)."""
    make_command(env["bin"], "vulture", "vulture 2.14")
    outcome = prepare_tool(
        "vulture",
        version="2.16",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "conflict"
    assert "2.14" in outcome["detail"]
    # Nothing is registered and nothing is listed.
    assert not tools_json(env["root"]).exists()


def test_version_match_is_not_a_substring_match(env):
    """ "2.0.0" is not inside "12.0.0"."""
    make_command(env["bin"], "hyperfine", "hyperfine 12.0.0")
    outcome = prepare_tool(
        "hyperfine",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "conflict"


def test_install_is_verified_against_the_running_entry(env):
    """A same-name entry must not be registered as the selected release."""
    from vesryn_tool_runtime import host_tools

    def shadowing_uv(argv, **kwargs):
        if len(argv) >= 3 and argv[1] == "tool":
            # The install leaves an OLDER entry first on PATH.
            make_command(env["bin"], "vulture", "vulture 2.14")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "vulture",
        version="2.16",
        root=env["root"],
        environ=env["environ"],
        runner=shadowing_uv,
    )
    assert outcome["status"] == "conflict"
    # No verification is claimed for an entry that was not verified, and
    # nothing is registered for it.
    assert "source_verified" not in outcome
    assert not tools_json(env["root"]).exists()
    assert not host_tools.tools_database(env["root"]).exists()


def test_uninstall_removes_the_exposed_copy(env, monkeypatch):
    """The exposure copy is this runtime's own file and goes with it."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    monkeypatch.setenv("VESRYN_BIN_HOME", str(env["bin"] / "exposed"))
    exposed = env["bin"] / "exposed" / "hyperfine.exe"
    exposed.parent.mkdir(parents=True, exist_ok=True)
    exposed.write_bytes(b"payload-bytes")
    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "hyperfine"
    )
    host_tools._register(
        env["root"],
        asset,
        "hyperfine",
        "2.0.0",
        str(exposed),
        "命令行基准测试计时",
        "aria2",
        reused=False,
        source_verified=True,
        status="installed",
    )
    uninstall_tool("hyperfine", root=env["root"])
    assert not exposed.exists()


def test_uninstall_gives_uv_the_package_name(env):
    """uv removes the PACKAGE; the command may have another name."""
    calls = []

    def installing_uv(argv, **kwargs):
        if len(argv) >= 3 and argv[1] == "tool":
            make_command(env["bin"], "lint-imports", "lint-imports 2.15")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "import-linter",
        command="lint-imports",
        description="import 边界检查",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert outcome["status"] == "installed"

    def fake_uv(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    uninstall_tool("import-linter", root=env["root"], runner=fake_uv)
    assert calls == [["uv", "tool", "uninstall", "import-linter"]]


def test_exposure_directory_follows_the_target_environ(env):
    """The exposure directory comes from the target environment."""
    from vesryn_tool_runtime import host_tools

    payload = env["root"] / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "tool.exe").write_bytes(b"payload-bytes")
    target = env["bin"] / "from-environ"
    entry = host_tools._expose_native_entry(
        "demo",
        payload / "tool.exe",
        env["root"],
        environ={"VESRYN_BIN_HOME": str(target)},
    )
    assert entry.parent == target
    assert entry.read_bytes() == b"payload-bytes"


def test_list_skips_a_same_name_entry_that_is_not_the_registered_one(env):
    """The Agent must run the verified artifact, not a same-name binary."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    make_command(env["bin"], "vulture", "vulture 2.16")
    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    host_tools._register(
        env["root"],
        asset,
        "vulture",
        "2.16",
        str(env["root"] / "elsewhere" / "vulture"),
        "检测 Python 无用代码",
        "external",
        reused=True,
        source_verified=False,
        status="reused",
    )
    refresh_tools(root=env["root"], environ=env["environ"])
    assert read_json(tools_json(env["root"])) == []


def test_default_list_ships_as_a_data_resource():
    """The packaged default list lives at data/default-tools.json."""
    from importlib.resources import files

    resource = files("vesryn_tool_runtime").joinpath("data", "default-tools.json")
    assert resource.is_file()


def test_probe_reads_an_entry_in_a_path_with_spaces(tmp_path):
    """A resolved path may carry spaces (Program Files, ...)."""
    from vesryn_tool_runtime import host_tools

    binroot = tmp_path / "bin with spaces"
    binroot.mkdir()
    make_command(binroot, "vulture", "vulture 2.16")
    entry, shown = host_tools._probe("vulture", {"PATH": str(binroot)}, run_real)
    assert entry is not None
    assert "2.16" in (shown or "")


def test_an_empty_target_path_resolves_nothing(env):
    """An empty target PATH must not fall back to the host's PATH."""
    from vesryn_tool_runtime import host_tools

    make_command(env["bin"], "vulture", "vulture 2.16")
    assert host_tools._which("vulture", {"PATH": ""}) is None


def test_user_data_root_follows_the_target_environ(env):
    """VESRYN_TOOLS_HOME comes from the target environment."""
    make_command(env["bin"], "vulture", "vulture 2.16")
    outcome = prepare_tool(
        "vulture",
        environ=env["environ"],
        runner=run_real,
    )
    assert outcome["status"] == "reused"
    assert tools_json(env["root"]).exists()


def test_an_upgrade_replaces_our_own_exposed_copy(env):
    """Our own previous copy is replaced; a foreign one is refused."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    exposed_dir = env["bin"] / "exposed"
    exposed_dir.mkdir(parents=True, exist_ok=True)
    exposed = exposed_dir / "hyperfine.exe"
    exposed.write_bytes(b"old-bytes")
    payload = env["root"] / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "hyperfine.exe").write_bytes(b"new-bytes")
    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "hyperfine"
    )
    host_tools._register(
        env["root"],
        asset,
        "hyperfine",
        "2.0.0",
        str(exposed),
        "命令行基准测试计时",
        "aria2",
        reused=False,
        source_verified=True,
        status="installed",
    )
    entry = host_tools._expose_native_entry(
        "hyperfine",
        payload / "hyperfine.exe",
        env["root"],
        environ={"VESRYN_BIN_HOME": str(exposed_dir)},
    )
    assert entry.read_bytes() == b"new-bytes"


def test_a_foreign_exposed_command_is_never_overwritten(env):
    """A copy owned by another tool stays untouched."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    exposed_dir = env["bin"] / "exposed"
    exposed_dir.mkdir(parents=True, exist_ok=True)
    foreign = exposed_dir / "hyperfine.exe"
    foreign.write_bytes(b"foreign-bytes")
    payload = env["root"] / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "hyperfine.exe").write_bytes(b"our-bytes")
    other = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    host_tools._register(
        env["root"],
        other,
        "vulture",
        "2.16",
        str(foreign),
        "检测 Python 无用代码",
        "aria2",
        reused=False,
        source_verified=True,
        status="installed",
    )
    with pytest.raises(HostToolError, match="entry_conflict"):
        host_tools._expose_native_entry(
            "hyperfine",
            payload / "hyperfine.exe",
            env["root"],
            environ={"VESRYN_BIN_HOME": str(exposed_dir)},
        )
    assert foreign.read_bytes() == b"foreign-bytes"


def test_the_list_write_leaves_no_temporary_file(env):
    """The replacement file is unique and removed."""
    from vesryn_tool_runtime import host_tools

    path = env["root"] / "tools.json"
    assert host_tools._atomic_write_json(path, [{"command": "vulture"}]) is True
    assert read_json(path) == [{"command": "vulture"}]
    assert sorted(p.name for p in env["root"].iterdir()) == ["tools.json"]
