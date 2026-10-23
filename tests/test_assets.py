"""Asset selection and actual local receipts do not grant invocation authority."""

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from filelock import FileLock

import vesryn_tool_runtime
from vesryn_tool_runtime import (
    AssetDefinition,
    AssetError,
    AssetFile,
    AssetIndex,
    AssetPolicy,
    AssetReceipt,
    AssetRelease,
    AssetSelection,
    AssetTarget,
    Catalog,
    DiscoveryScope,
    Invocation,
    ToolResult,
    ToolRuntime,
    ToolSpec,
    asset_root,
    compose,
    create_binding,
    native_asset_directory,
    verify_binding,
)
from vesryn_tool_runtime.documents import digest, read, write
from vesryn_tool_runtime.registry import scoped_catalog

TARGET = AssetTarget("windows", "x86_64", abi="gnu")
POLICY = AssetPolicy("approved-1")


def native(version="2.0", **changes):
    return replace(
        AssetRelease(
            version,
            "native",
            "aria2",
            f"https://example.invalid/tool-{version}.zip",
            hashlib.sha256(version.encode()).hexdigest(),
            "tool.exe",
            os="windows",
            arch="x86_64",
            abi="gnu",
        ),
        **changes,
    )


def catalog(
    *releases, asset_id="sample.cli", revision="published-1", tool="sample.read"
):
    tools = Catalog()
    tools.provider_name = "sample-domain"
    tools.register(ToolSpec(tool, {}, {}, effect="read"), None)
    tools.register_asset(
        AssetDefinition(asset_id, revision, releases or (native(), native("1.0"))),
        tools=(tool,),
    )
    return tools


def choose(tools=None, **options):
    return (tools or catalog()).select_asset(
        "sample.read", target=TARGET, policy=POLICY, **options
    )


def success(root, selection):
    location = native_asset_directory(root, selection)
    location.mkdir(parents=True, exist_ok=True)
    content = selection.release.version.encode()
    (location / "tool.exe").write_bytes(content)
    return AssetReceipt(
        selection,
        ToolResult("passed", 0, executed=True, complete=True, current=True),
        str(location),
        (AssetFile("tool.exe", hashlib.sha256(content).hexdigest()),),
        verified_source_sha256=selection.release.sha256,
    )


def test_defaults_follow_published_order_and_old_choices_remain_readable():
    first = choose()
    assert choose().document() == first.document()
    assert first.release.version == "2.0"
    current = choose(catalog(native("3.0"), native(), revision="published-2"))
    assert current.release.version == "3.0"
    assert current.selection_id != first.selection_id
    assert AssetSelection.from_document(first.document()) == first
    new_policy = catalog().select_asset(
        "sample.read", target=TARGET, policy=AssetPolicy("approved-2")
    )
    assert new_policy.selection_id != first.selection_id
    assert new_policy.artifact_id == first.artifact_id
    # Version ordering is explicitly the release declaration's policy, not sorting
    # tool contract versions or interpreting the highest installed version as default.
    assert choose(catalog(native("1.0"), native())).release.version == "1.0"


def test_two_consumers_share_index_but_freeze_different_versions(tmp_path):
    tools = catalog()
    first = choose(tools, specifier="<2")
    second = choose(tools, version="2.0")
    index = AssetIndex(tmp_path)
    index.record(success(tmp_path, first))
    index.record(success(tmp_path, second))
    assert first.release.version == "1.0" and second.release.version == "2.0"
    assert (
        index.installed(first)["status"]
        == index.installed(second)["status"]
        == "present"
    )
    assert native_asset_directory(tmp_path, first) != native_asset_directory(
        tmp_path, second
    )


