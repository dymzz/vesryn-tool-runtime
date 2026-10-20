"""Public ownership and JSON/Schema boundaries independent of any consumer."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

import vesryn_tool_runtime
from vesryn_tool_runtime import (
    Catalog,
    ToolResult,
    ToolRuntime,
    ToolRuntimeError,
    ToolSpec,
)
from vesryn_tool_runtime.documents import canonical, decode
from vesryn_tool_runtime.registry import provider, scoped_catalog
from vesryn_tool_runtime.scope import DiscoveryScope


def test_package_has_no_reverse_imports_or_workflow_dependencies():
    for path in Path(vesryn_tool_runtime.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = (
                [entry.name for entry in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            assert not any(
                name.split(".")[0]
                in {"vesryn", "engineering_ci", "dagger", "transitions"}
                for name in modules
            )


@pytest.mark.parametrize(
    "raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]", b'{"a":Infinity}']
)
def test_json_identity_boundary(raw):
    with pytest.raises(ToolRuntimeError):
        decode(raw)
    assert canonical({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_remote_schema_references_are_rejected_without_fetching():
    with pytest.raises(ToolRuntimeError, match="local references"):
        Catalog().register(
            ToolSpec("test.schema", {"$ref": "https://example.invalid/schema"}, {}),
            None,
        )


def test_scoped_catalog_preserves_provider_and_batch_identity():
    class Adapter:
        def invoke(self, calls, context):
            return {call.step_id: ToolResult("failed", 7) for call in calls}

    tools = Catalog()
    tools.provider_name = "example"
    adapter = Adapter()
    for name in ("test.first", "test.second"):
        tools.register(ToolSpec(name, {}, {}), adapter)
    scoped = scoped_catalog(tools, DiscoveryScope(permissions=frozenset({"check"})))
    assert scoped.provider_for("test.first") == "example"
    assert scoped.resolve("test.first")[1] is scoped.resolve("test.second")[1]
    assert ToolRuntime(scoped).scope is scoped.discovery_scope


def test_provider_requires_unique_explicit_entry_point_and_valid_identity(monkeypatch):
    from types import SimpleNamespace

    from vesryn_tool_runtime import registry

    tools = Catalog()
    tools.provider_name = "different"
    entry = SimpleNamespace(name="example", load=lambda: lambda **kwargs: tools)
    monkeypatch.setattr(registry, "entry_points", lambda **kwargs: [entry])
    with pytest.raises(ToolRuntimeError, match="identity"):
        provider("example", Path.cwd())
    with pytest.raises(ToolRuntimeError, match="explicit"):
        provider("absent", Path.cwd())
    tools.provider_name = "example"
    assert provider("example", Path.cwd()) is tools


def test_contract_metadata_changes_do_not_change_semantic_identity():
    spec = ToolSpec("test.identity", {}, {})
    assert (
        replace(spec, display_name="Friendly", description="New purpose").sha256
        == spec.sha256
    )
    assert replace(spec, environments=("dagger",)).sha256 != spec.sha256


def test_original_engineering_schema1_document_remains_readable():
    from vesryn_tool_runtime import verify_binding
    from vesryn_tool_runtime.documents import read
    from vesryn_tool_runtime.schemas import object_schema

    # Created by the original engineering-ci create_binding function captured
    # before extraction, including its original workflow association and digest.
    binding = read(Path(__file__).parent / "fixtures/selection-binding-schema1.json")
    tools = Catalog()
    tools.provider_name = "legacy-provider"
    number = object_schema({"value": {"type": "integer"}})
    tools.register(
        ToolSpec("legacy.check", number, number, environments=("dagger",)), None
    )
    scope = DiscoveryScope(
        repository="example", environment="dagger", permissions=frozenset({"check"})
    )
    spec, _ = verify_binding(binding, tools, current_scope=scope)
    assert spec.sha256 == binding["contract_sha256"]


def test_real_log_sink_preserves_failure_and_excludes_private_payloads(tmp_path):
    import json

    from vesryn_log import JsonlSink
    from vesryn_tool_runtime import Invocation

    class Adapter:
        def invoke(self, calls, context):
            return {
                call.step_id: ToolResult("failed", 7, reason="private adapter reason")
                for call in calls
            }

    tools = Catalog()
    tools.register(ToolSpec("example.check", {}, {}), Adapter())
    journal = tmp_path / "tool-events.jsonl"
    receipt = ToolRuntime(
        tools,
        scope=DiscoveryScope(permissions=frozenset({"check"})),
        event_sink=JsonlSink(journal),
    ).invoke(Invocation("call", "example.check", {"private": "private input value"}, 1))
    assert receipt.results["call"]["exit_code"] == 7
    assert receipt.observation_status == "complete" and not receipt.observation_errors
    raw = journal.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw.splitlines()]
    assert events and all(event["tool_id"] == "example.check" for event in events)
    assert "private input value" not in raw and "private adapter reason" not in raw
