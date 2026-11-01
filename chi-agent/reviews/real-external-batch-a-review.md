# 真实批次 A 执行记录：B 成功、provider C 超时未结算

更新：2026-11-01。**本次触发未知用量停止；payer/CM/Y 均未运行，禁止自动重试。** 状态/权限见 [REVIEW_STATE](REVIEW_STATE.md)。

## 1. 身份与范围

| 项目 | 值 |
| --- | --- |
| 源码 | `81a3b15`（bundle 修复） + external operator 合并 |
| release | `runs/z6-clean-repro/release-v2` |
| bundle SHA | `ee004c97770b9532f5e373d5daa43b7da39326ce4c12a579f24a49d98b618c59` |
| runtime identity | `e41ae14232e5a832676fbfbe29b1d751568ddf391d2d19ebeb29e2a225cfe056` |
| history | external，`runs/real-external/state-v2` |
| 用户批准 | 1 B + 7 C；external；清单内新 attempt；不自动重发原请求 |

执行前发现并修复：release 首次漏打包 `go_chi_context/guidance/search/state`，B 在 import 阶段失败（旧状态 `state` 保留为失败证据）；bundle 清单和 preflight 导入检查修复后重建 `release-v2`。首次 B 失败不计成功，原失败保留。

## 2. coding-B

| 项目 | 值 |
| --- | --- |
| run | `real-ext-b-002` |
| 状态 | `complete` |
| 请求 | 3 |
| tokens | 1406 input / 123 output |
| 费用 | charged 0 / list 0.00017180 / allowance 0.00010308 USD，完整 |
| official_reward | null |

B 收据已写入 `state-v2`；这是真实 Go 调用，不是合成。

## 3. provider C（t032）

| 项目 | 值 |
| --- | --- |
| task | `pa_t032_t032_o002_p01_new_referral_provider` |
| run | `real-ext-provider-001` |
| 结果 | `failed`，`chi_timeout` |
| 请求/工具 | 17 requests，84 tool events |
| 已结算 tokens | 3,147,059 input / 33,754 output（16 次请求） |
| 未结算 | round 17 `pending`，request SHA `3395ab…`，无 response evidence |
| operator | runner_exit_code=1；world_quiescence=confirmed；runner/world/network 均 removed；capture_error=null |
| 业务检查 | 部分通过：case_created/procedure_code/diagnosis/service_type/site_of_service/forward_transitions=true；case_status、final_action、provider_determination、closed_backed=false；required_documents=not_applicable |
| official_reward | null |

失败发生在 16 次大上下文请求之后（第 15/16 次已约 345k/365k input tokens）；第 17 次等待响应超时。仅证明调用方没有及时取得结果，**不能证明服务端未处理**。

## 3.1 round 17 的提供方记录（2026-11-01 补核）

用户提供的 OpenCode Console 日志已精确对上 round 17：

- request ID：`01a196e9-2bf4-7c19-a984-fba43d6b9b21`
- 时间：19:40:25.972–19:41:33.700（本地），duration 67,728 ms
- 状态：HTTP 200 / succeeded
- input 369,422 / output 8,192 / reasoning 8,192 / cache 0；cost 0.0603285 USD
- content-length 1,274,867，等于 journal dispatch 的 body_bytes
- session `chi-22a92…` 的 SHA-256 等于 dispatch session_sha256 `7bc5b6…`

因此：**服务端实际执行并返回了 200，客户端的 60 秒读超时先发生**。本地 `pending` 是客户端未收全结果的账目状态，不是“服务端未知”。但本报告不自行把 pending 改成 settled；需要受审的结算/处置路径。

## 4. 为什么停止

`chi-accounting.json` 的 `pending` 指向 provider round 17，usage/response 未知。按现行规则：

- 同一真实账/账户的后续 B/C 准入停止；
- 不自动重发、不换模型、不换账根、不删除 pending；
- payer/CM/Y 批次未启动；
- 需要提供方 Console 单请求记录或用户明确处置后，才能评估下一步。

这不是业务失败结论，也不是“服务端未执行”的证明；只是未知。

## 5. 已知观察

