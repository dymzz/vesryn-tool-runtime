"""uv adapter against the real uv executable and real wheel artifacts."""

import base64
import hashlib
import platform
import shutil
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

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
from vesryn_tool_runtime.documents import WorkflowError

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required")

OS = {"win32": "windows", "linux": "linux", "darwin": "macos"}[sys.platform]
ARCH = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}[platform.machine().lower()]
PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"
TARGET = AssetTarget(OS, ARCH, python=PYTHON, abi="gnu" if OS == "linux" else None)
POLICY = AssetPolicy("approved-1")


def wheel(directory, name, version, *, requires=(), script=None):
    """Hand-built pure-Python wheel; ``script`` makes a console entry point."""
    directory.mkdir(parents=True, exist_ok=True)
    tag = f"{name}-{version}"
    files = {
        f"{name}/__init__.py": f"VERSION = {version!r}\n\ndef main():\n    print({tag!r})\n",
        f"{tag}.dist-info/METADATA": "\n".join(
            [
                "Metadata-Version: 2.1",
                f"Name: {name}",
                f"Version: {version}",
                *(f"Requires-Dist: {item}" for item in requires),
                "",
            ]
        ),
        f"{tag}.dist-info/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    if script:
        files[f"{tag}.dist-info/entry_points.txt"] = (
            f"[console_scripts]\n{script} = {name}:main\n"
        )
    record = []
    for path, text in files.items():
        raw = text.encode()
        encoded = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=")
        record.append(f"{path},sha256={encoded.decode()},{len(raw)}")
    record.append(f"{tag}.dist-info/RECORD,,")
    files[f"{tag}.dist-info/RECORD"] = "\n".join(record) + "\n"
    path = directory / f"{tag}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for item, text in files.items():
            archive.writestr(item, text)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def release(path, sha256, version, package="vtr_cli", entry="vtr-cli"):
    return AssetRelease(
        version,
        "python",
        "uv",
        path.resolve().as_uri(),
        sha256,
        entry,
        package=package,
        requires_python=">=3.14",
    )


def catalog(*releases, tool_id="vtr.check"):
    tools = Catalog()
    tools.register(ToolSpec(tool_id, {}, {}, effect="check"), None)
    tools.register_asset(
        AssetDefinition("vtr-cli", "rev-1", tuple(releases)), tools=(tool_id,)
    )
    return tools


@pytest.fixture
def uv_cache(tmp_path, monkeypatch):
    cache = tmp_path / "uv-cache"
    monkeypatch.setenv("UV_CACHE_DIR", str(cache))
    return cache


@pytest.fixture
def backend(tmp_path, uv_cache):
    return UvToolBackend(
        AssetIndex(tmp_path / "assets"), find_links=(tmp_path / "wheels",)
    )


def entry_version(command):
    return subprocess.run(
        command, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_prepare_runs_exact_version_without_touching_project_files(tmp_path, backend):
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='p'\nversion='0'\n")
    before = (project / "pyproject.toml").read_bytes()
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)

    assert backend.index.installed(selection)["status"] == "missing"
    receipt = backend.prepare(selection, policy=POLICY)
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    command = backend.command(tools, selection, scope=scope, policy=POLICY)

    assert receipt["outcome"]["status"] == "passed"
    assert receipt["verified_source_sha256"] == sha
    assert (
        receipt["environment_id"]
        == backend.installed(selection, policy=POLICY)["environment_id"]
    )
    assert entry_version(command) == "vtr_cli-1.0"
    assert (project / "pyproject.toml").read_bytes() == before


def test_two_versions_coexist_and_stay_selected(tmp_path, backend):
    first, first_sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    second, second_sha = wheel(tmp_path / "wheels", "vtr_cli", "2.0", script="vtr-cli")
    tools = catalog(
        release(second, second_sha, "2.0"), release(first, first_sha, "1.0")
    )
    old = tools.select_asset("vtr.check", target=TARGET, policy=POLICY, version="1.0")
    new = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    backend.prepare(old, policy=POLICY)
    backend.prepare(new, policy=POLICY)

    assert new.release.version == "2.0"
    assert (
        entry_version(backend.command(tools, old, scope=scope, policy=POLICY))
        == "vtr_cli-1.0"
    )
    assert (
        entry_version(backend.command(tools, new, scope=scope, policy=POLICY))
        == "vtr_cli-2.0"
    )
    assert (
        backend.installed(old, policy=POLICY)["locator"]
        != backend.installed(new, policy=POLICY)["locator"]
    )


def test_offline_reuse_and_missing_dependency_fails_truthfully(tmp_path, backend):
    wheel(tmp_path / "wheels", "vtr_dep", "1.0")
    path, sha = wheel(
        tmp_path / "wheels",
        "vtr_cli",
        "1.0",
        requires=("vtr_dep==1.0",),
        script="vtr-cli",
    )
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)

    assert backend.prepare(selection, policy=POLICY)["outcome"]["status"] == "passed"
    assert backend.installed(selection, policy=POLICY)["status"] == "present"
    shutil.rmtree(tmp_path / "wheels")  # dependency no longer obtainable anywhere

    missing = tools.select_asset(
        "vtr.check", target=TARGET, policy=replace(POLICY, revision="p2")
    )
    other = UvToolBackend(
        AssetIndex(tmp_path / "fresh"), find_links=(tmp_path / "wheels",)
    )
    # The source wheel is gone too, so a fresh offline preparation must fail.
    receipt = other.prepare(missing, policy=POLICY)
    assert receipt["outcome"]["status"] == "failed"
    assert other.index.installed(missing)["status"] == "missing"
    # The prepared environment is self-contained and still works offline.
    assert backend.installed(selection, policy=POLICY)["status"] == "present"


