"""Admit and dispatch complete adapter batches, independently reporting observation."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from time import time_ns
from types import MappingProxyType
from uuid import uuid4

from vesryn_log import EventSink

from .binding import verify_binding
from .contracts import ExecutionContext, Invocation, ToolResult
from .documents import WorkflowError, canonical
from .schemas import RESULT, TOOL_EVENT, validate
from .scope import DiscoveryScope

OUTCOMES = {"passed", "failed", "incomplete", "unavailable", "interrupted", "unknown"}


def checked_result(result, spec):
    """Validate execution facts and output without inferring success from delivery."""
    if (
        not isinstance(result, ToolResult)
        or not isinstance(result.status, str)
        or result.status not in OUTCOMES
    ):
        raise WorkflowError("Adapter returned an unsupported result")
    value = result.document()
    validate(value, RESULT, label="tool result")
    canonical(value)
    if type(result.exit_code) not in (int, type(None)):
        raise WorkflowError("Adapter returned an invalid exit status")
    if any(
        type(getattr(result, name)) is not bool
        for name in ("executed", "complete", "current", "reused", "report_generated")
    ):
        raise WorkflowError("Adapter returned invalid execution facts")
    validate(result.outputs, spec.output_schema, label="tool output")
    if result.status == "passed" and not (
        result.exit_code == 0 and result.executed and result.complete and result.current
    ):
        raise WorkflowError("Passed result lacks current complete execution evidence")
    if result.status == "failed" and not result.exit_code:
        raise WorkflowError("Failed result lacks a nonzero exit status")
    return value


@dataclass
class DispatchReceipt:
    """Execution results and safe, separate diagnostics for this dispatch only."""

    results: dict = field(default_factory=dict)
    execution_facts: dict = field(default_factory=dict)
    invocation_ids: dict = field(default_factory=dict)
    batch_ids: dict = field(default_factory=dict)
    admission_errors: dict = field(default_factory=dict)
    validation_errors: dict = field(default_factory=dict)
    observation_errors: list = field(default_factory=list)
    observation_status: str = "not_configured"
    interrupted: bool = False


def _invalid_result(original, spec, interrupted):
    failure = (
        isinstance(original, ToolResult)
        and original.status == "failed"
        and type(original.exit_code) is int
        and original.exit_code != 0
    )
    code = (
        original.exit_code
        if isinstance(original, ToolResult)
        and type(original.exit_code) is int
        and original.exit_code != 0
        else (130 if interrupted else 3)
    )
    retained = (
        original.status
        if isinstance(original, ToolResult)
        and isinstance(original.status, str)
        and original.status in {"interrupted", "unknown"}
        else None
    )
    return ToolResult(
        "unknown"
        if spec.recovery == "manual"
        else "failed"
        if failure
        else retained
        if retained is not None
        else "interrupted"
        if interrupted
        else "unavailable",
        code,
        executed=isinstance(original, ToolResult) and original.executed is True,
        reason="Tool result unavailable or invalid; inspect original tool evidence",
        summary="The adapter returned no valid tool result; execution completion is uncertain.",
    ).document()


def _execution_facts(original):
    """Retain safe Adapter-reported facts independently of output validation."""
    value = {"status": None, "exit_code": None}
    if isinstance(original, ToolResult):
        if isinstance(original.status, str) and original.status in OUTCOMES:
            value["status"] = original.status
        if type(original.exit_code) in (int, type(None)):
            value["exit_code"] = original.exit_code
        for key in ("executed", "complete", "current", "reused", "report_generated"):
            fact = getattr(original, key)
            if type(fact) is bool:
                value[key] = fact
    return value


class ToolRuntime:
    """No workflow, persistence, retries, provider selection or transport fallback.

    The host supplies an admitted scope, optional public EventSink, and any adapter
    context. Each adapter receives all of its admitted calls in one invocation.
    Bindings are keyed by step_id and reverified against this current Catalog and
    scope. Before dispatch, hosts own durable intent and manual recovery decisions.
    """

    def __init__(self, catalog, *, scope=None, event_sink: EventSink | None = None):
        self.catalog = catalog
        self.scope = (
            scope
            if scope is not None
            else getattr(catalog, "discovery_scope", DiscoveryScope())
        )
        self.event_sink = event_sink

    def invoke(self, call, context=None, *, binding=None):
        return self.dispatch(
            (call,),
            context,
            bindings=None if binding is None else {call.step_id: binding},
        )

    def dispatch(self, calls, context=None, *, bindings=None, batch_id=None):
        try:
            calls = tuple(deepcopy(tuple(calls)))
        except TypeError, ValueError, RecursionError:
            raise WorkflowError("Invocation batch cannot be copied safely") from None
        if not calls or any(not isinstance(call, Invocation) for call in calls):
            raise WorkflowError("Invocation batch must contain Invocation objects")
        if (
            any(not isinstance(call.step_id, str) or not call.step_id for call in calls)
            or len({call.step_id for call in calls}) != len(calls)
            or any(type(call.attempt) is not int or call.attempt < 1 for call in calls)
        ):
            raise WorkflowError(
                "Invocation identities must be unique with positive attempts"
            )
        if bindings is not None and (
            not isinstance(bindings, Mapping)
            or set(bindings) - {call.step_id for call in calls}
        ):
            raise WorkflowError("Bindings must name calls in the current batch")
        context = context or ExecutionContext(
            "", "", "", Path.cwd(), MappingProxyType({})
        )
        receipt = DispatchReceipt(
            observation_status="complete"
            if self.event_sink is not None
            else "not_configured"
        )
        groups = {}
        recovery_required = False
        # Resolve the entire request before dispatch, so unknown tools never cause a
        # partially executed batch. Admission is repeated immediately before invoke.
        selected = {call.step_id: self.catalog.resolve(call.tool_id) for call in calls}
        for call in calls:
            spec, adapter = selected[call.step_id]
            receipt.invocation_ids[call.step_id] = uuid4().hex
            groups.setdefault(id(adapter), (adapter, []))[1].append(call)
        for adapter, group in groups.values():
            identity = batch_id or uuid4().hex
            admitted = []
            for call in group:
                spec, _ = selected[call.step_id]
                receipt.batch_ids[call.step_id] = identity
                if receipt.interrupted or recovery_required:
                    receipt.results[call.step_id] = ToolResult(
                        "interrupted" if receipt.interrupted else "unavailable",
                        130 if receipt.interrupted else 3,
                        reason="Batch stopped before this adapter was dispatched; host continuation is required",
                    ).document()
                    self._emit(
                        receipt, "rejected", call, spec, context, identity, len(group)
                    )
                    continue
                try:
                    self.scope.admit(spec)
                    canonical(call.inputs)
                    validate(call.inputs, spec.input_schema, label="tool input")
                    if bindings is not None and call.step_id in bindings:
                        binding = bindings[call.step_id]
                        verify_binding(binding, self.catalog, current_scope=self.scope)
                        if binding.get("execution_id") is not None and binding[
                            "execution_id"
                        ] != getattr(context, "execution_id", None):
                            raise WorkflowError(
                                "Invocation execution differs from its selection binding"
                            )
                        if binding["tool_id"] != call.tool_id or canonical(
                            binding["parameters"]
                        ) != canonical(call.inputs):
                            raise WorkflowError(
                                "Invocation differs from its selection binding"
                            )
                    if spec.recovery == "manual" and call.previous is not None:
                        raise WorkflowError(
                            "Write tools require domain-owned manual recovery"
                        )
                    admitted.append(call)
                except WorkflowError:
                    receipt.admission_errors[call.step_id] = (
                        "Invocation admission failed"
                    )
                    receipt.results[call.step_id] = ToolResult(
                        "unavailable",
                        3,
                        reason="Tool inputs, binding or current scope do not admit this call",
                    ).document()
                    self._emit(
                        receipt, "rejected", call, spec, context, identity, len(group)
                    )
            for call in admitted:
                self._emit(
                    receipt,
                    "invoking",
                    call,
                    selected[call.step_id][0],
                    context,
                    identity,
                    len(group),
                )
            if not admitted:
                continue
            interrupted = False
            try:
                results = adapter.invoke(tuple(admitted), context)
                if not isinstance(results, Mapping) or set(results) != {
                    call.step_id for call in admitted
                }:
                    raise WorkflowError("Adapter batch omitted a requested result")
            except KeyboardInterrupt:
                results, interrupted = {}, True
                receipt.interrupted = True
            except Exception:  # noqa: BLE001 -- SDK diagnostics may contain credentials
                results = {}
            for call in admitted:
                spec, _ = selected[call.step_id]
                original = results.get(call.step_id)
                receipt.execution_facts[call.step_id] = _execution_facts(original)
                try:
                    result = checked_result(original, spec)
                except WorkflowError, TypeError, ValueError, RecursionError:
                    receipt.validation_errors[call.step_id] = (
                        "Tool result unavailable or invalid"
                    )
                    result = _invalid_result(original, spec, interrupted)
                receipt.results[call.step_id] = result
                if result["status"] == "interrupted":
                    receipt.interrupted = True
                if result["status"] == "unknown":
                    recovery_required = True
                self._emit(
                    receipt, "returned", call, spec, context, identity, len(group)
                )
        return receipt

    def _emit(self, receipt, event, call, spec, context, batch_id, batch_size):
        if self.event_sink is None:
            return
        value = {
            "schema_version": 1,
            "kind": "tool-invocation-observation",
            "event": event,
            "observed_ns": time_ns(),
            "tool_id": spec.tool_id,
            "invocation_id": receipt.invocation_ids[call.step_id],
            "batch_id": batch_id,
            "batch_size": batch_size,
            "attempt": call.attempt,
            "contract_version": spec.contract_version,
            "contract_sha256": spec.sha256,
        }
        if getattr(context, "execution_id", None):
            value["execution_id"] = context.execution_id
        if call.step_id in receipt.results:
            result = receipt.results[call.step_id]
            value.update(
                {
                    key: result[key]
                    for key in (
                        "status",
                        "exit_code",
                        "executed",
                        "complete",
                        "current",
                        "reused",
                        "report_generated",
                    )
                }
            )
            value["result_validation"] = (
                "invalid"
                if call.step_id in receipt.validation_errors
                else "not_executed"
                if event == "rejected"
                else "valid"
            )
            original = receipt.execution_facts.get(call.step_id, {})
            value["execution_status"] = original.get("status")
            value["result_exit_code"] = result["exit_code"]
            value["exit_code"] = original.get("exit_code")
        try:
            validate(value, TOOL_EVENT, label="tool observation")
            self.event_sink.emit(value)
        except Exception:  # noqa: BLE001 -- separate recording policy, no raw sink diagnostics
            receipt.observation_errors.append(
                {
                    "invocation_id": value["invocation_id"],
                    "event": event,
                    "reason": "Tool observation write failed",
                }
            )
            receipt.observation_status = "incomplete"


def invoke_tool(
    tool_id, inputs=None, *, catalog, scope, context=None, binding=None, event_sink=None
):
    """Direct single-call API; no Workflow construction or on-disk side effects."""
    return ToolRuntime(catalog, scope=scope, event_sink=event_sink).invoke(
        Invocation("call", tool_id, {} if inputs is None else inputs, 1),
        context,
        binding=binding,
    )