- 大上下文请求（30 万+ input tokens）在 60 秒读超时下发生超时；F4 的字符预算未能避免服务端长响应/慢响应。不能因此直接改超时并重试；需要独立分析/候选和复审。
- provider 的 case 已创建且部分字段通过，但 case_status/final_action 未完成；不能把部分检查当业务成功。
- operator 清理与 world quiescence 已确认；这是清理证据，不是任务成功。

## 6. 下一步（未执行）

1. 提供方记录已证明 round 17 服务端 200、usage/cost 已知；但本地 `pending` 仍未结算。
2. 选项 A：新增**受审的 external pending 结算工具**，严格校验 session/body/request ID，保留原账原字节并追加事件；经 Gemini 复审后结算，再评估 payer/CM/Y 新 attempt。
3. 选项 B：不结算，批次 A 记为未完成，保持 pending，停止真实 C，转 Z8 材料/离线工作。
4. 无论哪项，都不能直接编辑 `chi-accounting.json`、重发 round 17 或换账根。
5. 超时本身暴露 F4/timeout 策略问题：369k input + 8192 output 花了 67.7s，超过 60s read；需独立候选/复审，不自动重试。

## 7. 正式对账与 payer 尝试（2026-11-01）

正式 `state-v2` 已按复审通过的 `reconcile_provider_timeout` 执行一次：

- 结果：`reconciled_provider_timeout`，`execution_allowed=false`、`request_retry_allowed=false`、`admission_cleared=true`、`settled=false`
- provider request ID `01a196e9…`，tokens 369422/8192，console cost 0.0603285
- `state.pending=null`；原 request 仍 pending，attempt 仍 failed，run seal 字节不变
- event SHA `e96cbb2584c88d01f4811d006cc42479e26317a0afb09415dc19cf50f16f525a`
- 对账后 accounting SHA `b9bdf98e92e8e19861cdb74a2bc5bf47e18974be4649cb0d39dba27732b89922`
- 备份：`runs/real-external/state-v2-pre-reconcile-backup-20261101`

随后尝试 payer t011 `real-ext-payer-001`，**在发请求前失败**：

- runner 日志：`{"status":"blocked","safe_error_code":"chi_history_invalid"}`
- 原因：release-v2 包内 `go_chi_journal.py` 早于 reconciliation schema，不识别 `reconciliations` 字段
- 无 provider 请求、无 journal attempt、无 token/费用
- operator：runner/world/network 已移除、client closed；`world_quiescence=unproven`、`capture_error=world_quiescence_unproven`、无 final capture
- 原 `payer-001` 输出保留，不覆盖

因此 payer/CM/Y 不能继续用旧 release-v2；需要新 release（含 reconciliation 源码）+ 新 coding-B + 新 external state（state-v3），并保留旧 state/失败证据。

## 8. release-v3 新 B、payer 002 与 CM 002（2026-11-01）

release-v3：bundle `6f6e71d8…`、identity `b936b7…`、state-v3。

### B3

- `real-ext-b-003` complete：3 请求，1399 input / 133 output，费用完整；`official_reward=null`。

### payer 002

- `real-ext-payer-002`：`failed`，`chi_tool_batch_invalid`。
- 18 请求、68 工具事件；请求全部 settled，**无 pending**。
- 清理确认（runner/world/network removed，world_quiescence confirmed）。
- 确定性检查：intake/nurse 多为 true；md/outcome/letter 多项 false/NA；业务未完成。
- 已知工具批次/协议失败，不是未知用量；不自动重试。

### CM 002

- `real-ext-cm-002`：`failed`，`chi_timeout`。
- 8 请求、36 工具事件；7 次 settled（约 62k/64k input 的最后两次），round 8 pending/usage unknown。
- 清理确认；确定性检查多为 false/NA，业务未完成。
- 这再次触发同账准入停止；Y 未运行。

### 当前停止点

`state-v3.pending = {run: real-ext-cm-002, round: 8}`。需要 CM round8 的 Console 记录（若显示 200）才能评估对账；否则批次 A 按未完成收口。不能自动重试或换账根。

## 9. CM round8 对账与 payer 失败定位（2026-11-01 补）

