"""Native acquisition verifies source and payload, never invokes a business tool."""

import hashlib
import io
import os
import shutil
import struct
import subprocess
import tarfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from filelock import FileLock

from vesryn_tool_runtime import (
    Aria2NativeBackend,
    Aria2Source,
    AssetDefinition,
    AssetError,
    AssetIndex,
    AssetPolicy,
    AssetRelease,
    AssetTarget,
    Catalog,
    DiscoveryScope,
    Invocation,
    ToolRuntime,
    ToolSpec,
    native_asset_directory,
)
from vesryn_tool_runtime.documents import digest, read, write

POLICY = AssetPolicy("current-policy")
TARGET = AssetTarget("linux", "x86_64", abi="gnu")


def elf(machine=62):
    data = bytearray(128)
    data[:6] = b"\x7fELF\x02\x01"
    data[6] = 1
    struct.pack_into("<HH", data, 16, 2, machine)
    return bytes(data)


def pe():
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664)
    return bytes(data)


def package(tmp_path, *, kind="tar", version="2.0", members=None, target=TARGET):
    suffix = {"tar": ".tar.gz", "zip": ".zip", "raw": ""}[kind]
    path = tmp_path / ("program-" + version + suffix)
    entry = "tool.exe" if target.os == "windows" else "tool"
    members = (
        members
        if members is not None
        else [
            ("bundle/" + entry, pe() if target.os == "windows" else elf()),
            ("bundle/LICENSE", b"license"),
        ]
    )
    if kind == "tar":
        with tarfile.open(path, "w:gz") as archive:
            for name, content in members:
                item = tarfile.TarInfo(name)
                if isinstance(content, tarfile.TarInfo):
                    archive.addfile(content)
                else:
                    item.size = len(content)
                    archive.addfile(item, io.BytesIO(content))
    elif kind == "zip":
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in members:
                archive.writestr(name, content)
        # Windows ZipInfo normalizes os.sep on write. Restore the malformed raw
        # names in both local and central headers so the reader sees the attack.
        for name, _ in members:
            if "\\" in name:
                path.write_bytes(
                    path.read_bytes().replace(
                        name.replace("\\", "/").encode(), name.encode()
                    )
                )
    else:
        path.write_bytes(members[0][1])
    release = AssetRelease(
        version,
        "native",
        "aria2",
        "https://example.invalid/" + path.name,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        entry,
        os=target.os,
        arch=target.arch,
        abi=target.abi,
    )
    catalog = Catalog()
    catalog.provider_name = "native-fixture"
    catalog.register(ToolSpec("native.check", {}, {}), None)
    catalog.register_asset(
        AssetDefinition("sample-native", "reviewed-1", (release,)),
        tools=("native.check",),
    )
    selection = catalog.select_asset("native.check", target=target, policy=POLICY)
    return path, selection, catalog


@pytest.fixture
def backend(tmp_path):
    executable = tmp_path / "prepared-aria2.exe"
    executable.write_bytes(b"independently supplied aria2")
    return Aria2NativeBackend(
        AssetIndex(tmp_path / "assets"),
        aria2=Aria2Source(
            str(executable),
            "1.37.0",
            hashlib.sha256(executable.read_bytes()).hexdigest(),
        ),
    )


def forbidden(*args, **kwargs):
    raise AssertionError("Unexpected subprocess or download")


def runner(
    monkeypatch,
    backend,
    source,
    *,
    exit_code=0,
    interrupt=False,
    version=b"aria2 version 1.37.0\n",
):
    calls = []

    def run(argv, **options):
        calls.append((argv, options))
        assert argv[0] == backend.aria2.executable
        assert "--no-conf=true" in argv
        assert options["stdin"] == subprocess.DEVNULL
        if "--version" in argv:
            return SimpleNamespace(returncode=0, stdout=version)
        assert "--no-netrc=true" in argv
        assert "--check-certificate=true" in argv
        assert "--enable-dht=false" in argv
        assert "--enable-dht6=false" in argv
        assert "--allow-overwrite=false" in argv
        if interrupt:
            (Path(options["cwd"]) / "artifact").write_bytes(b"partial")
            raise subprocess.TimeoutExpired(argv, 1)
        if not exit_code:
            shutil.copyfile(source, Path(options["cwd"]) / "artifact")
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(subprocess, "run", run)
    return calls


