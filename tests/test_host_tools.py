"""Host CLI preparation, registration and the shared Agent list (issue #33)."""

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
from ub_test_reports.pytest_plugin import add_test_properties

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
            # The asset root is hermetic too: a test never reads or writes
            # the host's own asset store.
            "VESRYN_TOOL_ASSETS": str(tmp_path / "tool-assets"),
        },
    }


def _synthetic_declaration(env, *, version="2.16", payload=b"the verified wheel"):
    """A declaration whose artifact identity this test controls.

    Returns (asset, release, stored): the asset the runtime sees, the release
    it declares, and where the verified artifact lives in the asset store.
    The digest is the digest OF THE PAYLOAD, so the artifact's bytes can
    actually be checked against it.
    """
    import hashlib
    from urllib.parse import urlsplit

    from vesryn_tool_runtime.discovery_records import ToolAsset, ToolAssetVersion

    digest = hashlib.sha256(payload).hexdigest()
    source = (
        "https://files.pythonhosted.org/packages/aa/bb/vulture-2.16-py3-none-any.whl"
    )
    release = ToolAssetVersion(
        version=version,
        source=source,
        digest_type="sha256",
        digest=digest,
        platform=None,
        python=">=3.9",
    )
    asset = ToolAsset(
        tool_id="vulture",
        name="vulture",
        provider="uv",
        versions=(release,),
        entrypoint="vulture",
        package="vulture",
    )
    name = PurePosixPath(urlsplit(source).path).name
    stored = (
        Path(env["environ"]["VESRYN_TOOL_ASSETS"])
        / "python"
        / "asset-vulture"
        / ("version-" + version)
        / digest
        / name
    )
    return asset, release, stored


def _store_artifact(stored, payload=b"the verified wheel"):
    """Put the verified artifact where the runtime puts it."""
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(payload)
    return stored


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


def test_missing_python_cli_installed_via_uv_and_registered(env, monkeypatch):
    from vesryn_tool_runtime import host_tools

    calls = []
    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")

    def fake_artifact(asset, release, **kwargs):
        return artifact

    monkeypatch.setattr(host_tools, "_verified_artifact", fake_artifact)

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
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
    # The backend receives the SELECTED artifact, not a bare name==version.
    assert calls
    argv = calls[0]
    index = argv.index("tool")
    assert argv[index : index + 2] == ["tool", "install"]
    assert argv[-1] == str(artifact)
    assert "vulture==2.16" not in argv
    assert read_json(tools_json(env["root"])) == [
        {"command": "vulture", "description": "检测 Python 无用代码"}
    ]


def test_the_offline_requirement_reaches_the_backend(env, monkeypatch):
    """allow_network=False must reach uv itself, not just the runtime."""
    from vesryn_tool_runtime import host_tools

    calls = []
    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            calls.append(argv)
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
        allow_network=False,
    )
    assert calls and "--offline" in calls[0]


def test_the_tool_interpreter_is_stated_not_guessed(env, monkeypatch):
    """uv must be told which interpreter builds the tool environment.

    Left to itself, uv picks one — on a free-threaded host that pick cannot
    load the stable-ABI (abi3) wheels publishers ship, and the install
    fails. The runtime names the interpreter instead.
    """
    from vesryn_tool_runtime import host_tools

    calls = []
    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            calls.append(argv)
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert calls
    argv = calls[0]
    assert "--python" in argv
    named = argv[argv.index("--python") + 1]
    # A pure-python artifact loads on any interpreter: the running one.
    assert named == sys.executable