@pytest.mark.parametrize(
    "target",
    [
        AssetTarget("linux", "x86_64", abi="gnu"),
        AssetTarget("windows", "aarch64", abi="gnu"),
        AssetTarget("windows", "x86_64", abi="msvc"),
        AssetTarget("windows", "x86_64"),
    ],
)
def test_target_mismatch_is_not_unregistered_or_installed(target, tmp_path):
    tools = catalog()
    index = AssetIndex(tmp_path)
    selection = choose(tools)
    index.record(success(tmp_path, selection))
    with pytest.raises(AssetError, match="unsupported_target"):
        tools.select_asset("sample.read", target=target, policy=POLICY)
    view = tools.asset_view("sample.read", target=target, policy=POLICY, index=index)
    assert view["available"] == [] and view["selection_status"] == "unsupported_target"
    with pytest.raises(AssetError, match="selection_target_mismatch"):
        tools.asset_view(
            "sample.read", target=target, policy=POLICY, selection=selection
        )


def test_unknown_registration_version_policy_and_backend_facts_are_distinct(tmp_path):
    tools = catalog()
    with pytest.raises(AssetError, match="unregistered_tool"):
        tools.asset_for("missing.tool")
    tools.register(ToolSpec("bare.tool", {}, {}), None)
    with pytest.raises(AssetError, match="unregistered_asset"):
        tools.asset_for("bare.tool")
    with pytest.raises(AssetError, match="no_matching_version"):
        choose(tools, specifier=">=9")
    disabled = AssetPolicy("disabled-1", enabled=False)
    with pytest.raises(AssetError, match="selection_disabled"):
        tools.select_asset("sample.read", target=TARGET, policy=disabled)
    selection = choose(tools)
    index = AssetIndex(tmp_path)
    assert index.installed(selection) == {
        "status": "missing",
        "reason": "local_missing",
    }
    receipt = AssetReceipt(selection, ToolResult("unknown", None, executed=True))
    index.record(receipt)
    assert index.installed(selection)["status"] == "unknown"
    assert index.installed(selection)["reason"] == "backend_unknown"


@pytest.mark.parametrize("status", ["unavailable", "interrupted", "incomplete"])
def test_inconclusive_backend_outcomes_do_not_assert_local_absence(tmp_path, status):
    index, selection = AssetIndex(tmp_path), choose()
    index.record(AssetReceipt(selection, ToolResult(status, 3)))
    view = index.installed(selection)
    assert view["status"] == "unknown" and view["reason"] == "backend_unknown"
    assert view["last_outcome"]["status"] == status


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"version": "latest"}, "mutable_version"),
        ({"backend": "uv"}, "invalid_backend"),
        ({"sha256": "missing"}, "invalid_digest"),
        ({"source": "https://token@example.invalid/tool.zip"}, "invalid_source"),
        (
            {"source": "https://example.invalid/tool.zip?token=private"},
            "invalid_source",
        ),
    ],
)
def test_invalid_distribution_identity_is_rejected_before_backend_use(changes, reason):
    with pytest.raises(AssetError, match=reason):
        native(**changes)


def test_available_installed_and_caller_selection_remain_separate_when_disabled(
    tmp_path,
):
    tools, index = catalog(), AssetIndex(tmp_path)
    selection = choose(tools, version="1.0")
    index.record(success(tmp_path, selection))
    view = tools.asset_view(
        "sample.read",
        target=TARGET,
        policy=AssetPolicy("disabled-2", enabled=False),
        selection=selection,
        index=index,
    )
    assert len(view["available"]) == 2
    assert view["selection_status"] == "selection_disabled"
    assert view["selected"]["release"]["version"] == "1.0"
    assert view["installed"]["status"] == "present"
    assert "ready" not in json.dumps(view)


