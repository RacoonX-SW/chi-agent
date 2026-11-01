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