def test_a_compiled_wheel_names_a_gil_enabled_interpreter(env, monkeypatch):
    """A compiled wheel cannot be loaded by a free-threaded interpreter.

    The runtime names a GIL-enabled interpreter of the same version instead
    of letting the backend pick one — uv's own version request does not
    exclude the free-threaded build.
    """
    from vesryn_tool_runtime import host_tools

    other = env["bin"] / "python.exe"
    other.write_bytes(b"interpreter")

    facts = {
        sys.executable: (3, 14, False),
        str(other): (3, 14, True),
    }
    monkeypatch.setattr(
        host_tools, "_interpreter_facts", lambda executable: facts.get(str(executable))
    )
    monkeypatch.setattr(
        host_tools,
        "_uv_interpreters",
        lambda uv, environ, version, runner: [str(other)],
    )

    # A compiled wheel (a platform-specific one) needs the GIL-enabled build.
    assert host_tools._tool_interpreter(
        "deptry-0.25.1-cp310-abi3-win_amd64.whl", env["environ"]
    ) == str(other)
    # A pure-python wheel loads on the running interpreter.
    assert (
        host_tools._tool_interpreter("vulture-2.16-py3-none-any.whl", env["environ"])
        == sys.executable
    )


def test_a_plugin_set_names_a_gil_enabled_interpreter(env, monkeypatch):
    """A plugin set lands in the same environment and must load there too.

    Published plugin wheels are commonly GIL-bound — a cpXY build or the
    stable ABI — and a free-threaded interpreter cannot load them: the
    backend would have to build the plugin from source instead.
    """
    from vesryn_tool_runtime import host_tools

    other = env["bin"] / "python.exe"
    other.write_bytes(b"interpreter")

    facts = {
        sys.executable: (3, 14, False),
        str(other): (3, 14, True),
    }
    monkeypatch.setattr(
        host_tools, "_interpreter_facts", lambda executable: facts.get(str(executable))
    )
    monkeypatch.setattr(
        host_tools,
        "_uv_interpreters",
        lambda uv, environ, version, runner: [str(other)],
    )

    # A pure-python wheel WITH a plugin set: the plugin's own artifacts have
    # to load in that environment, so the GIL-enabled build is named.
    assert host_tools._tool_interpreter(
        "sphinx-9.2.0-py3-none-any.whl",
        env["environ"],
        ("sphinx-codelinks==2.0.1",),
    ) == str(other)
    # Without a plugin set the running interpreter is kept.
    assert (
        host_tools._tool_interpreter("sphinx-9.2.0-py3-none-any.whl", env["environ"])
        == sys.executable
    )
    # A host without a GIL-enabled interpreter keeps the running one: the
    # plugin set may be pure Python, and that is not refused over.
    monkeypatch.setattr(
        host_tools, "_uv_interpreters", lambda uv, environ, version, runner: []
    )
    assert (
        host_tools._tool_interpreter(
            "sphinx-9.2.0-py3-none-any.whl",
            env["environ"],
            ("sphinx-codelinks==2.0.1",),
        )
        == sys.executable
    )


def test_no_interpreter_that_can_load_the_wheel_is_a_stable_reason(env, monkeypatch):
    """A host without a GIL-enabled interpreter reports a stable reason."""
    from vesryn_tool_runtime import host_tools

    monkeypatch.setattr(
        host_tools, "_interpreter_facts", lambda executable: (3, 14, False)
    )
    monkeypatch.setattr(
        host_tools, "_uv_interpreters", lambda uv, environ, version, runner: []
    )
    assert (
        host_tools._tool_interpreter(
            "deptry-0.25.1-cp310-abi3-win_amd64.whl", env["environ"]
        )
        is None
    )


def test_the_gil_interpreters_come_from_uv_own_listing(env):
    """uv's list tells the builds apart, and names the ones it manages.

    uv's own listing says which build an entry is — the free-threaded one
    cannot load a GIL-bound wheel — and it lists the interpreters uv
    manages, which are not on the target PATH at all. An entry uv could
    only download is not an interpreter yet.
    """
    from vesryn_tool_runtime import host_tools

    def entry(version, variant, path, implementation="cpython"):
        marker = "" if variant == "default" else f"+{variant}"
        return {
            "key": f"cpython-{version}{marker}-windows-x86_64-none",
            "version": version,
            "variant": variant,
            "implementation": implementation,
            "path": path,
        }

    # The fixture names each interpreter once; the expectation is read back
    # from it, so a changed fixture needs no new literal here.
    ordinary = entry("3.14.3", "default", "ordinary")
    managed = entry("3.14.3", "default", "managed")
    freethreaded = entry("3.14.8", "freethreaded", "freethreaded")
    other_version = entry("3.13.5", "default", "other-version")
    downloadable = entry("3.15.0", "default", None)
    listing = json.dumps([ordinary, managed, freethreaded, other_version, downloadable])
    calls = []

    def listing_uv(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, listing, "")

    assert host_tools._uv_interpreters("uv", env["environ"], "3.14", listing_uv) == [
        ordinary["path"],
        managed["path"],
    ]
    assert calls == [["uv", "python", "list", "--output-format", "json"]]

    # A listing uv cannot read leaves the caller with no candidate.
    def failing_uv(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "no")

    assert host_tools._uv_interpreters("uv", env["environ"], "3.14", failing_uv) == []


