# CM target 绑定与三题重跑（2026-11-10）

范围：修复 CM 任务 target 绑定过晚的问题，并记录 CM anorexia/asthma/ckd 重跑结果。**只做离线代码/测试与文档；CKD 真实重跑在合并后另行执行；`official_reward=null`。**

## 1. CM 三题结果

| 题 | run | 结果 | 说明 |
| --- | --- | --- | --- |
| anorexia | `ce-c-cm-anorexia-rerun-002` | **complete + claim** | 45 main + 10 patient_simulator，target 正确，inspect inspected |
| asthma | `ce-c-cm-asthma-rerun-002` | failed / `chi_tool_batch_invalid` | 模型连续 3 次 `cm_outreach.send_message` 漏传 `session_id`，达到 schema refusal 上限 |
| ckd | `ce-c-cm-ckd-rerun-002` | failed / `chi_runner_failed` | 50 main 用尽，未 claim |

### anorexia

- input 2,838,348 / output 53,216；list 0.44785981 / allowance 0.26871582 / charged 0；
- care plan `CP-9236C90E` finalized；
- cleanup confirmed；`inspect_history` inspected。

### asthma

- 23 main + 3 patient_simulator，全部 settled；
- `start_outreach_call` 返回 `session_id=SES-6046D5EC`，第一次 `send_message` 带上了；
- 后两次漏传 `session_id`，返回 `chi_tool_arguments_invalid`；
- 第三次再次漏传，达到 `RECOVERABLE_SCHEMA_LIMIT`，contract 按设计 fail-closed；
- **这是模型工具使用问题，不是代码 bug。**

### ckd

- 50 main + 10 patient_simulator，全部 settled；
- 业务已做到 `cm_care_plan.finalize`，但 `latest_business_status` 一直为 null；
- 两次 `local-state-update` 被 `chi_state_target_required` 拒绝；
- target 直到 seq 61 的本地 `local-fs-read` 才绑定，已无剩余 main 请求；
- 根因：CM 任务通常没有可读的本地 case 文件，模型靠 `cm_chart.get_chart_data` 识别 case，但该 MCP 读取此前不绑定 target。

## 2. 修复

`_bind_target_from_observation` 对 CM 增加一个 task-scoped 例外：

- 本地 `local` 成功 read（原有规则）；
- CM 的 `cm_chart.get_chart_data` 成功、case-scoped、returned read。

payer/provider 仍只从本地 workspace 成功 read 绑定；`payer_intake_hub.get_intake_case` 等队列读取仍不绑定。

## 3. 测试

- 新增：CM `cm_chart.get_chart_data` 绑定；
- 新增：CM 失败 chart read 不绑定；
- 新增：CM 其他 MCP case read 不绑定；
- 新增：payer `get_intake_case` 不绑定；
- 全量 `dev_verify.sh --allow-dirty`：**789 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`ec8b3307646dd66c80d7c611ad0e49d099989b08619c88e0e56bd4e34453d38e`；
- 新 identity：`431867bde6808eeb36fb2affb843f628fd13dd9b6f0fa15fd000bbfa8b92f8bd`；
- preflight：`identity_verified`。

## 4. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-008`/bundle `20b4dd75…`/CM 三题对应修复前代码；
- 合并后需重建 bundle + 新 B，再重跑 CKD；asthma 是否手动重跑由用户决定，不自动重试；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- asthma 的 `session_id` 漏传是模型行为，本次未加提示词/工具描述改动。