def test_uv_receipt_uses_locator_environment_and_actual_entry_bytes(tmp_path):
    release = AssetRelease(
        "1.0",
        "python",
        "uv",
        "https://example.invalid/cli.whl",
        "a" * 64,
        "cli",
        package="example-cli",
        requires_python=">=3.14,<3.15",
        lock_ref="lock-sha256:" + "c" * 64,
    )
    tools = catalog(release)
    target = AssetTarget("linux", "x86_64", python="3.14.3")
    selection = tools.select_asset("sample.read", target=target, policy=POLICY)
    with pytest.raises(AssetError, match="unsupported_target"):
        tools.select_asset(
            "sample.read", target=replace(target, python="3.13"), policy=POLICY
        )
    # The uv-owned environment is explicitly located, not copied into the index.
    environment = tmp_path / "uv-environments/cli"
    (environment / "bin").mkdir(parents=True)
    entry = environment / "bin/cli"
    entry.write_bytes(b"real installed entry")
    receipt = AssetReceipt(
        selection,
        ToolResult("passed", 0, executed=True, complete=True, current=True),
        str(environment),
        (AssetFile("bin/cli", hashlib.sha256(entry.read_bytes()).hexdigest()),),
        environment_id="b" * 64,
        verified_source_sha256="a" * 64,
    )
    index = AssetIndex(tmp_path / "assets")
    index.record(receipt)
    assert index.installed(selection)["environment_id"] == "b" * 64
    assert not (index.root / "native").exists()
    entry.write_bytes(b"changed")
    assert index.installed(selection)["reason"] == "integrity_mismatch"
    entry.unlink()
    assert index.installed(selection)["reason"] == "local_missing"


@pytest.mark.parametrize(
    "omission", ["files", "locator", "verified_source_sha256", "environment_id"]
)
def test_no_success_from_backend_claim_without_required_facts(tmp_path, omission):
    selection = choose()
    receipt = success(tmp_path, selection)
    if omission == "environment_id":
        python = AssetRelease(
            "1.0",
            "python",
            "uv",
            "https://example.invalid/cli.whl",
            "a" * 64,
            "cli",
            package="cli",
            requires_python=">=3.14",
        )
        selection = catalog(python).select_asset(
            "sample.read",
            target=AssetTarget("linux", "x86_64", python="3.14"),
            policy=POLICY,
        )
        values = {
            "selection": selection,
            "locator": str(tmp_path),
            "files": (AssetFile("bin/cli", "b" * 64),),
            "verified_source_sha256": "a" * 64,
            "environment_id": "c" * 64,
        }
    else:
        values = {
            "selection": selection,
            "locator": receipt.locator,
            "files": receipt.files,
            "verified_source_sha256": receipt.verified_source_sha256,
            "environment_id": None,
        }
    values[omission] = () if omission == "files" else None
    with pytest.raises(AssetError, match="backend_unknown"):
        AssetReceipt(outcome=receipt.outcome, **values)


def test_failure_receipt_keeps_original_exit_and_previous_verified_installation(
    tmp_path,
):
    index, selection = AssetIndex(tmp_path), choose()
    receipt = success(tmp_path, selection)
    index.record(receipt)
    failed = AssetReceipt(
        selection,
        ToolResult(
            "failed",
            17,
            executed=True,
            outputs={"private": "do-not-store"},
            reason="do-not-store",
        ),
    )
    recorded = index.record(failed)
    assert recorded["outcome"]["status"] == "failed"
    assert recorded["outcome"]["exit_code"] == 17
    assert "do-not-store" not in index.path.read_text()
    view = index.installed(selection)
    assert view["status"] == "present" and view["last_outcome"]["exit_code"] == 17
    Path(receipt.locator, "tool.exe").write_bytes(b"tampered")
    assert index.installed(selection)["reason"] == "integrity_mismatch"


def test_source_hash_and_entry_file_proof_are_independent(tmp_path):
    receipt = success(tmp_path, choose())
    with pytest.raises(AssetError, match="integrity_mismatch"):
        replace(receipt, verified_source_sha256="f" * 64)
    with pytest.raises(AssetError, match="backend_unknown"):
        replace(receipt, files=(AssetFile("unrelated.txt", "a" * 64),))
    with pytest.raises(AssetError, match="integrity_mismatch"):
        AssetIndex(tmp_path).record(
            replace(receipt, files=(AssetFile("tool.exe", "a" * 64),))
        )
    assert not (tmp_path / "index.json").exists()