def test_the_selected_artifact_is_digest_checked_before_the_install(
    env, monkeypatch, tmp_path
):
    """A cached artifact whose digest does not match is never installed."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    release = next(item for item in asset.versions if item.version == "2.16")
    calls = []
    monkeypatch.setattr(
        host_tools,
        "_uv_install",
        lambda *args, **kwargs: calls.append(args) or None,
    )
    # A hermetic asset root: the host's own asset store is never consulted.
    environ = {"VESRYN_TOOL_ASSETS": str(tmp_path / "assets")}
    with pytest.raises(HostToolError, match="offline_missing"):
        host_tools._verified_artifact(
            asset, release, allow_network=False, environ=environ
        )
    assert calls == []


def _synthetic_release(digest, *, version="2.16", name="vulture-2.16-py3-none-any.whl"):
    """A release whose publisher digest this test controls."""
    from types import SimpleNamespace

    return SimpleNamespace(
        version=version,
        digest=digest,
        source="https://files.pythonhosted.org/packages/aa/bb/" + name,
    )


def test_a_verified_artifact_in_the_asset_root_is_reused_offline(tmp_path):
    """Offline preparation uses the already-verified copy, without network."""
    import hashlib

    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    payload = b"the verified wheel bytes"
    digest = hashlib.sha256(payload).hexdigest()
    release = _synthetic_release(digest)
    assets = tmp_path / "assets"
    cached = (
        assets
        / "python"
        / "asset-vulture"
        / "version-2.16"
        / digest
        / "vulture-2.16-py3-none-any.whl"
    )
    cached.parent.mkdir(parents=True)
    cached.write_bytes(payload)

    path = host_tools._verified_artifact(
        asset,
        release,
        allow_network=False,
        environ={"VESRYN_TOOL_ASSETS": str(assets)},
    )
    assert path == cached
    assert path.read_bytes() == payload


def test_a_cached_artifact_with_the_wrong_digest_is_never_installed(tmp_path):
    """A corrupt cached copy is dropped, not installed and not reused."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    digest = "0" * 64
    release = _synthetic_release(digest)
    assets = tmp_path / "assets"
    corrupt = (
        assets
        / "python"
        / "asset-vulture"
        / "version-2.16"
        / digest
        / "vulture-2.16-py3-none-any.whl"
    )
    corrupt.parent.mkdir(parents=True)
    corrupt.write_bytes(b"not the declared artifact")

    with pytest.raises(HostToolError, match="offline_missing"):
        host_tools._verified_artifact(
            asset,
            release,
            allow_network=False,
            environ={"VESRYN_TOOL_ASSETS": str(assets)},
        )
    # The corrupt copy is gone: it is never installed and never reused.
    assert not corrupt.exists()


def test_a_downloaded_artifact_with_the_wrong_digest_is_never_installed(
    tmp_path, monkeypatch
):
    """A download that does not match the publisher digest is discarded."""
    import io
    import urllib.request

    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "vulture"
    )
    digest = "1" * 64
    release = _synthetic_release(digest)
    assets = tmp_path / "assets"

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *arguments):
            self.close()
            return False

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *arguments, **keywords: Response(b"a different artifact"),
    )
    with pytest.raises(HostToolError, match="artifact_mismatch"):
        host_tools._verified_artifact(
            asset,
            release,
            allow_network=True,
            environ={"VESRYN_TOOL_ASSETS": str(assets)},
        )
    # Nothing was installed from it: no wheel and no partial download.
    installed = assets / "python" / "asset-vulture" / "version-2.16" / digest
    assert not list(installed.glob("*"))