- CM round8 Console 精确匹配：request `01a19734-9e29-7610-a59e-a52bb1ff8ba2`，HTTP200，105,771 input / 4,623 output，cost 0.01863945，90.8s，body 394,869/session SHA 与 dispatch 一致。
- 已对正式 `state-v3` 执行同款对账：`execution_allowed=false`、`admission_cleared=true`、`settled=false`；event `5be3fa04…`，对账后 accounting SHA `c384e379…`；seal 不变、原 request 仍 pending；备份 `state-v3-pre-cm-reconcile-backup-20261101`。
- payer 002 最后响应是合法 JSON，但工具调用为 `determination__get_summary({case_id: CASE-6B9F238D})`；该工具在 intake 阶段没有被当前角色工具面接受，guard 返回 `chi_tool_batch_invalid`，整个 run 终止。不是用量未知，也不是网络失败。模型在 nurse 建议后直接跳到 determination，未先按阶段路由/终态路径推进。
- payer 失败无 pending、全部请求 settled；CM 失败已对账；state-v3 pending=null。Y 未运行。

## 10. 现状总结与下一步（2026-11-01）

批次 A 与 Y 的实际状态：

| run | 任务 | 状态 | 请求 | 用量 | pending |
| --- | --- | --- | --- | --- | --- |
| `real-ext-b-002` | coding-B（release-v2） | complete | 3 | 1406/123 | 无 |
| `real-ext-provider-001` | provider t032 | failed `chi_timeout` | 17 | 3,147,059/33,754 | 已对账（round17） |
| `real-ext-payer-001` | payer t011 | blocked `chi_history_invalid` | 0 | 0 | 无 |
| `real-ext-b-003` | coding-B（release-v3） | complete | 3 | 1399/133 | 无 |
| `real-ext-payer-002` | payer t011 | failed `chi_tool_batch_invalid` | 18 | 2,304,350/11,329 | 无 |
| `real-ext-cm-002` | CM afib | failed `chi_timeout` | 8 | 343,056/3,068 | 已对账（round8） |
| Y 4C | — | 未运行 | 0 | 0 | — |

两个工程问题：

1. **60s 客户端读超时短于长上下文生成时间**。provider round17 服务端 67.7s、CM round8 90.8s，均 HTTP200 后客户端已放弃。已完成受审对账，但真正修复需评估更长读超时或上下文预算策略；不能只改超时后原样重跑（新候选 + 新 attempt）。
2. **payer 阶段工具面过大/错误不可恢复**。模型在 intake/nurse 后直接调用 `determination__get_summary`，guard 判 `chi_tool_batch_invalid` 并 fatal，整个运行终止。需要的是按阶段暴露工具或把“当前阶段不可用”返回为可恢复的工具错误，让模型改道，而不是放宽校验。

下一步（离线）：

- 复现 payer 002 的工具序列，确认 `determination__get_summary` 在 intake 阶段为何出现在可用工具列表里（ListTools 快照/阶段白名单）。
- 设计候选：阶段性工具过滤 + 可恢复 `tool_not_available` 错误语义；读超时改为配置项并做合成慢响应测试。
- 两处均先离线测试、复审，再决定是否值得新 release + 新 B + 新 attempt；Y 还需第二个 payer 任务公开资源。
- 不重试 provider/payer/CM，不换账根，不伪造 settled。

## 11. release-v4：修复后重跑 payer / CM（2026-11-01）

候选 `db7d402`（`index` 兼容 + 主读窗口 240/300 + profile 同步）经外部 Gemini 两轮复审通过，与真实证据分支合并为 `41b8edf`，构建 release-v4：

- bundle `55d7393d7900a2bd2d5b3eea95bf2c0708ce2da5c2df70bf0942a044e2c0ab84`
- identity `f7d11712eb9de79e2ddaec9513e4338bba9d1a32f0335b1f45fa41bfe523fb26`
- 无 Key 禁网 preflight：`identity_verified`，upstream clean
- state 根 `runs/real-external/state-v4`（新身份，不复用 v2/v3）

### B4

`real-ext-b-004` complete：3 请求，1,378 入 / 118 出，费用完整（清单 $0.0001646，allowance $0.00009876，charged 0）。

### payer 003

`real-ext-payer-003` **complete**，无 safe_error_code：