def test_cleared_cache_and_deleted_environment_are_not_reported_ready(
    tmp_path, backend, uv_cache
):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    backend.prepare(selection, policy=POLICY)
    shutil.rmtree(uv_cache, ignore_errors=True)
    assert (
        backend.installed(selection, policy=POLICY)["status"] == "present"
    )  # env is self-contained
    shutil.rmtree(Path(backend.installed(selection, policy=POLICY)["locator"]))
    assert backend.installed(selection, policy=POLICY)["status"] == "missing"


def test_failures_unsupported_targets_and_mismatch_keep_facts(tmp_path, backend):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    bad = release(path, "0" * 64, "1.0")
    tools = catalog(bad)
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    receipt = backend.prepare(selection, policy=POLICY)
    assert receipt["outcome"]["status"] == "failed"
    assert backend.index.installed(selection)["status"] == "missing"

    other_os = "linux" if OS != "linux" else "windows"
    foreign = replace(selection, target=AssetTarget(other_os, ARCH, python=PYTHON))
    with pytest.raises(AssetError) as error:
        backend.prepare(foreign, policy=POLICY)
    assert error.value.code == "unsupported_target"

    wrong = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    wrong = replace(wrong, release=release(path, sha, "2.0"), version=None)
    assert backend.prepare(wrong, policy=POLICY)["outcome"]["status"] == "failed"
    assert backend.index.installed(wrong)["status"] == "missing"


def test_discovery_does_not_prepare_and_execution_needs_its_own_admission(
    tmp_path, backend
):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    view = tools.asset_view(
        "vtr.check", target=TARGET, policy=POLICY, index=backend.index
    )
    assert view["installed"]["status"] == "missing"
    assert not (backend.root / "uv").exists()

    backend.prepare(selection, policy=POLICY)
    with pytest.raises(WorkflowError):
        backend.command(
            tools, selection, scope=DiscoveryScope(), policy=POLICY
        )  # no admitted permission
    with pytest.raises(WorkflowError):
        backend.command(
            tools,
            selection,
            scope=DiscoveryScope(permissions=frozenset({"read"})),
            policy=POLICY,
        )


def test_lock_describes_target_linux_for_containers(tmp_path, backend):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    linux = AssetTarget("linux", "x86_64", abi="gnu", python=PYTHON)
    selection = tools.select_asset("vtr.check", target=linux, policy=POLICY)
    lock = backend.lock(selection, policy=POLICY)
    document = lock.document()

    assert document["python_platform"] == "x86_64-unknown-linux-gnu"
    assert f"--hash=sha256:{sha}" in document["requirements"]
    assert document["source_sha256"] == sha
    assert document["uv_version"] == backend.uv_version()
    assert not (
        backend.root / "uv" / f"artifact-{selection.artifact_id}" / "venv"
    ).exists()


def test_prepared_environment_reuses_its_frozen_lock_after_cache_is_cleared(
    tmp_path, backend, uv_cache, monkeypatch
):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    first = backend.prepare(selection, policy=POLICY)
    scope = DiscoveryScope(permissions=frozenset({"check"}))
    command = backend.command(tools, selection, scope=scope, policy=POLICY)
    before = Path(command[0]).stat().st_mtime_ns
    frozen = backend.lock(selection, policy=POLICY).requirements
    shutil.rmtree(uv_cache, ignore_errors=True)
    shutil.rmtree(tmp_path / "wheels")
    original = backend._uv

    def no_rebuild(*args, **kwargs):
        assert args[0] != "venv"
        assert args[:2] not in {("pip", "compile"), ("pip", "install")}
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "_uv", no_rebuild)
    again = backend.prepare(selection, policy=POLICY)
    assert again["outcome"]["status"] == "passed"
    assert again["environment_id"] == first["environment_id"]
    assert Path(command[0]).stat().st_mtime_ns == before
    assert backend.lock(selection, policy=POLICY).requirements == frozen
    assert entry_version(command) == "vtr_cli-1.0"