def test_uninstalling_one_tool_keeps_the_others_listed(env):
    """The rebuild after an uninstall uses the SAME target environment.

    A rebuild that resolved in the HOST's shell would drop every tool that
    only exists in the target shell — uninstalling one tool would silently
    empty the shared list.
    """
    make_command(env["bin"], "vulture", "vulture 2.16")
    make_command(env["bin"], "pyright", "pyright 1.1.414")
    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    prepare_tool(
        "pyright",
        command="pyright",
        description="Python static type checking",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert len(read_json(tools_json(env["root"]))) == 2

    uninstall_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    entries = read_json(tools_json(env["root"]))
    assert [item["command"] for item in entries] == ["pyright"]


def test_a_failed_version_probe_is_not_a_reuse(env):
    """A non-zero probe exit is a failure fact, not a version."""
    make_command(env["bin"], "vulture", "vulture 2.16")

    def failing_probe(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 42, "vulture 2.16", "")

    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=failing_probe,
    )
    assert outcome["status"] == "conflict"
    assert "42" in outcome["detail"]
    # Nothing is registered and nothing is listed.
    assert not tools_json(env["root"]).exists()


def test_preparing_twice_keeps_the_installation_owner(env, monkeypatch):
    """A re-preparation must not drop the runtime's installation ownership."""
    from vesryn_tool_runtime import host_tools

    calls = []
    asset, _release, stored = _synthetic_declaration(env)
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset,)
    )
    monkeypatch.setattr(
        host_tools,
        "_verified_artifact",
        lambda asset, release, **kwargs: _store_artifact(stored),
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            calls.append(argv)
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert outcome["status"] == "installed"
    assert outcome["prepared_via"] == "uv"
    # The second preparation reuses the SAME entry and keeps the owner, so
    # the uninstall path still knows which environment it manages.
    again = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert again["status"] == "reused"
    assert again["prepared_via"] == "uv"
    # The SAME artifact identity: the verification fact still holds.
    assert again["source_verified"] is True


@pytest.mark.parametrize("changed", ["digest", "source"])
@add_test_properties(verifies=["SPEC_TR_MAIN_ARTIFACT_PROOF"])
def test_cached_replacement_is_not_installation_proof(env, monkeypatch, changed):
    """A cached B must never claim that the current entry was installed from B."""
    asset_a, _release_a, cached_a = _synthetic_declaration(env)
    _store_artifact(cached_a)
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset_a,)
    )
    installs = []

    def backend(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            installs.append(argv)
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    installed = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert installed["source_verified"] is True
    # The replacement is downloaded/cached, but has NEVER been installed.
    if changed == "source":
        from dataclasses import replace

        asset_b = replace(
            asset_a,
            versions=(replace(_release_a, source="https://example.test/other.whl"),),
        )
    else:
        asset_b, _release_b, cached_b = _synthetic_declaration(
            env, payload=b"another artifact of the same version"
        )
        _store_artifact(cached_b, b"another artifact of the same version")
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset_b,)
    )
    again = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert len(installs) == 1
    assert again["prepared_via"] == "uv"
    assert again["source_verified"] is False
    # Repeating the lookup must not turn availability into installation evidence.
    repeated = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert repeated["source_verified"] is False
    # Declaration sync must retain A's installation evidence rather than save B's.
    from vesryn_tool_runtime import open_record_store

    store = open_record_store(tools_database(env["root"]))
    assert store._db.execute(
        "SELECT verified_source, verified_sha256 FROM tool_install"
    ).fetchone() == (_release_a.source, _release_a.digest)
    store.close()
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset_a,)
    )
    original = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert original["source_verified"] is True
    assert len(installs) == 1