- 37 请求、138 工具事件、579s；7,474,812 入 / 46,618 出；请求全部 settled，`pending=null`
- 清理确认（world_quiescence confirmed），runner 退出码 0
- 确定性检查：`md.audit`、`md.decision_exists`、`outcome.letter_types`、`outcome.target_status` 为 false —— **与 W 批次完全相同的一组**，说明这是稳定的业务终态差距，不是本次修复引入
- F5 回读状态：`completion.verification=blocked`、`reason=completion_readback_required:<call>`，即最后一次写后没有回读

### CM 003

`real-ext-cm-003` **complete**，不再超时：

- 23 次主请求 + 6 次患者模拟 = 29 条请求；2,333,183 入 / 26,024 出；359s；72 工具事件
- 清理确认，`pending=null`
- 业务结局：患者在电话中**没有给出入组同意**（要求先看书面材料、约周二回电），Agent 依据 CM-OUTREACH-001 §3.3/§3.4 拒绝开始 assessment，如实结束在 `outreach_complete`。因此 `cm.assessment.record_exists`、`cm.care_plan.record_exists`、`cm.cross_stage.audit_actions`、`cm.cross_stage.target_status` 为 false 是**预期路径**，不是工程失败
- 同时暴露一个真实可用性缺陷：`local-fs-write` 三次被拒。两次是模型把目录写成 `<case>/care-manager/...`（允许的是 `<case>/cm|payer|provider|shared>/...`，工具描述没有写明），一次是 `<case>/shared/...` 因父目录不存在返回 `workspace parent unavailable`（工具不建目录）。结果是 Agent 承诺的书面材料没能落盘

### 判断

- 两个修复达到目的：`index` 字段不再杀运行；105k/370k 上下文的长生成不再因 60s 读超时中断
- payer 的业务终态差距与 W 一致，需要单独分析（不是本次改动造成）；CM 的 false 检查来自合规的“未同意即不评估”路径
- 新发现的工作区写路径问题属于 F2/F1 接线缺口，应在下一候选修复（写明 `<case>/<role>` 约定 + 允许写时创建父目录），再决定是否值得新 release 重跑

## 12. release-v5：工作区写路径修复后重跑 CM（2026-11-01）

候选 `780d097`（工作区写入约定 + 父目录创建）复审通过后构建 release-v5：

- bundle `7a4582c485d0211bcdb0507fdbff526a1fb86ea27a87c3a7c545842acaabf8d9`
- identity `c8cba7215bcd9a0f0345e522be2e6b418ecf9c9bbf58bc85f0a58759ea55e632`
- state 根 `runs/real-external/state-v5`；无 Key preflight `identity_verified`

### B5

`real-ext-b-005` complete：3 请求，1,399 入 / 114 出，费用完整。

### CM 004

`real-ext-cm-004` **complete**：

- 37 次主请求 + 10 次患者模拟；5,465,882 入 / 约 5.2 万出（患者模拟 47,325/5,232）；602s；110 工具事件
- `local-fs-write` **0 次拒绝**（对比 CM 003 的 3 次），说明路径约定和父目录创建生效
- 业务路径：患者本次给出同意 → 四段评估 → care plan `CP-692179FC` finalize → case 终态 closed
- 确定性检查：**14 项 true、0 项 false**（CM 003 的 4 项 false 全部消除）
- 仍余 `local-state-update` 拒绝 2 次、`local-claim_done` 拒绝 2 次（不影响终态，但说明状态层还有可用性问题）
- 全部请求 settled、`pending=null`、清理确认、退出码 0

### 发现的证据缺陷（已修，未重跑）

`go_chi_guidance.digest()` 只哈希 `_INVARIANTS`，而 `guidance()` 实际返回 `_INVARIANTS[role] + [_WORKSPACE_INVARIANT]`。因此 CM 004 记录的 `guidance_sha256=eca20d…` 没有覆盖新增的工作区约定行；文件字节本身已进入 bundle identity，但日志摘要少算了一条。

修复：`delivered_invariants()` 作为唯一来源，`guidance()` 与 `digest()` 共用；新 digest `db66857e…`；新增测试断言 digest 覆盖该行。

不重跑 CM 004 的理由：行为未变，仅摘要覆盖面修正；重跑只会重复同一业务路径并消耗额度。CM 004 的证据保留，并以本段说明其 `guidance_sha256` 的已知含义。
