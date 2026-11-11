# Target 绑定修复（2026-11-09）

范围：修复正常 16384 基线 `ce-c-baseline-001` 暴露的 target 绑定错误。**只做离线代码/测试与文档；未跑真实 C、judge/Trial/发布；`official_reward=null`。**

## 1. 现象

`ce-c-baseline-001`（t023 payer，正常 16384）50 main 全部 settled、无 recovery、无 pending，但 `chi_runner_failed`，未 claim。

- task-state `target = CASE-E33A4F82`（68 岁同名患者）；
- 任务实际是 `CASE-7D075BE2`（52 岁，1973-11-08）；
- 模型最后业务状态已把 `CASE-7D075BE2` finalize，但 target 未改，状态源仍引用了错误 case 的 `triage.get`。

根因：`TaskState._bind_target_from_observation` 对任意 `case:` scope 的首个观察绑定 target，包括 MCP `payer_intake_hub.get_intake_case`。同名队列里先读到哪个 case，target 就绑到哪个。

## 2. 修复

| 项 | 处理 |
| --- | --- |
| target 绑定 | 只接受 `kind == "local"` 且 `scope == case:<case>` 的 workspace 观察；任意 MCP case 读取不再绑定。若模型从未读本地 workspace，target 保持 `null`，由既有门禁要求先确认，而不是猜第一个 |
| 跨 case mutation | target 已绑定后，mutation 的 `case_id`（MCP）或 workspace path case（`local-fs-write`/`local-fs-edit`）与 target 不同 → `HARD:target_mismatch`，dispatch 停止 |
| path case 推导 | 新增 `_mutation_case_id`：MCP 用 `case_id`；本地文件按 `<root>/<case>/<role\|shared>/...` 推导，兼容嵌套子目录；`unread_write` 复用同一推导 |
| 错误状态源 | 既有 `_check_source_scope` 继续拒绝引用非 target case 的 `latest_business_status` |

t023 证据中 seq 20 已 `local-fs-list` 到 `case:CASE-7D075BE2`。修复后 target 会在该处绑定为正确 case；seq 97 的错误 case `triage.get` 不能再被用作状态源。

## 3. 代码触点

- `scripts/go_chi_state.py`：`_mutation_case_id`、`_bind_target_from_observation`、`drift_check`。
- `tests/test_go_chi_state.py`：新增 `TargetBindingTests`（MCP 不绑定、workspace 绑定、先读错再读对、无 workspace 保持 null）。
- `tests/test_drift.py`：新增 MCP/local target mismatch 硬拒绝与匹配放行。
- `tests/test_completion_gate.py`、`tests/test_intent_anchor.py`：改用 local workspace 观察建立 target。

## 4. 测试

- 全量 `unittest discover`：**768 tests / 23 skipped / 3 个既有 import error**。
- 定向 `test_go_chi_state` + `test_drift`：**45 passed**。
- `test_completion_gate` + `test_intent_anchor`：**11 passed**。
- recovery pytest：**48 passed**。
- C-002 旧 state 用新代码 `inspect_history`：**inspected**。

3 个既有 import error 不变：`test_dev_patient_adapter`、`test_dev_patient_network`（缺 `anthropic`）、`test_role_payer_projection`（缺 `docker.types`）。

## 5. 身份与后续

- 本改动改变 bundle/runtime 身份；
- 现有 bundle `bc0d8270…` / identity `30ceaddc…`、B `ce-b-003` 和 `ce-c-baseline-001` 都对应**修复前**代码；
- 修复后真实运行必须重建 bundle + 新 B，不能复用 `ce-b-003`；
- 旧 pending（C-002 round 8、t022/t024 429/timeout）保留，不重试、不清。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 未对错误 case 的只读访问加 soft drift；当前只对 mutation 硬拒绝，状态引用由 `_check_source_scope` 拒绝。
- 待独立复审与用户合并；不 auto-merge。