def test_oci_can_be_frozen_but_index_never_probes_an_engine_or_claims_installation(
    tmp_path,
):
    release = AssetRelease(
        "1.0",
        "oci",
        "oci",
        "ghcr.io/example/cli@sha256:" + "a" * 64,
        "a" * 64,
        "cli",
        os="linux",
        arch="x86_64",
    )
    selection = catalog(release).select_asset(
        "sample.read", target=AssetTarget("linux", "x86_64"), policy=POLICY
    )
    index = AssetIndex(tmp_path)
    index.record(AssetReceipt(selection, ToolResult("unknown", None)))
    assert index.installed(selection)["status"] == "unknown"
    claimed = AssetReceipt(
        selection,
        ToolResult("passed", 0, executed=True, complete=True, current=True),
        str(tmp_path),
        (AssetFile("cli", "b" * 64),),
        verified_source_sha256="a" * 64,
    )
    with pytest.raises(AssetError, match="backend_unknown"):
        index.record(claimed)


def test_registration_composition_and_scope_wrapping_keep_provider_and_one_asset():
    tools = catalog()
    tools.register(ToolSpec("sample.other", {}, {}), None)
    tools.register_asset(tools.asset_for("sample.read"), tools=("sample.other",))
    combined = compose(tools)
    guarded = scoped_catalog(
        combined, DiscoveryScope(permissions=frozenset({"read", "check"}))
    )
    assert guarded.asset_for("sample.read") == guarded.asset_for("sample.other")
    assert choose(guarded).provider == "sample-domain"
    assert choose(guarded).release.backend == "aria2"
    conflicting = catalog(native("9.0"), tool="another.tool")
    before = combined.documents()
    with pytest.raises(AssetError, match="conflicting_asset"):
        combined.merge(conflicting)
    assert combined.documents() == before
    with pytest.raises(AssetError, match="unregistered_tool"):
        tools.register_asset(tools.asset_for("sample.read"), tools=("missing.tool",))


def test_installation_never_changes_existing_binding_digest_or_admission(tmp_path):
    tools = catalog()
    scope = DiscoveryScope(environment="host", permissions=frozenset({"read"}))
    spec = tools.resolve("sample.read")[0]
    binding = create_binding(
        tools, "sample.read", provider="sample-domain", scope=scope
    )
    before = json.dumps(binding, sort_keys=True)
    index = AssetIndex(tmp_path)
    index.record(success(tmp_path, choose(tools)))
    assert (
        json.dumps(
            create_binding(tools, "sample.read", provider="sample-domain", scope=scope),
            sort_keys=True,
        )
        == before
    )
    assert verify_binding(binding, tools, current_scope=scope)[0].sha256 == spec.sha256
    result = ToolRuntime(tools).invoke(
        Invocation("call", "sample.read", {}, 1), binding=binding
    )
    assert result.admission_errors and not result.execution_facts


def test_discovery_and_missing_index_reads_have_no_acquisition_or_write_side_effects(
    tmp_path, monkeypatch
):
    import urllib.request

    from vesryn_tool_runtime import documents

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only discovery attempted an acquisition, engine or write")

    tools = catalog()
    root = tmp_path / "not-created"
    index = AssetIndex(root)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(documents, "write", forbidden)
    tools.documents()
    tools.page()
    tools.search(query="sample")
    tools.resolve("sample.read")
    view = tools.asset_view("sample.read", target=TARGET, policy=POLICY, index=index)
    assert view["selected"] is None and view["installed"]["status"] == "missing"
    assert not root.exists()


def test_invalid_or_tampered_index_is_not_overwritten(tmp_path):
    index, selection = AssetIndex(tmp_path), choose()
    index.record(success(tmp_path, selection))
    document = read(index.path)
    document["entries"][selection.artifact_id]["last_receipt"]["backend"] = "uv"
    write(index.path, document, replace=True)
    before = index.path.read_bytes()
    with pytest.raises(AssetError, match="invalid_index"):
        index.installed(selection)
    with pytest.raises(AssetError, match="invalid_index"):
        index.record(AssetReceipt(selection, ToolResult("failed", 5)))
    assert index.path.read_bytes() == before


def test_receipt_paths_cannot_escape_the_explicit_location(tmp_path):
    receipt = success(tmp_path, choose())
    with pytest.raises(AssetError, match="invalid_receipt"):
        AssetFile("../outside/tool.exe", "a" * 64)
    with pytest.raises(AssetError, match="invalid_location"):
        AssetIndex(tmp_path).record(
            replace(receipt, locator=str(tmp_path / "elsewhere"))
        )


