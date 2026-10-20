# TR-001 — Binding 与准入公共契约兼容核对

本文件记录 [Issue #2](https://github.com/dymzz/vesryn-tool-runtime/issues/2)
([P1][TR-001][按需] Binding 与准入公共契约兼容核对) 的核对结论。

任务为按需启动；当前未收到消费者的明确公共 API 疑问或可复现的上游缺口。
本核对在不修改本仓库实现的前提下完成，仅基于当前公开 head
(`e88935002e898be79216a9e5c0f3326019623850`，版本 `0.1.0`) 与已交付 wheel。

## 版本与可复核产物

| 项 | 值 |
| --- | --- |
| 版本 | `vesryn-tool-runtime==0.1.0` |
| Wheel | `dist/vesryn_tool_runtime-0.1.0-py3-none-any.whl` |
| Wheel SHA-256 | `93ce72f1c9119ad9802b6c94bc0cfa4ca769d76b21c644d7c48419bb4d3fff5e` |
| Wheel 大小 | 24 768 bytes |
| 源分布 | `dist/vesryn_tool_runtime-0.1.0.tar.gz` |
| Git 头 | `e88935002e898be79216a9e5c0f3326019623850` |
| Python | `>=3.14` |
| 依赖 | `jsonschema==4.26.0`, `vesryn-log==0.1.0`（实测该 wheel 的 `METADATA`；开发源 pin 同一 `0.1.0` 提交） |

上表是本次核对所依据的 `0.1.0` 已交付 wheel 的实测元数据。依赖范围的放宽属于
独立任务，不在本核对内变更。

## 已交付的可复用公共 API

下列 API 来自 `src/vesryn_tool_runtime/` 与 `docs/python-api.md`，未在本任务
内被修改；消费者可直接复用。表格与文档保持一致。

| API | 模块 | 签名 | 用途 |
| --- | --- | --- | --- |
| `Catalog.register` | `contracts.py` | `(spec: ToolSpec, adapter: ToolAdapter)` | 注册一个 `(spec, adapter)` 装配；显式 Provider 持有 |
| `Catalog.resolve` | `contracts.py` | `(tool_id, *, scope=None)` | 按当前 Catalog 与 scope 解析一项工具 |
| `Catalog.provider_for` | `contracts.py` | `(tool_id)` | 取回冻结 Binding 所需的 Provider 身份 |
| `Catalog.merge` / `compose(*catalogs)` | `contracts.py` / `registry.py` | 原子拒绝重复所有权 | 跨 Provider 合并 |
| `Catalog.page` / `Catalog.search` | `contracts.py` | 渐进式披露，仅 `search` 可作初步挑选 | 不替代 Binding |
| `DiscoveryScope.matches` / `DiscoveryScope.admit` | `scope.py` | `(spec)` | 域过滤与最终准入 |
| `create_binding` | `binding.py` | `(catalog, tool_id, *, provider, parameters=None, scope=None)` | 冻结 Schema 1 Selection Binding |
| `verify_binding` | `binding.py` | `(binding, catalog, *, current_scope=None)` | 校验完整性 + 当前版本/hash/summary、Provider、参数、scope |
| `verify_document` | `binding.py` | `(binding)` | 仅做 Schema 与 `binding_id` 完整性 |
| `SELECTION_BINDING` | `binding.py` | JSON Schema 常量 | Schema 1 文档结构 |
| `ToolRuntime.invoke` | `invocation.py` | `(call, context=None, *, binding=None)` | 单次调用；支持 Binding 重新校验 |
| `ToolRuntime.dispatch` | `invocation.py` | `(calls, context=None, *, bindings=None, batch_id=None)` | 多调用批；按 step_id 重新校验 Binding |
| `invoke_tool` | `invocation.py` | `(tool_id, inputs=None, *, catalog, scope, context=None, binding=None, event_sink=None)` | 直接单步 API；**已接受 Binding 参数** |
| `checked_result` | `invocation.py` | `(result, spec)` | 严格结果校验 |

`Invocation(step_id, tool_id, inputs, attempt, previous=None)`、`ToolResult`
（`status`、`exit_code`、`outputs`、`executed/complete/current/reused/report_generated`、
`reason`、可选 `summary`）、`ExecutionContext` 与 `DispatchReceipt`
（`results`、`execution_facts`、`invocation_ids`、`admission_errors`、
`validation_errors`、`observation_errors`、`observation_status`、`interrupted`）
均为既有事实契约；不在任务范围内变动。

## 已覆盖的契约条款

| 条款 | 已覆盖测试 |
| --- | --- |
| Provider / hash / 参数 / scope 在 Adapter 调用前拒绝变化 | `test_binding_rejects_current_identity_mismatch`, `test_binding_integrity_and_parameters_are_not_authorization`, `test_discovery_filters_before_limit_and_execution_revalidates_constraints` |
| 原 `failed` / `interrupted` / `unknown` / `unavailable` / `incomplete` 结果保留 | `test_original_outcomes_and_exit_codes_are_retained`, `test_invalid_outputs_preserve_unknown_and_interrupted_outcomes`, `test_reported_stop_outcome_never_starts_later_adapter_groups` |
| 真实 Sink 失败与原结果分离，不影响 `exit_code`、状态、`outputs` | `test_observation_failure_never_changes_original_failure_or_leaks_arguments`（stub Sink）与 `tests/test_boundaries.py::test_real_log_sink_preserves_failure_and_excludes_private_payloads`（`vesryn_log.JsonlSink`） |
| 公开事件不含 `parameters`、`outputs`、`reason` 与原始 SDK 异常 | `test_registration_discovery_binding_invocation_and_actual_event_sink`, `test_unreturned_adapter_call_has_safe_outcome`, `tests/test_boundaries.py::test_real_log_sink_preserves_failure_and_excludes_private_payloads` |
| 写工具的不确定性 + 宿主手动恢复边界 | `test_write_tool_uncertainty_and_manual_recovery` |
| 现有 `Selection Binding Schema 1` 仍可读 | `test_original_engineering_schema1_document_remains_readable`（legacy fixture） |

回归基线：

```
tests/test_boundaries.py ........... 11 passed
tests/test_runtime.py .............. 29 passed
tests/test_app.py ..................  1 passed
========================= 41 passed in 0.53s =========================
```

## 消费者转发项（不属于本仓修改）

1. **Vesryn 上层 `invoke_tool` 缺少 `binding` 透传**：本仓 `invoke_tool` 的
   签名 `(tool_id, inputs=None, *, catalog, scope, context=None, binding=None,
   event_sink=None)` 已包含 `binding` 关键字参数；Vesryn 侧
   `vesryn.invocation.invoke_tool` 需自行把保存的 Binding 转发至此参数。
   本仓不为 Vesryn 另建 MCP / 执行器或 `binding` 默认值。
2. **Vesryn Workflow → ToolRuntime.dispatch**：本仓 `dispatch` 接受
   `bindings: Mapping[step_id, Binding] | None`；Vesryn DAG/FSM 层需在
   `dispatch` 调用前把每个 `step_id` 的冻结 Binding 汇集到此映射。无 Binding
   的步骤维持现有直接调用，不引入默认 `Binding` 数据库。
3. **engineering-ci 检查 Provider**：工程侧的 Schema 1 Binding 已由其
   既有 `create_binding` 路径生成并持有 `provider`；冻结后调用本仓
   `verify_binding` 进行二次校验，Provider 身份必须等于 `catalog.provider_for`。
4. **Scope 字段对齐**：消费者需保证冻结 Binding 的 `scope.{repository,
   environment, permissions}` 与运行时的 `DiscoveryScope` 相容；本仓在
   `verify_binding` 与 dispatch 时均独立校验，运行时不再推断或放宽。
5. **执行身份绑定**：若 Binding 中 `execution_id` 非空，消费者调用本仓
   `dispatch` / `invoke` 时必须传入 `ExecutionContext.execution_id` 与之
   相等；不等直接拒绝并记录 `admission_errors`。
6. **写工具手动恢复**：对 `effect == "write"` 且 `recovery == "manual"`
   的工具，调用方需自带恢复决策；本仓对带 `previous` 的直接调用返回
   `admission_errors`，不提供自动重启。
7. **观测隔离**：消费者不必重写 `EventSink`；只需把
   `vesryn_log.JsonlSink(authorized_path)` 透传给 `invoke_tool(...)` 或
   `ToolRuntime(..., event_sink=...)`。`observation_errors` 已与工具结果
   隔离，不影响 `results` / `execution_facts`。

## 兼容核对结论

现有 Binding、准入与 Admission 公共 API 已满足 Schema 1 复用、Provider /
hash / 参数 / scope 校验、原失败保留与观测分离的全部要求。本任务按"没有
缺口时交付兼容结论"原则完成，**未对本仓源码做任何改动**。

下游需在本仓以外完成自身适配：

- Vesryn 的 `invoke_tool` 上层透传 `binding`（消费者任务
  [VES-003](https://github.com/dymzz/vesryn/issues/6)）。
- engineering-ci 在共享 Provider 与自有 Binding 之间复用现有
  `verify_binding` 路径，不在本仓另造接口。
- 双方在本核对结论生效前先确认实际安装/源码身份（`vesryn-log` 0.1.x
  系列与 `vesryn-tool-runtime` 0.1.0 wheel），再走各自的接入验收。

## 已运行的复现证据

下列复现在已安装的 `vesryn_tool_runtime==0.1.0` wheel 与 Vesryn 工作树
（`runtime-env` 内置 `vesryn`）之上运行；脚本位于
`.test-tools/tr001_reproduction.py` 与 `.test-tools/tr001_consumer_repro.py`，
均以 `python -I` 启动以排除用户脚本目录干扰。

### 1. Tool-runtime 公共 API 已具备 binding 透传

实际探测签名（与 `docs/python-api.md` 一致）：

```
invoke_tool(tool_id, inputs=None, *, catalog, scope, context=None, binding=None, event_sink=None)
ToolRuntime.invoke(self, call, context=None, *, binding=None)
ToolRuntime.dispatch(self, calls, context=None, *, bindings=None, batch_id=None)
verify_binding(binding, catalog, *, current_scope=None)
create_binding(catalog, tool_id, *, provider, parameters=None, scope=None)
```

端到端跑通（创建 → `verify_binding` → `invoke_tool(..., binding=...)`）：

```
binding_id: 088bdeee25d6c31b...
outputs: {'value': 4}
adapter_batches: 1
```

### 2. Vesryn 消费者 Runtime 已转发 bindings

```
Runtime.__init__(self, catalog, *, scope=None, event_sink=None, bindings=None)
```

`Runtime._execute` 已把 `self.bindings[step_id]` 组装成
`bindings={step_id: self.bindings[step_id] ...}` 传入 `ToolRuntime.dispatch`。
复现测试 `test_runtime_batch_dispatch_forwards_bindings` 走完
`generate → runtime.create → runtime.resume`，断言
`state["status"] == "passed"` 且 Adapter 收到了与 binding parameters 一致的
inputs。

### 3. Vesryn `invoke_tool` 已接受 binding 透传

```
vesryn.invoke_tool(
    tool_id, inputs=None, *, root, purpose, catalog=None, out=None, prefer=None,
    allow_host_fallback=False, scope=None, providers=(), dagger_module=None,
    vesryn_source=None, tool_runtime_source=None, github_repository=None,
    binding=None, require_binding=False,
)
```

具体行为（源码核对 `src/vesryn/invocation.py`）：

1. `binding is not None` 且 `allow_host_fallback` 为真时强制 `allow_host_fallback=False`
   —— Binding 钉死 Provider/backend，自动 fallback 会改写 Provider，被 binding 拒绝。
2. 调用 `_enforce_selection_binding(binding, ...)`，其内部走
   `verify_binding(binding, catalog, current_scope=...)` 并额外校验
   `binding["tool_id"] == tool_id` 与 canonical(parameters) 相等；任何不匹配
   在 Adapter 收到任何工作前抛 `WorkflowError`。
3. `Runtime(catalog, bindings=None if binding is None else {"call": binding})`
   把 binding 透传给已验证的 `ToolRuntime.dispatch` 路径。
4. `_stamp_selection_binding(binding, execution_id=directory.name)` 把
   `execution_id` 写入并通过 `SELECTION_BINDING` Schema 校验后落盘
   `<execution>/selection-binding.json`；任何落盘失败都是预分派失败，
   不会进入 Adapter。

复现测试 `test_vesryn_invoke_tool_forwards_binding` 与
`test_vesryn_invoke_tool_rejects_mismatched_binding` 验证：

- `selection-binding.json` 已写入且 `binding_id` 与调用方传入的 binding 一致。
- `result.outputs` 与 binding parameters 加一后一致。
- 当 `inputs` 与 `binding.parameters` 不匹配时抛 `WorkflowError` 且 Adapter
  未被调用。

### 复现结果汇总

```
tests/ — 41 passed（含独立 test_real_log_sink_preserves_failure_and_excludes_private_payloads）
examples/direct_tool.py — passed/0
.test-tools/tr001_consumer_repro.py — 3 passed
  test_runtime_batch_dispatch_forwards_bindings PASSED
  test_vesryn_invoke_tool_forwards_binding PASSED
  test_vesryn_invoke_tool_rejects_mismatched_binding PASSED
```

## 结论重述

TR-001 范围内的 Binding / 准入 / Admission 公共契约兼容性核对完成：

- 本仓 `invoke_tool`、`ToolRuntime.invoke`、`ToolRuntime.dispatch`、
  `verify_binding`、`create_binding` 已支持 binding 透传（单次与批量两路）。
- Vesryn `Runtime` 与 `invoke_tool` 已独立实现 binding 透传、预分派
  校验、执行 ID 盖章与 `selection-binding.json` 落盘；VES-003 缺口在
  Vesryn 当前 head 已闭合。
- engineering-ci 通过既有 `verify_binding` 路径完成 Binding 校验，本仓
  无须另造接口。

**本任务对本仓源码零改动**，交付兼容核对结论与可重跑复现脚本。

## 边界

- 本核对不构成正式发布授权；`docs/delivery/release-readiness.md` 的
  C1–C8 与 C6 的不可变引用 / 交付审计仍按既有路径处理。
- 本核对不读取或写入消费者仓库；任何跨仓修改须按各自任务的明示授权执行。
- 本核对不修改现有 `pyproject.toml` / `uv.lock` / `uv_sources` 中的
  vesryn-log pin；依赖范围扩展由独立任务单独交付，不与本核对结论合并。