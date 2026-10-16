# Failure and observation semantics

The runtime preserves valid `passed`, `failed`, `incomplete`, `unavailable`,
`interrupted` and `unknown` results with their original integer/null exit codes,
including negative native signal codes. It does not translate native exit codes
to shell conventions; Workflow may retain its existing outer CLI conversion.

`passed` requires exit 0 and executed, complete, current evidence. `failed`
requires a nonzero exit status. Every result validates the declared output schema.
Report generation and reuse never establish success or current evidence alone.

Admission failure returns unavailable without dispatch. Unknown tool IDs or
invalid batch identities raise ToolRuntimeError before any Adapter runs. An
Adapter must return precisely the requested result keys; an invalid envelope is
treated as unavailable evidence. Exceptions are sanitized; KeyboardInterrupt
returns interrupted/130 for restartable tools and unknown for manual writes.

If execution failed and output validation also fails, the nonzero exit code and
failed status remain authoritative for restartable tools. `validation_errors`
reports the independent evidence problem. A manual write with invalid/missing
evidence is unknown. Invalid output is not exposed as validated evidence; safe
normalization can return empty outputs even if the tool schema requires fields.
Such a result is explicitly marked in `validation_errors` and never passed.
`execution_facts` retains the original Adapter status, actual integer/null exit
code and well-typed execution flags independently. Unknown and interrupted outcomes
remain unknown/interrupted even when their output validation fails.

Existing previous-result evidence is passed unchanged to the Adapter after input
admission. Calls with previous evidence for a manual-write tool require the host's
domain recovery path and are rejected by direct dispatch. No retry, tool switch
or transport fallback occurs in the generic package.

Events use the existing `vesryn_log.EventSink.emit(Mapping)` API. Only these fields
are emitted: schema/kind/event/time; Tool ID, Invocation ID, optional Execution ID,
Batch ID/size, Attempt, contract version/hash, and returned status, actual exit
code, execution/completeness/current/reuse/report facts and validation state.
`status` describes the runtime result, `execution_status` the original Adapter
outcome, `exit_code` the actual Adapter exit (null when unobserved), and
`result_exit_code` the normalized runtime code. For example, a process returning
0 with invalid output records actual exit 0 and result unavailable/3 separately.
Batch size counts the requested calls for that Adapter group. An interrupted
Adapter prevents later Adapter groups from being dispatched.
An Adapter-reported unknown outcome also stops later groups; they return
unavailable without execution so the host owns any continuation/recovery decision.
Parameters, credentials, raw outputs, summaries, reasons and SDK exceptions are
excluded. Invoking/returned share invocation and batch identities.
The normative JSON Schema is `vesryn_tool_runtime.schemas.TOOL_EVENT`.

Sink exceptions become safe `observation_errors`; they do not change tool status,
exit code or output. A caller requiring observation must configure a sink and
inspect `observation_status` separately. `complete` covers only emitted boundaries
for this dispatch, not global task coverage. Crash recovery and guarantees beyond
the Sink protocol belong to the host. Vesryn records tool events through JsonlSink
and adds recording errors to its existing independent observation error count.
