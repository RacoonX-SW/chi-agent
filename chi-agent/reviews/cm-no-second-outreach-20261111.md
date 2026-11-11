# CM 不重开 outreach session（2026-11-11）

范围：asthma rerun-007 在 session_id 修复后撞到 auxiliary 请求上限；根因是模型在 session 结束后重开 outreach。**只做离线代码/测试与文档；真实 asthma 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-cm-asthma-rerun-007`：

- 29 main + 10 patient_simulator；
- schema 拒绝 **0**，`session_id` 问题已消失；
- 第一次 outreach `SES-D40ADE0C` 到 turn 20 自动 `ended`；
- 模型读取 transcript（`status: "ended"`）后，又调用了一次 `cm_outreach.start_outreach_call`，得到新会话 `SES-D56A7B5E`；
- 新会话的 `send_message` 成为第 11 次 patient_simulator 请求，触发 `chi_aux_request_limit`；
- target 正确，drift/recovery/pending 0，cleanup confirmed，未 claim。

## 2. 修复

CM invariants 增加通用规则：

> Do not start a second outreach session for the same case. After a session ends, read the transcript and record the outcome with end_outreach_call; if consent or enrollment was obtained, continue to assessment and care plan, otherwise take the terminal or blocked path.

含义：

- 同一 case 只保留一次 outreach attempt；
- session 结束后用 transcript 和 `end_outreach_call` 记录 outcome；
- consent 已获得 → 继续 assessment/care plan；
- decline/STOP/联系不上 → 记录 terminal 或 blocked 路径；
- 不用第二次 `start_outreach_call` 延续第一次对话。

## 3. 测试

- 新增 CM guidance 断言：不重开 outreach、读 transcript、使用 `end_outreach_call`；
- 全量 `dev_verify.sh --allow-dirty`：**796 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`f346cca627b5efddd18200f4977fa79ed21863eec3c3d8c3d52f29c44a53adc6`；
- 新 identity：`1715a86062a23f6ab2ff639ebfd02417394e31475428ce8287263e37e123dbd2`；
- preflight：`identity_verified`。

## 4. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-012`/bundle `d0258448…`/asthma rerun-007 对应修复前代码；
- 合并后需重建 bundle + 新 B，再手动重跑 asthma；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 未提高 auxiliary 请求上限；10 次对应 20-turn session，重开才是根因。
