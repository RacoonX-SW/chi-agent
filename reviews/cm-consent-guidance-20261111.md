# CM consent 不是终态 guidance（2026-11-11）

范围：asthma 重跑暴露的“患者同意后停止”问题；增加通用 CM guidance。**只做离线代码/测试与文档；真实 asthma 重跑在合并后另行执行；`official_reward=null`。**

## 1. asthma 重跑结果

### `ce-c-cm-asthma-rerun-003`

- 通用 provenance hint 生效：拒绝信息包含 `session_id=SES-2FC2946B from cm_outreach__start_outreach_call (...)`；
- 模型仍第三次漏传 `session_id`，`chi_tool_batch_invalid`，未 claim；
- 17 main + 3 patient_simulator。

### `ce-c-cm-asthma-rerun-004`

- `attempt_id` 仍是 `attempt-1`，被 journal 的重复 attempt 检查拦住；
- `chi_attempt_or_run_exists`，未调用模型；
- 证据保留，不覆盖。

### `ce-c-cm-asthma-rerun-005`（attempt-2）

- 6 次 `cm_outreach.send_message` 全部 returned，**session_id 问题未再出现**；
- 患者在第 12 turn 明确同意 enroll；
- 模型之后只继续 `send_message`，没有 `end_outreach_call`、assessment、care plan 或 `local-claim_done`；
- 22 main + 6 patient_simulator，`chi_claim_required`，未 claim；
- target 正确，drift/recovery/pending 0，cleanup confirmed。

## 2. 修复

在 `_INVARIANTS["cm"]` 增加通用规则：

> Patient consent or enrollment is not a terminal state; unless the patient declines, STOPs or cannot be reached, continue to the assessment and care plan.

这不是 asthma 专用规则，适用于所有 CM 任务；它只说明阶段边界，不包含任务 ID、期望结局或隐藏答案。

## 3. 测试

- 新增 CM guidance 断言：consent/enrollment 不是终态，继续 assessment/care plan；
- 全量 `dev_verify.sh --allow-dirty`：**795 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`100a5001ddd26826d9685c40e15830d5e4dd2915f37eba0017d71a7097b4d946`；
- 新 identity：`e958747ef81bde294f8a34944ddef80eae590af32eaeb3ab4be928829964ddaf`；
- preflight：`identity_verified`。

## 4. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-010`/bundle `16a6c825…`/asthma rerun-003/005 对应修复前代码；
- 合并后需重建 bundle + 新 B，再手动重跑 asthma；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- guidance 只提示阶段边界，不保证模型一定继续；若仍失败，再考虑更强约束或接受。