def test_current_disable_and_version_policy_apply_to_old_uv_snapshots(
    tmp_path, backend
):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    selection = tools.select_asset("vtr.check", target=TARGET, policy=POLICY)
    for policy, reason in [
        (AssetPolicy("disabled-now", enabled=False), "selection_disabled"),
        (AssetPolicy("restricted-now", specifier=">2"), "no_matching_version"),
    ]:
        for operation in (backend.lock, backend.prepare, backend.installed):
            with pytest.raises(AssetError, match=reason):
                operation(selection, policy=policy)
        with pytest.raises(AssetError, match=reason):
            backend.command(
                tools,
                selection,
                scope=DiscoveryScope(permissions=frozenset({"check"})),
                policy=policy,
            )
    assert not backend.root.exists()


def test_linux_triples_follow_the_targets_real_libc(tmp_path, backend):
    path, sha = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    tools = catalog(release(path, sha, "1.0"))
    # A musl request resolves with the musl triple, never a silent GNU one.
    musl = AssetTarget("linux", "x86_64", abi="musl", python=PYTHON)
    selection = tools.select_asset("vtr.check", target=musl, policy=POLICY)
    document = backend.lock(selection, policy=POLICY).document()
    assert document["python_platform"] == "x86_64-unknown-linux-musl"
    # A Linux target whose C library is unknown cannot get a truthful triple;
    # it is explicitly rejected instead of resolved as GNU.
    unknown = replace(selection, target=AssetTarget("linux", "x86_64", python=PYTHON))
    with pytest.raises(AssetError) as error:
        backend.installed(unknown, policy=POLICY)
    assert error.value.code == "unsupported_target"


def test_platform_wheel_libc_is_read_from_the_artifact_name(tmp_path, backend):
    path, _ = wheel(tmp_path / "wheels", "vtr_cli", "1.0", script="vtr-cli")
    glibc = path.with_name("vtr_cli-1.0-cp314-abi3-manylinux_2_17_x86_64.whl")
    musl_wheel = path.with_name("vtr_cli-1.0-cp314-abi3-musllinux_1_2_x86_64.whl")
    shutil.copyfile(path, glibc)
    shutil.copyfile(path, musl_wheel)
    glibc_sha = hashlib.sha256(glibc.read_bytes()).hexdigest()
    musl_sha = hashlib.sha256(musl_wheel.read_bytes()).hexdigest()

    # Old-style mislabel: the release declares no ABI, but the manylinux name
    # is the authoritative artifact fact; admission follows it, not the label.
    mislabeled = catalog(release(glibc, glibc_sha, "1.0"))
    selection = mislabeled.select_asset("vtr.check", target=TARGET, policy=POLICY)
    for target in (
        AssetTarget("linux", "x86_64", abi="musl", python=PYTHON),
        AssetTarget("linux", "x86_64", python=PYTHON),
        AssetTarget("windows", "x86_64", abi="msvc", python=PYTHON),
    ):
        with pytest.raises(AssetError) as error:
            backend.installed(replace(selection, target=target), policy=POLICY)
        assert error.value.code == "unsupported_target"
    # A genuinely glibc target passes admission; the miss is an index fact.
    assert (
        backend.installed(
            replace(
                selection,
                target=AssetTarget("linux", "x86_64", abi="gnu", python=PYTHON),
            ),
            policy=POLICY,
        )["status"]
        == "missing"
    )

    # A musllinux wheel never reaches a glibc target, labeled or not.
    musl_tools = catalog(release(musl_wheel, musl_sha, "1.0"))
    musl_selection = musl_tools.select_asset(
        "vtr.check",
        target=AssetTarget("linux", "x86_64", abi="musl", python=PYTHON),
        policy=POLICY,
    )
    with pytest.raises(AssetError) as error:
        backend.installed(
            replace(
                musl_selection,
                target=AssetTarget("linux", "x86_64", abi="gnu", python=PYTHON),
            ),
            policy=POLICY,
        )
    assert error.value.code == "unsupported_target"