def test_the_ownership_lookup_compares_the_entry_as_a_path(env, monkeypatch):
    """The recorded entry is compared as a PATH, not as a byte string.

    The shared list compares a resolved entry with the recorded one through
    the path identity rule (`normcase(abspath(...))`). The ownership lookup
    must use the same rule: an entry recorded in another equivalent form is
    still the same entry, and the owner must be found.
    """
    import os

    from vesryn_tool_runtime import host_tools

    asset, _release, stored = _synthetic_declaration(env)
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset,)
    )
    monkeypatch.setattr(
        host_tools,
        "_verified_artifact",
        lambda asset, release, **kwargs: _store_artifact(stored),
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert outcome["status"] == "installed"
    entry = outcome["entry"]

    # The same file, written in another equivalent form.
    variant = os.path.join(os.path.dirname(entry), ".", os.path.basename(entry))
    assert variant != entry
    owner, _source, _sha256 = host_tools._existing_ownership(
        asset, "2.16", variant, env["root"]
    )
    assert owner == "uv"


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive paths")
def test_the_ownership_lookup_finds_an_entry_recorded_in_another_case(env, monkeypatch):
    """On Windows the same file can be recorded with another case."""
    from vesryn_tool_runtime import host_tools

    asset, _release, stored = _synthetic_declaration(env)
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset,)
    )
    monkeypatch.setattr(
        host_tools,
        "_verified_artifact",
        lambda asset, release, **kwargs: _store_artifact(stored),
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    outcome = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert outcome["status"] == "installed"
    owner, _source, _sha256 = host_tools._existing_ownership(
        asset,
        "2.16",
        outcome["entry"].upper(),
        env["root"],
    )
    assert owner == "uv"


def test_the_declared_release_is_the_one_of_the_target(env):
    """A version with several releases selects the TARGET's release.

    deptry ships a manylinux and a win_amd64 wheel under the same version;
    the artifact identity belongs to the release of this target, not to the
    first one with that version.
    """
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "deptry"
    )
    linux = host_tools._declared_release(asset, "0.25.1", platform="linux")
    windows = host_tools._declared_release(asset, "0.25.1", platform="windows")
    assert linux is not None and windows is not None
    assert linux.digest != windows.digest
    assert (linux.platform.os, windows.platform.os) == ("linux", "windows")


def test_installation_verification_survives_cache_eviction(env, monkeypatch):
    """Removing a download cache does not erase a verified installation fact."""
    asset, _release, cached = _synthetic_declaration(env)
    _store_artifact(cached)
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset,)
    )

    def backend(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    installed = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert installed["source_verified"] is True
    cached.unlink()
    again = prepare_tool(
        "vulture", root=env["root"], environ=env["environ"], runner=backend
    )
    assert again["prepared_via"] == "uv"
    assert again["source_verified"] is True


def test_a_switched_version_does_not_inherit_the_verification_state(env, monkeypatch):
    """The verification fact belongs to ONE artifact: the recorded version.

    The same path carrying another version is another artifact — the
    earlier registration's owner and verification state do not carry over,
    and the entry is recorded as an honest external reuse.
    """
    from vesryn_tool_runtime import host_tools

    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    installed = prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )
    assert installed["status"] == "installed"
    assert installed["source_verified"] is True

    # The entry now reports a DIFFERENT version: the same path, another
    # artifact, which the runtime never downloaded nor verified.
    make_command(env["bin"], "vulture", "vulture 2.14")
    switched = prepare_tool(
        "vulture",
        version="2.14",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    assert switched["status"] == "reused"
    assert switched["source_verified"] is False
    assert switched["prepared_via"] == "external"


def test_a_failed_uninstall_keeps_the_registration(env, monkeypatch):
    """A failing backend is not a completed uninstall."""
    from vesryn_tool_runtime import host_tools

    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
            make_command(env["bin"], "vulture", "vulture 2.16")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return run_real(argv, **kwargs)

    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=installing_uv,
    )

    def failing_uv(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 23, "", "refused")

    with pytest.raises(HostToolError, match="uninstall_failed"):
        uninstall_tool("vulture", root=env["root"], runner=failing_uv)
    # The registration and the list entry are untouched.
    assert read_json(tools_json(env["root"])) == [
        {"command": "vulture", "description": "检测 Python 无用代码"}
    ]