def test_selection_document_checks_integrity_and_schema_version():
    document = choose().document()
    document["release"]["version"] = "8.0"
    with pytest.raises(AssetError, match="invalid_selection"):
        AssetSelection.from_document(document)
    document = choose().document()
    document["schema_version"] = True
    body = {key: value for key, value in document.items() if key != "selection_id"}
    document["selection_id"] = digest(body)
    with pytest.raises(AssetError, match="invalid_selection"):
        AssetSelection.from_document(document)


def test_system_directory_resolution_is_pure_and_explicit_configuration_wins(tmp_path):
    assert asset_root(tmp_path) == tmp_path
    assert (
        asset_root(environ={"LOCALAPPDATA": str(tmp_path)}, platform="win32")
        == tmp_path / "vesryn/tool-assets"
    )
    assert (
        asset_root(environ={"XDG_CACHE_HOME": str(tmp_path)}, platform="linux")
        == tmp_path / "vesryn/tool-assets"
    )
    assert (
        asset_root(environ={"VESRYN_TOOL_ASSETS": str(tmp_path)}, platform="win32")
        == tmp_path
    )
    assert not (tmp_path / "vesryn").exists()


def test_lock_timeout_does_not_rewrite_index(tmp_path):
    index, selection = AssetIndex(tmp_path, timeout=0), choose()
    index.record(success(tmp_path, selection))
    before = index.path.read_bytes()
    with (
        FileLock(str(index.path) + ".lock"),
        pytest.raises(AssetError, match="index_busy"),
    ):
        index.record(AssetReceipt(selection, ToolResult("failed", 7)))
    assert index.path.read_bytes() == before


def test_concurrent_threads_do_not_lose_different_artifacts(tmp_path):
    selections = [choose(catalog(native(str(i)))) for i in range(1, 9)]
    receipts = [success(tmp_path, selection) for selection in selections]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda receipt: AssetIndex(tmp_path).record(receipt), receipts))
    assert len(read(tmp_path / "index.json")["entries"]) == 8
    assert all(
        AssetIndex(tmp_path).installed(item)["status"] == "present"
        for item in selections
    )


def test_concurrent_processes_merge_updates_under_the_same_file_lock(tmp_path):
    root = Path(__file__).resolve().parents[1]
    selections = [choose(catalog(native(str(i)))) for i in range(1, 7)]
    worker = tmp_path / "writer.py"
    worker.write_text(
        """import sys,time
from pathlib import Path
from vesryn_tool_runtime import AssetIndex, AssetReceipt
from vesryn_tool_runtime.documents import read
base=Path(sys.argv[1]); name=sys.argv[2]
receipt=AssetReceipt.from_document(read(base/(name+'.json')))
(base/(name+'.ready')).touch()
deadline=time.monotonic()+15
while not (base/'go').exists():
    if time.monotonic()>deadline: raise RuntimeError('start barrier timeout')
    time.sleep(0.01)
AssetIndex(base/'assets').record(receipt)
""",
        encoding="utf-8",
    )
    for i, selection in enumerate(selections):
        write(
            tmp_path / f"{i}.json", success(tmp_path / "assets", selection).document()
        )
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(vesryn_tool_runtime.__file__).resolve().parent.parent),
    }
    processes = [
        subprocess.Popen(
            [sys.executable, str(worker), str(tmp_path), str(i)],
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for i in range(6)
    ]
    try:
        deadline = time.monotonic() + 15
        while len(list(tmp_path.glob("*.ready"))) != 6:
            if time.monotonic() > deadline:
                pytest.fail("writers failed to reach start barrier")
            time.sleep(0.01)
        (tmp_path / "go").touch()
        for process in processes:
            _, error = process.communicate(timeout=20)
            assert process.returncode == 0, error.decode(errors="replace")
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    assert len(read(tmp_path / "assets/index.json")["entries"]) == 6
    assert all(
        AssetIndex(tmp_path / "assets").installed(item)["status"] == "present"
        for item in selections
    )
