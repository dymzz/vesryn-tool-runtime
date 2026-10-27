"""Explicit Python CLI plugins through the existing, real uv tool chain."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from vesryn_tool_runtime import (
    HostToolError,
    ToolAsset,
    bundled_records,
    prepare_tool,
    uninstall_tool,
)
from vesryn_tool_runtime.discovery_records import ToolAssetVersion
from vesryn_tool_runtime.host_tools import tools_database, tools_json


@pytest.mark.parametrize(
    "requirements",
    [
        "demo==1.0",
        ["demo>=1.0"],
        ["demo==1.*"],
        ["demo===1.0"],
        ["demo[extra]==1.0"],
        ['demo==1.0; python_version>="3.10"'],
        ["demo @ https://example.test/demo.whl"],
        ["../demo"],
        ["--index-url=https://example.test"],
        ["demo==1.0", "Demo==2.0"],
        ["vulture==2.16"],
        [None],
    ],
)
def test_invalid_additional_requirements_fail_before_any_preparation(
    tmp_path, requirements
):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid requirements reached an external operation")

    root = tmp_path / "data"
    with pytest.raises(HostToolError) as caught:
        prepare_tool("vulture", root=root, with_packages=requirements, runner=forbidden)
    assert caught.value.code == "invalid_input"
    assert not root.exists()


def test_explicit_packages_cannot_be_applied_to_a_native_tool(tmp_path):
    with pytest.raises(HostToolError) as caught:
        prepare_tool("hyperfine", root=tmp_path / "data", with_packages=())
    assert caught.value.code == "invalid_input"
    assert not (tmp_path / "data").exists()


def test_pin_normalization_preserves_none_and_explicit_empty():
    from vesryn_tool_runtime._uv_tool_packages import normalize_with_packages

    assert normalize_with_packages(None, "sphinx") is None
    assert normalize_with_packages([], "sphinx") == ()
    assert normalize_with_packages(
        ["Other==2.0", "Demo_Plugin==1.0", "demo-plugin==1.0"], "sphinx"
    ) == ("demo-plugin==1.0", "other==2.0")


def test_public_tool_view_checks_the_actual_environment_and_entry(tmp_path):
    from vesryn_tool_runtime._uv_tool_packages import inspect_uv_tool

    home = tmp_path / "tool env (one)"
    python = home / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    entry = (
        tmp_path / "bin" / ("sphinx-build.exe" if os.name == "nt" else "sphinx-build")
    )
    calls = []
    environment = {
        "python": str(python),
        "prefix": str(home),
        "python_version": "3.14.3",
        "packages": [
            {"name": "sphinx", "version": "9.2.0"},
            {"name": "myst-parser", "version": "5.1.0"},
        ],
    }

    def runner(argv, **kwargs):
        calls.append(argv)
        assert kwargs["env"]["UV_TOOL_DIR"] == str(tmp_path)
        if "list" in argv:
            output = (
                "other v1.0 (/unrelated)\n- /unrelated/other\n"
                f"sphinx v9.2.0 [with: myst-parser==5.1.0] ({home})\n- {entry}\n"
            )
        elif "check" in argv:
            assert argv[argv.index("--python") + 1] == str(python)
            output = ""
        else:
            assert argv[0] == str(python) and argv[1:3] == ["-I", "-B"]
            output = json.dumps(environment)
        return subprocess.CompletedProcess(argv, 0, output, "")

    result = inspect_uv_tool(
        "uv", "sphinx", environ={"UV_TOOL_DIR": str(tmp_path)}, runner=runner
    )
    assert result["package"] == "sphinx" and result["version"] == "9.2.0"
    assert result["entrypoints"] == (str(entry),)
    assert result["environment"]["with_packages"] == ("myst-parser==5.1.0",)
    assert result["environment"]["dependencies_consistent"] is True
    assert result["environment"]["python"] == str(python)
    assert any("--show-with" in argv and "--show-paths" in argv for argv in calls)


@pytest.mark.parametrize(
    "mutation", ["prefix", "python", "main-version", "duplicate", "inventory"]
)
def test_public_tool_view_rejects_wrong_or_incomplete_environment_evidence(
    tmp_path, mutation
):
    from vesryn_tool_runtime._uv_tool_packages import inspect_uv_tool

    home = tmp_path / "tools"
    python = home / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    facts = {
        "python": str(python),
        "prefix": str(home),
        "python_version": "3.14.3",
        "packages": [{"name": "sphinx", "version": "9.2.0"}],
    }
    if mutation == "prefix":
        facts["prefix"] = str(tmp_path / "project-env")
    elif mutation == "python":
        facts["python"] = str(tmp_path / "project-env/python.exe")
    elif mutation == "main-version":
        facts["packages"][0]["version"] = "8.0.0"
    elif mutation == "duplicate":
        facts["packages"].append(dict(facts["packages"][0]))
    else:
        facts["packages"] = None

    def runner(argv, **kwargs):
        output = (
            f"sphinx v9.2.0 ({home})\n- {tmp_path / 'sphinx-build'}\n"
            if "list" in argv
            else json.dumps(facts)
        )
        return subprocess.CompletedProcess(argv, 0, output, "")

    with pytest.raises((ValueError, TypeError)):
        inspect_uv_tool("uv", "sphinx", environ={}, runner=runner)


@pytest.fixture
def uv_case(tmp_path, monkeypatch):
    from test_uv_assets import wheel

    from vesryn_tool_runtime import host_tools, record_sources

    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required")
    wheels = tmp_path / "wheels"
    main, digest = wheel(wheels, "vtr_cli", "1.0", script="vtr-cli")
    wheel(wheels, "vtr_plugin", "1.0")
    wheel(wheels, "vtr_plugin", "2.0")
    release = ToolAssetVersion("1.0", main.as_uri(), "sha256", digest, python=">=3.14")
    asset = ToolAsset("vtr-cli", "Test CLI", "uv", (release,), "vtr-cli", "vtr-cli")
    records = (*bundled_records(), asset)
    monkeypatch.setattr(record_sources, "bundled_records", lambda: records)
    binroot = tmp_path / "bin"
    binroot.mkdir()
    environ = {
        "PATH": str(binroot),
        "UV_TOOL_DIR": str(tmp_path / "tools"),
        "UV_TOOL_BIN_DIR": str(binroot),
        "UV_CACHE_DIR": str(tmp_path / "cache"),
        "UV_NO_INDEX": "1",
        "UV_FIND_LINKS": str(wheels),
        "UV_PYTHON_DOWNLOADS": "never",
        "VESRYN_TOOL_ASSETS": str(tmp_path / "assets"),
    }
    # A real local wheel is cached by the already established verification
    # path; subsequent prepare calls and uv are genuinely offline.
    host_tools._verified_artifact(asset, release, allow_network=True, environ=environ)
    calls = []

    def runner(argv, check=False, **kwargs):
        calls.append(argv)
        return subprocess.run(argv, check=check, **kwargs)

    def prepare(requirements=None, **kwargs):
        return prepare_tool(
            "vtr-cli",
            version="1.0",
            command="vtr-cli",
            description="Test CLI",
            root=tmp_path / "data",
            uv=uv,
            environ=environ,
            with_packages=requirements,
            runner=kwargs.pop("runner", runner),
            **kwargs,
        )

    return {
        "root": tmp_path / "data",
        "environ": environ,
        "prepare": prepare,
        "calls": calls,
        "asset": asset,
        "release": release,
        "runner": runner,
    }


def _installs(case):
    return [argv for argv in case["calls"] if "tool" in argv and "install" in argv]


def _versions(outcome):
    return {
        item["name"]: item["version"] for item in outcome["environment"]["packages"]
    }


def test_real_uv_reconciles_changed_and_removed_pins_and_reuses_equal_sets(uv_case):
    first = uv_case["prepare"](["VTR_Plugin==1.0", "vtr-plugin==1.0"])
    assert first["status"] == "installed" and first["source_verified"] is True
    assert _versions(first)["vtr-plugin"] == "1.0"
    assert first["environment"]["with_packages"] == ("vtr-plugin==1.0",)
    assert "--offline" in _installs(uv_case)[0]
    assert "--with" in _installs(uv_case)[0]
    calls = len(_installs(uv_case))
    same = uv_case["prepare"](("vtr-plugin==1.0",))
    assert same["status"] == "reused" and same["reused"] is True
    assert len(_installs(uv_case)) == calls
    changed = uv_case["prepare"](("vtr-plugin==2.0",))
    assert (
        changed["status"] == "installed" and _versions(changed)["vtr-plugin"] == "2.0"
    )
    assert len(_installs(uv_case)) == calls + 1
    removed = uv_case["prepare"](())
    assert removed["status"] == "installed" and "vtr-plugin" not in _versions(removed)
    assert removed["environment"]["with_packages"] == ()
    again = uv_case["prepare"](())
    assert again["status"] == "reused"
    legacy = uv_case["prepare"]()
    assert legacy["status"] == "reused" and "environment" not in legacy
    rows = json.loads(tools_json(uv_case["root"]).read_text(encoding="utf-8"))
    assert rows == [{"command": "vtr-cli", "description": "Test CLI"}]


def test_same_cli_without_plugins_is_not_a_plugin_environment_hit(uv_case):
    first = uv_case["prepare"]()
    assert first["status"] == "installed"
    with_plugin = uv_case["prepare"](("vtr-plugin==1.0",))
    assert with_plugin["status"] == "installed"
    assert _versions(with_plugin)["vtr-plugin"] == "1.0"
    assert len(_installs(uv_case)) == 2


def test_real_uv_uninstall_uses_the_prepared_directory_and_preserves_the_host_tool(
    uv_case, tmp_path, monkeypatch
):
    import sqlite3

    uv = shutil.which("uv")
    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    host_environ = {
        **uv_case["environ"],
        "PATH": str(host_bin),
        "UV_TOOL_DIR": str(tmp_path / "host-tools"),
        "UV_TOOL_BIN_DIR": str(host_bin),
        "UV_CACHE_DIR": str(tmp_path / "host-cache"),
    }
    host_root = tmp_path / "host-data"
    host = prepare_tool(
        "vtr-cli",
        version="1.0",
        command="vtr-cli",
        description="Host control CLI",
        root=host_root,
        uv=uv,
        environ=host_environ,
        with_packages=(),
        runner=uv_case["runner"],
    )
    target = uv_case["prepare"](("vtr-plugin==1.0",))
    assert host["status"] == target["status"] == "installed"
    host_manifest = tools_json(host_root).read_bytes()
    with sqlite3.connect(tools_database(host_root)) as db:
        host_registration = db.execute("SELECT * FROM tool_install").fetchall()
    # Model a host with the same package, entirely inside this fixture. An
    # uninstall that inherits the process environment will remove that control.
    for key, value in host_environ.items():
        monkeypatch.setenv(key, value)

    result = uninstall_tool(
        "vtr-cli",
        root=uv_case["root"],
        uv=uv,
        environ=uv_case["environ"],
        runner=uv_case["runner"],
    )
    assert result["status"] == "uninstalled"
    assert not Path(target["entry"]).exists()
    assert not Path(target["environment"]["prefix"]).exists()
    with sqlite3.connect(tools_database(uv_case["root"])) as db:
        assert db.execute("SELECT * FROM tool_install").fetchall() == []
    assert json.loads(tools_json(uv_case["root"]).read_text(encoding="utf-8")) == []
    probe = subprocess.run(
        [host["entry"], "--version"], capture_output=True, text=True, check=True
    )
    assert probe.stdout.strip() == "vtr_cli-1.0"
    assert tools_json(host_root).read_bytes() == host_manifest
    with sqlite3.connect(tools_database(host_root)) as db:
        assert db.execute("SELECT * FROM tool_install").fetchall() == host_registration


def test_missing_offline_plugin_keeps_old_registration_honest(uv_case):
    import sqlite3

    uv_case["prepare"](("vtr-plugin==1.0",))
    before = tools_json(uv_case["root"]).read_bytes()
    with sqlite3.connect(tools_database(uv_case["root"])) as db:
        old = db.execute("SELECT * FROM tool_install").fetchall()
    with pytest.raises(HostToolError) as caught:
        uv_case["prepare"](("vtr-plugin==99.0",))
    assert caught.value.code == "uv_install_failed"
    assert tools_json(uv_case["root"]).read_bytes() == before
    with sqlite3.connect(tools_database(uv_case["root"])) as db:
        assert db.execute("SELECT * FROM tool_install").fetchall() == old


def test_foreign_same_version_entry_is_not_overwritten(uv_case, tmp_path):
    from test_host_tools import make_command

    entry = make_command(Path(uv_case["environ"]["PATH"]), "vtr-cli", "vtr-cli 1.0")
    before = entry.read_bytes()
    result = uv_case["prepare"](("vtr-plugin==1.0",))
    assert result["status"] == "conflict"
    assert not _installs(uv_case)
    assert entry.read_bytes() == before
    assert not tools_database(uv_case["root"]).exists()


def test_unknown_source_proof_survives_inspection_and_is_reestablished_only_by_install(
    uv_case,
):
    import sqlite3

    uv_case["prepare"](("vtr-plugin==1.0",))
    with sqlite3.connect(tools_database(uv_case["root"])) as db:
        db.execute(
            "UPDATE tool_install SET prepared_via='external', verified_source=NULL, verified_sha256=NULL"
        )
    same = uv_case["prepare"](("vtr-plugin==1.0",))
    assert same["status"] == "reused" and same["source_verified"] is False
    changed = uv_case["prepare"](("vtr-plugin==2.0",))
    assert changed["source_verified"] is True
    argv = _installs(uv_case)[-1]
    assert argv[argv.index("--reinstall-package") + 1] == "vtr-cli"
    assert "--force" not in argv and "--reinstall" not in argv


def test_unverifiable_post_install_state_never_registers_success(uv_case):
    installed = False

    def runner(argv, **kwargs):
        nonlocal installed
        if installed and "list" in argv and "tool" in argv:
            return subprocess.CompletedProcess(argv, 0, "broken output", "")
        result = uv_case["runner"](argv, **kwargs)
        if "tool" in argv and "install" in argv:
            installed = True
        return result

    with pytest.raises(HostToolError) as caught:
        uv_case["prepare"](("vtr-plugin==1.0",), runner=runner)
    assert caught.value.code == "environment_unverified"
    assert not tools_database(uv_case["root"]).exists()


def test_dependency_check_failure_never_registers_success(uv_case):
    def runner(argv, **kwargs):
        if "pip" in argv and "check" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "dependency mismatch")
        return uv_case["runner"](argv, **kwargs)

    with pytest.raises(HostToolError) as caught:
        uv_case["prepare"](("vtr-plugin==1.0",), runner=runner)
    assert caught.value.code == "environment_unverified"
    assert not tools_database(uv_case["root"]).exists()


def test_shadowing_entry_is_not_admitted_by_another_valid_uv_environment(
    uv_case, tmp_path
):
    from test_host_tools import make_command

    original = uv_case["prepare"](("vtr-plugin==1.0",))
    before = tools_json(uv_case["root"]).read_bytes()
    installs = len(_installs(uv_case))
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    make_command(foreign, "vtr-cli", "vtr-cli 1.0")
    uv_case["environ"]["PATH"] = str(foreign) + os.pathsep + uv_case["environ"]["PATH"]
    result = uv_case["prepare"](("vtr-plugin==1.0",))
    assert result["status"] == "conflict" and result["entry"] != original["entry"]
    assert len(_installs(uv_case)) == installs
    assert tools_json(uv_case["root"]).read_bytes() == before