def test_a_delayed_publisher_cannot_overwrite_a_newer_list(env):
    """A publisher that waited for the lock publishes the CURRENT facts."""
    import threading

    from vesryn_tool_runtime import host_tools

    make_command(env["bin"], "vulture", "vulture 2.16")
    prepare_tool(
        "vulture",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    make_command(env["bin"], "pyright", "pyright 1.1.414")

    real_publish = host_tools._publish_list
    started = threading.Event()
    release = threading.Event()

    def paused_publish(root, environ=None):
        started.set()
        release.wait(10)
        return real_publish(root, environ)

    def slow_refresh():
        host_tools._publish_list = paused_publish
        try:
            host_tools.refresh_tools(root=env["root"], environ=env["environ"])
        finally:
            host_tools._publish_list = real_publish

    worker = threading.Thread(target=slow_refresh)
    worker.start()
    assert started.wait(10)
    # A newer registration and its list are published while the old
    # publisher waits.
    prepare_tool(
        "pyright",
        command="pyright",
        description="Python static type checking",
        root=env["root"],
        environ=env["environ"],
        runner=run_real,
    )
    release.set()
    worker.join(10)
    entries = read_json(tools_json(env["root"]))
    assert sorted(item["command"] for item in entries) == ["pyright", "vulture"]


def test_a_linux_target_resolves_to_the_record_platform(env):
    """platform=linux must speak the records' vocabulary."""
    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    assert host_tools.sys_platform("linux") == "linux"
    assert host_tools.sys_platform("win32") == "windows"
    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "hyperfine"
    )
    # The linux release of the record is found instead of "missing_release".
    release = host_tools._find_release(asset, "2.0.0", platform="linux")
    assert release.platform.os == "linux"
    assert release.platform.arch == "x86_64"


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
    def broken_publish(root, environ=None):
        raise HostToolError("list_not_written", "simulated")

    from vesryn_tool_runtime import host_tools

    monkeypatch.setattr(host_tools, "_publish_list", broken_publish)
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


def test_install_is_verified_against_the_running_entry(env, monkeypatch):
    """A same-name entry must not be registered as the selected release."""
    from vesryn_tool_runtime import host_tools

    artifact = env["root"] / "artifact" / "vulture-2.16-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def shadowing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
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
        status="installed",
    )
    uninstall_tool("hyperfine", root=env["root"])
    assert not exposed.exists()


def test_uninstall_gives_uv_the_package_name(env, monkeypatch):
    """uv removes the PACKAGE; the command may have another name."""
    from vesryn_tool_runtime import host_tools

    calls = []
    artifact = env["root"] / "artifact" / "import_linter-2.15-py3-none-any.whl"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified wheel")
    monkeypatch.setattr(
        host_tools, "_verified_artifact", lambda asset, release, **kwargs: artifact
    )

    def installing_uv(argv, **kwargs):
        if isinstance(argv, list) and "tool" in argv:
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
    entry, shown, probed, _detail = host_tools._probe(
        "vulture", {"PATH": str(binroot)}, run_real
    )
    assert entry is not None
    assert probed is True
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


def test_native_backend_must_match_the_selected_artifact(env, monkeypatch):
    from dataclasses import replace

    from vesryn_tool_runtime import host_tools
    from vesryn_tool_runtime.discovery_records import ToolAsset
    from vesryn_tool_runtime.record_sources import bundled_records

    asset = next(
        r
        for r in bundled_records()
        if isinstance(r, ToolAsset) and r.tool_id == "hyperfine"
    )
    selected = host_tools._declared_release(asset, "2.0.0", platform="windows")
    changed = replace(selected, digest="a" * 64)
    asset = replace(asset, versions=(changed,))
    monkeypatch.setattr(
        "vesryn_tool_runtime.record_sources.bundled_records", lambda: (asset,)
    )
    # The existing backend's same-version artifact must not stand in for the
    # selected one. No download, exposure or registration is allowed here.
    with pytest.raises(HostToolError, match="no_preparation_release"):
        prepare_tool(
            "hyperfine",
            root=env["root"],
            environ=env["environ"],
            runner=run_fake_uv,
            platform="windows",
            aria2=(str(env["bin"] / "aria2c.exe"), "1.37.0", "b" * 64),
        )
    assert not tools_database(env["root"]).exists()
    assert not (env["bin"] / "exposed").exists()
