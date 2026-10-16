"""Independent public-chain verification, including hostile results and recording loss."""

import json
from dataclasses import replace

import pytest
from vesryn_log import JsonlSink

from vesryn_tool_runtime import (
    Catalog,
    DiscoveryScope,
    Invocation,
    ToolResult,
    ToolRuntime,
    ToolRuntimeError,
    ToolSpec,
    canonical_binding,
    compose,
    create_binding,
    invoke_tool,
    verify_binding,
)
from vesryn_tool_runtime.documents import digest
from vesryn_tool_runtime.schemas import object_schema

NUMBER = object_schema({"value": {"type": "integer"}})
SCOPE = DiscoveryScope(
    repository="example", environment="host", permissions=frozenset({"check"})
)


class Adapter:
    def __init__(self, result=None, error=None):
        self.batches = []
        self.result, self.error = result, error

    def invoke(self, calls, context):
        self.batches.append(calls)
        if self.error:
            raise self.error
        return {
            call.step_id: self.result
            or ToolResult(
                "passed",
                0,
                {"value": call.inputs["value"] + 1},
                executed=True,
                complete=True,
                current=True,
            )
            for call in calls
        }


def registered(adapter=None, spec=None, provider="example"):
    tools = Catalog()
    tools.provider_name = provider
    adapter = adapter or Adapter()
    tools.register(
        spec or ToolSpec("math.increment", NUMBER, NUMBER, use_when=("increment",)),
        adapter,
    )
    return tools, adapter


def test_registration_discovery_binding_invocation_and_actual_event_sink(tmp_path):
    tools, adapter = registered()
    assert (
        tools.search(operation="increment", scope=SCOPE)[0]["tool_id"]
        == "math.increment"
    )
    assert "input_schema" not in tools.page()["tools"][0]
    assert tools.page(details=True)["tools"][0]["input_schema"] == NUMBER
    binding = create_binding(
        tools,
        "math.increment",
        provider="example",
        parameters={"value": 3},
        scope=SCOPE,
    )
    receipt = invoke_tool(
        "math.increment",
        {"value": 3},
        catalog=tools,
        scope=SCOPE,
        binding=binding,
        event_sink=JsonlSink(tmp_path / "events.jsonl"),
    )
    assert receipt.results["call"]["outputs"] == {"value": 4}
    assert receipt.observation_status == "complete"
    assert len(adapter.batches) == 1
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert [event["event"] for event in events] == ["invoking", "returned"]
    assert events[0]["invocation_id"] == events[1]["invocation_id"]
    assert events[1]["contract_sha256"] == binding["contract_sha256"]
    assert events[1]["exit_code"] == 0
    assert all("parameters" not in event and "outputs" not in event for event in events)


def test_duplicate_registration_and_atomic_provider_merge():
    tools, adapter = registered()
    with pytest.raises(ToolRuntimeError, match="Duplicate"):
        tools.register(tools.resolve("math.increment")[0], adapter)
    second, _ = registered()
    second.register(ToolSpec("math.second", NUMBER, NUMBER), adapter)
    with pytest.raises(ToolRuntimeError, match="Duplicate"):
        tools.merge(second)
    assert tools.page()["total"] == 1


def test_composition_preserves_provider_identity_and_batching():
    first, adapter = registered()
    second, other = registered(
        spec=ToolSpec("math.other", NUMBER, NUMBER), provider="other"
    )
    tools = compose(first, second)
    binding = create_binding(
        tools, "math.other", provider="other", parameters={"value": 1}, scope=SCOPE
    )
    assert (
        verify_binding(binding, tools, current_scope=SCOPE)[0].tool_id == "math.other"
    )
    receipt = ToolRuntime(tools, scope=SCOPE).dispatch(
        (
            Invocation("one", "math.increment", {"value": 1}, 1),
            Invocation("two", "math.increment", {"value": 2}, 1),
            Invocation("other", "math.other", {"value": 3}, 1),
        )
    )
    assert [len(batch) for batch in adapter.batches] == [2]
    assert [len(batch) for batch in other.batches] == [1]
    assert len(set(receipt.invocation_ids.values())) == 3
    assert (
        receipt.batch_ids["one"]
        == receipt.batch_ids["two"]
        != receipt.batch_ids["other"]
    )


