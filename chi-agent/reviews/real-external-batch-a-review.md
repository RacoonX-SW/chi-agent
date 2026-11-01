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

1. 用户提供 round 17 的 OpenCode Console 单请求导出（或明确不提供）；离线核对 request/usage，不重发。
2. 若可结算，评估是否解除该 unknown；若不可结算，保持停止并把批次 A 记为未完成。
3. 不启动 payer/CM/Y，直到 unknown 有明确处置。
4. 若要修超时/上下文策略，另开候选、离线测试、Gemini 复审，再申请新 attempt；不能把本次 timeout 自动当重试理由。