@pytest.mark.parametrize(
    "kind,target",
    [
        ("tar", TARGET),
        ("raw", TARGET),
        ("zip", AssetTarget("windows", "x86_64", abi="msvc")),
    ],
)
def test_restoration_and_readonly_offline_reuse(
    backend, tmp_path, monkeypatch, kind, target
):
    source, selection, _ = package(tmp_path, kind=kind, target=target)
    monkeypatch.setattr(subprocess, "run", forbidden)
    receipt = backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert receipt.outcome.status == "passed"
    assert not receipt.outcome.reused
    assert receipt.verified_source_sha256 == selection.release.sha256
    before = Path(receipt.locator).stat().st_mtime_ns
    again = backend.prepare(selection, policy=POLICY)
    assert again.outcome.reused and again.outcome.status == "passed"
    assert Path(receipt.locator).stat().st_mtime_ns == before
    index_before = backend.index.path.read_bytes()
    delivery = backend.delivery(selection, policy=POLICY)
    assert delivery.executable.is_file()
    assert backend.index.path.read_bytes() == index_before
    assert delivery.document()["source_sha256"] == selection.release.sha256
    assert backend.index.installed(selection)["status"] == "present"


def test_two_versions_keep_exact_paths(backend, tmp_path):
    one, first, _ = package(tmp_path, version="1.0")
    two, second, _ = package(
        tmp_path, version="2.0", members=[("bundle/tool", elf() + b"second")]
    )
    for source, selection in [(one, first), (two, second)]:
        assert (
            backend.prepare(
                selection, policy=POLICY, source_artifact=source
            ).outcome.status
            == "passed"
        )
    deliveries = [backend.delivery(s, policy=POLICY) for s in (first, second)]
    assert deliveries[0].directory != deliveries[1].directory
    assert (
        deliveries[0].executable.read_bytes() != deliveries[1].executable.read_bytes()
    )
    assert len(read(backend.index.path)["entries"]) == 2


def test_explicit_download_then_reuse_never_downloads(backend, tmp_path, monkeypatch):
    source, selection, _ = package(tmp_path)
    calls = runner(monkeypatch, backend, source)
    receipt = backend.prepare(selection, policy=POLICY, allow_network=True)
    assert receipt.outcome.status == "passed"
    assert len(calls) == 2
    assert "--checksum=sha-256=" + selection.release.sha256 in calls[1][0]
    assert backend.prepare(selection, policy=POLICY, allow_network=True).outcome.reused
    assert len(calls) == 2


def test_default_network_permission_and_disabled_cache(backend, tmp_path, monkeypatch):
    source, selection, _ = package(tmp_path)
    monkeypatch.setattr(subprocess, "run", forbidden)
    result = backend.prepare(selection, policy=POLICY)
    assert result.outcome.status == "unavailable"
    assert result.outcome.reason == "offline_missing"
    backend.prepare(selection, policy=POLICY, source_artifact=source)
    before = backend.index.path.read_bytes()
    for operation in (backend.prepare, backend.delivery):
        with pytest.raises(AssetError, match="selection_disabled"):
            operation(selection, policy=AssetPolicy("disabled-now", enabled=False))
        with pytest.raises(AssetError, match="no_matching_version"):
            operation(selection, policy=AssetPolicy("restricted-now", specifier="<2"))
    assert backend.index.path.read_bytes() == before


def test_downloader_failure_preserves_original_status_and_existing_version(
    backend, tmp_path, monkeypatch
):
    source, old, _ = package(tmp_path, version="1.0")
    backend.prepare(old, policy=POLICY, source_artifact=source)
    source, selection, _ = package(tmp_path)
    runner(monkeypatch, backend, source, exit_code=17)
    receipt = backend.prepare(selection, policy=POLICY, allow_network=True)
    assert (receipt.outcome.status, receipt.outcome.exit_code) == ("failed", 17)
    assert not native_asset_directory(backend.root, selection).exists()
    assert backend.index.installed(old)["status"] == "present"
    assert backend.index.installed(selection)["last_outcome"]["exit_code"] == 17
    assert "download_failed" not in backend.index.path.read_text()