@pytest.mark.parametrize(
    "field,value",
    [("version", "2"), ("contract_sha256", "a" * 64), ("provider", "wrong")],
)
def test_binding_rejects_current_identity_mismatch(field, value):
    tools, adapter = registered()
    binding = create_binding(
        tools,
        "math.increment",
        provider="example",
        parameters={"value": 1},
        scope=SCOPE,
    )
    binding[field] = value
    binding["binding_id"] = digest(canonical_binding(binding))
    receipt = invoke_tool(
        "math.increment", {"value": 1}, catalog=tools, scope=SCOPE, binding=binding
    )
    assert receipt.admission_errors and not adapter.batches


def test_binding_integrity_and_parameters_are_not_authorization():
    tools, adapter = registered()
    binding = create_binding(
        tools,
        "math.increment",
        provider="example",
        parameters={"value": 1},
        scope=SCOPE,
    )
    altered = {**binding, "parameters": {"value": 2}}
    with pytest.raises(ToolRuntimeError, match="integrity"):
        verify_binding(altered, tools, current_scope=SCOPE)
    receipt = invoke_tool(
        "math.increment", {"value": 2}, catalog=tools, scope=SCOPE, binding=binding
    )
    assert receipt.admission_errors
    receipt = invoke_tool(
        "math.increment",
        {"value": 1},
        catalog=tools,
        scope=replace(SCOPE, permissions=None),
        binding=binding,
    )
    assert receipt.admission_errors and not adapter.batches


def test_discovery_filters_before_limit_and_execution_revalidates_constraints():
    tools, adapter = registered()
    tools.register(ToolSpec("alpha.read", NUMBER, NUMBER, effect="read"), adapter)
    allowed = {"value": True}
    scope = replace(SCOPE, constraint=lambda spec, current: allowed["value"])
    assert tools.page(limit=1, scope=scope)["tools"][0]["tool_id"] == "math.increment"
    allowed["value"] = False
    assert tools.search(scope=scope) == []
    assert invoke_tool(
        "math.increment", {"value": 1}, catalog=tools, scope=scope
    ).admission_errors
    assert not adapter.batches


@pytest.mark.parametrize(
    "inputs",
    [{"value": "wrong"}, {"value": float("nan")}, {"value": 1, "secret": "credential"}],
)
def test_invalid_input_never_reaches_adapter(inputs):
    tools, adapter = registered()
    receipt = invoke_tool("math.increment", inputs, catalog=tools, scope=SCOPE)
    assert receipt.results["call"]["status"] == "unavailable" and not adapter.batches


@pytest.mark.parametrize(
    "status,code",
    [
        ("failed", 7),
        ("interrupted", 130),
        ("unknown", None),
        ("unavailable", 3),
        ("incomplete", None),
    ],
)
def test_original_outcomes_and_exit_codes_are_retained(status, code):
    tools, _ = registered(Adapter(ToolResult(status, code, {"value": 1})))
    result = invoke_tool(
        "math.increment", {"value": 1}, catalog=tools, scope=SCOPE
    ).results["call"]
    assert (result["status"], result["exit_code"]) == (status, code)


@pytest.mark.parametrize(
    "status,code,expected", [("failed", -9, "failed"), ("passed", 0, "unavailable")]
)
def test_execution_failure_and_result_validation_failure_stay_distinct(
    status, code, expected
):
    tools, _ = registered(
        Adapter(
            ToolResult(status, code, {}, executed=True, complete=True, current=True)
        )
    )
    receipt = invoke_tool("math.increment", {"value": 1}, catalog=tools, scope=SCOPE)
    assert receipt.validation_errors
    assert receipt.results["call"]["status"] == expected
    assert receipt.results["call"]["exit_code"] == (code or 3)


@pytest.mark.parametrize(
    "error,status,code",
    [
        (KeyboardInterrupt(), "interrupted", 130),
        (RuntimeError("private token"), "unavailable", 3),
    ],
)
def test_unreturned_adapter_call_has_safe_outcome(error, status, code):
    tools, _ = registered(Adapter(error=error))
    receipt = invoke_tool("math.increment", {"value": 1}, catalog=tools, scope=SCOPE)
    result = receipt.results["call"]
    assert (result["status"], result["exit_code"]) == (status, code)
    assert "private token" not in json.dumps(result)