def test_interruption_does_not_publish_partial_payload(backend, tmp_path, monkeypatch):
    source, selection, _ = package(tmp_path)
    runner(monkeypatch, backend, source, interrupt=True)
    receipt = backend.prepare(selection, policy=POLICY, allow_network=True)
    assert receipt.outcome.status == "interrupted"
    assert not native_asset_directory(backend.root, selection).exists()
    assert backend.index.installed(selection)["status"] == "unknown"
    assert not list((backend.root / "downloads").glob(".prepare-*"))


@pytest.mark.parametrize("which", ["source", "payload", "extra"])
def test_every_reuse_and_delivery_rechecks_actual_bytes(backend, tmp_path, which):
    source, selection, _ = package(tmp_path)
    backend.prepare(selection, policy=POLICY, source_artifact=source)
    delivery = backend.delivery(selection, policy=POLICY)
    path = {
        "source": backend.root
        / "downloads"
        / ("sha256-" + selection.release.sha256)
        / "artifact",
        "payload": delivery.executable,
        "extra": delivery.directory / "injected-file",
    }[which]
    path.write_bytes(b"changed")
    with pytest.raises(AssetError, match="integrity_mismatch"):
        backend.delivery(selection, policy=POLICY)
    receipt = backend.prepare(selection, policy=POLICY, allow_network=True)
    assert receipt.outcome.status == "failed"
    assert receipt.outcome.reason == "integrity_mismatch"
    assert path.read_bytes() == b"changed"


def test_index_manifest_cannot_establish_source_trust(backend, tmp_path):
    source, selection, _ = package(tmp_path)
    backend.prepare(selection, policy=POLICY, source_artifact=source)
    delivery = backend.delivery(selection, policy=POLICY)
    delivery.executable.write_bytes(elf() + b"forged")
    document = read(backend.index.path)
    entry = document["entries"][selection.artifact_id]
    for key in ("installation", "last_receipt"):
        for item in entry[key]["files"]:
            if item["path"] == delivery.entry:
                item["sha256"] = hashlib.sha256(
                    delivery.executable.read_bytes()
                ).hexdigest()
    entry["sha256"] = digest({k: entry[k] for k in ("installation", "last_receipt")})
    write(backend.index.path, document, replace=True)
    assert backend.index.installed(selection)["status"] == "present"
    with pytest.raises(AssetError, match="integrity_mismatch"):
        backend.delivery(selection, policy=POLICY)


@pytest.mark.parametrize("kind", ["tar", "zip"])
@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:/drive",
        "bundle/../escape",
        "bundle\\escape",
        "CON",
        "CONIN$",
        "COM¹",
        "wild*name",
        "trailing.",
    ],
)
def test_archive_escaping_and_portable_aliases_are_refused(
    backend, tmp_path, kind, name
):
    source, selection, _ = package(
        tmp_path, kind=kind, members=[("tool", elf()), (name, b"bad")]
    )
    receipt = backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert receipt.outcome.reason == "unsafe_archive"
    assert not native_asset_directory(backend.root, selection).exists()
    assert not (tmp_path / "escape").exists()
    assert backend.index.installed(selection)["status"] == "missing"


@pytest.mark.parametrize(
    "link_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE]
)
def test_tar_links_and_special_files_are_refused(backend, tmp_path, link_type):
    link = tarfile.TarInfo("link")
    link.type, link.linkname = link_type, "../outside"
    source, selection, _ = package(tmp_path, members=[("tool", elf()), ("link", link)])
    result = backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert result.outcome.reason == "unsafe_archive"
    assert not native_asset_directory(backend.root, selection).exists()


@pytest.mark.parametrize(
    "members,reason",
    [
        ([("Tool", elf()), ("tool", elf())], "unsafe_archive"),
        ([("other", elf())], "entrypoint_missing"),
        ([("a/tool", elf()), ("b/tool", elf())], "entrypoint_ambiguous"),
        ([("tool", pe())], "artifact_target_mismatch"),
        ([("tool", elf(183))], "artifact_target_mismatch"),
    ],
)
def test_archive_ambiguity_and_wrong_binary_target(backend, tmp_path, members, reason):
    source, selection, _ = package(tmp_path, members=members)
    result = backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert result.outcome.reason == reason
    assert not native_asset_directory(backend.root, selection).exists()