def test_write_tool_uncertainty_and_manual_recovery():
    tools, adapter = registered(
        Adapter(error=KeyboardInterrupt()),
        spec=ToolSpec(
            "math.increment", NUMBER, NUMBER, effect="write", recovery="manual"
        ),
    )
    scope = replace(SCOPE, permissions=frozenset({"write"}))
    receipt = invoke_tool("math.increment", {"value": 1}, catalog=tools, scope=scope)
    assert receipt.results["call"]["status"] == "unknown"
    receipt = ToolRuntime(tools, scope=scope).invoke(
        Invocation("again", "math.increment", {"value": 1}, 2, {"status": "unknown"})
    )
    assert receipt.admission_errors and len(adapter.batches) == 1


def test_observation_failure_never_changes_original_failure_or_leaks_arguments():
    class Broken:
        def emit(self, event):
            raise OSError("credential from sink")

    tools, _ = registered(Adapter(ToolResult("failed", 12, {"value": 1})))
    receipt = invoke_tool(
        "math.increment", {"value": 1}, catalog=tools, scope=SCOPE, event_sink=Broken()
    )
    assert receipt.results["call"]["exit_code"] == 12
    assert (
        receipt.observation_status == "incomplete"
        and len(receipt.observation_errors) == 2
    )
    assert "credential" not in json.dumps(receipt.observation_errors)


def test_unknown_tool_and_duplicate_call_identity_fail_before_any_execution():
    tools, adapter = registered()
    calls = (
        Invocation("one", "math.increment", {"value": 1}, 1),
        Invocation("two", "math.missing", {}, 1),
    )
    with pytest.raises(ToolRuntimeError, match="not registered"):
        ToolRuntime(tools, scope=SCOPE).dispatch(calls)
    with pytest.raises(ToolRuntimeError, match="unique"):
        ToolRuntime(tools, scope=SCOPE).dispatch((calls[0], calls[0]))
    assert not adapter.batches


def test_interruption_stops_subsequent_adapter_dispatch():
    first, _ = registered(Adapter(error=KeyboardInterrupt()))
    second, adapter = registered(
        spec=ToolSpec("math.second", NUMBER, NUMBER), provider="second"
    )
    receipt = ToolRuntime(compose(first, second), scope=SCOPE).dispatch(
        (
            Invocation("one", "math.increment", {"value": 1}, 1),
            Invocation("two", "math.second", {"value": 1}, 1),
        )
    )
    assert receipt.interrupted and not adapter.batches
    assert receipt.results["two"]["status"] == "interrupted"
    assert receipt.results["two"]["executed"] is False


def test_invalid_success_retains_actual_exit_and_execution_facts_in_events():
    class Sink:
        def __init__(self):
            self.events = []

        def emit(self, event):
            self.events.append(event)

    sink = Sink()
    tools, _ = registered(
        Adapter(ToolResult("passed", 0, {}, executed=True, complete=True, current=True))
    )
    receipt = invoke_tool(
        "math.increment", {"value": 1}, catalog=tools, scope=SCOPE, event_sink=sink
    )
    assert receipt.results["call"]["status"] == "unavailable"
    assert receipt.execution_facts["call"]["exit_code"] == 0
    event = sink.events[-1]
    assert event["execution_status"] == "passed" and event["exit_code"] == 0
    assert event["status"] == "unavailable" and event["result_exit_code"] == 3
    assert event["result_validation"] == "invalid"


@pytest.mark.parametrize("status,code", [("unknown", 3), ("interrupted", 130)])
def test_invalid_outputs_preserve_unknown_and_interrupted_outcomes(status, code):
    tools, _ = registered(Adapter(ToolResult(status, code, {})))
    receipt = invoke_tool("math.increment", {"value": 1}, catalog=tools, scope=SCOPE)
    assert receipt.results["call"]["status"] == status
    assert receipt.execution_facts["call"]["exit_code"] == code
    assert receipt.validation_errors


@pytest.mark.parametrize("status,code", [("interrupted", 130), ("unknown", 3)])
def test_reported_stop_outcome_never_starts_later_adapter_groups(status, code):
    first, _ = registered(Adapter(ToolResult(status, code, {"value": 1})))
    second, adapter = registered(
        spec=ToolSpec("math.second", NUMBER, NUMBER), provider="second"
    )
    receipt = ToolRuntime(compose(first, second), scope=SCOPE).dispatch(
        (
            Invocation("one", "math.increment", {"value": 1}, 1),
            Invocation("two", "math.second", {"value": 1}, 1),
        )
    )
    assert receipt.results["one"]["status"] == status
    assert not adapter.batches and receipt.results["two"]["executed"] is False
    assert receipt.results["two"]["status"] == (
        "interrupted" if status == "interrupted" else "unavailable"
    )