def test_source_digest_and_extraction_limits(backend, tmp_path):
    source, selection, _ = package(tmp_path)
    source.write_bytes(b"different download")
    assert (
        backend.prepare(selection, policy=POLICY, source_artifact=source).outcome.reason
        == "integrity_mismatch"
    )
    source, selection, _ = package(tmp_path)
    backend.max_files = 1
    assert (
        backend.prepare(selection, policy=POLICY, source_artifact=source).outcome.reason
        == "asset_too_large"
    )
    assert not native_asset_directory(backend.root, selection).exists()


def test_aria2_executable_pin_and_version_are_checked(backend, tmp_path, monkeypatch):
    source, selection, _ = package(tmp_path)
    calls = runner(monkeypatch, backend, source, version=b"aria2 version 9.0.0\n")
    assert (
        backend.prepare(selection, policy=POLICY, allow_network=True).outcome.reason
        == "backend_version_mismatch"
    )
    assert len(calls) == 1
    Path(backend.aria2.executable).write_bytes(b"changed executable")
    assert (
        backend.prepare(selection, policy=POLICY, allow_network=True).outcome.reason
        == "backend_integrity_mismatch"
    )
    assert len(calls) == 1


def test_two_concurrent_preparations_publish_once(backend, tmp_path, monkeypatch):
    source, selection, _ = package(tmp_path)
    calls = runner(monkeypatch, backend, source)
    real_run = subprocess.run

    def slow(*args, **kwargs):
        time.sleep(0.03)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: backend.prepare(selection, policy=POLICY, allow_network=True),
                range(2),
            )
        )
    assert all(r.outcome.status == "passed" for r in results)
    assert len(calls) == 2
    assert sum(r.outcome.reused for r in results) == 1
    assert backend.delivery(selection, policy=POLICY).executable.is_file()


def test_corrupt_index_is_refused_before_network(backend, tmp_path, monkeypatch):
    _, selection, _ = package(tmp_path)
    backend.root.mkdir()
    backend.index.path.write_text("{}")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(AssetError, match="invalid_index"):
        backend.prepare(selection, policy=POLICY, allow_network=True)
    assert backend.index.path.read_text() == "{}"
    assert not (backend.root / "downloads").exists()


def test_source_lock_timeout_stays_explicit(backend, tmp_path):
    source, selection, _ = package(tmp_path)
    lock = backend.root / "locks" / ("source-" + selection.release.sha256 + ".lock")
    lock.parent.mkdir(parents=True)
    backend.index.timeout = 0.01
    with FileLock(lock), pytest.raises(AssetError, match="index_busy"):
        backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert not backend.index.path.exists()


def test_preparation_never_changes_binding_or_admits_execution(
    backend, tmp_path, monkeypatch
):
    source, selection, catalog = package(tmp_path)
    contract = catalog.resolve("native.check")[0].sha256
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert (
        catalog.asset_view(
            "native.check", target=TARGET, policy=POLICY, index=backend.index
        )["installed"]["status"]
        == "missing"
    )
    assert not backend.root.exists()
    backend.prepare(selection, policy=POLICY, source_artifact=source)
    assert catalog.resolve("native.check")[0].sha256 == contract
    receipt = ToolRuntime(catalog, scope=DiscoveryScope()).invoke(
        Invocation("call", "native.check", {}, 1)
    )
    assert receipt.results["call"]["status"] == "unavailable"


def test_backend_rejects_non_native_selection(backend, tmp_path):
    _, selection, _ = package(tmp_path)
    release = AssetRelease(
        "1.0",
        "oci",
        "oci",
        "registry.example/tool@sha256:" + "a" * 64,
        "a" * 64,
        "tool",
        os="linux",
        arch="x86_64",
    )
    with pytest.raises(AssetError, match="invalid_backend"):
        backend.prepare(replace(selection, release=release), policy=POLICY)


def test_index_symlink_is_rejected_before_reading_or_writing(backend, tmp_path):
    _, selection, _ = package(tmp_path)
    other = tmp_path / "untouched.json"
    other.write_text("do not read as an index")
    backend.root.mkdir()
    try:
        os.symlink(other, backend.index.path)
    except OSError:
        pytest.skip("This Windows host does not permit creating file symlinks")
    for operation in (backend.prepare, backend.delivery):
        with pytest.raises(AssetError, match="invalid_location"):
            operation(selection, policy=POLICY)
    assert other.read_text() == "do not read as an index"
