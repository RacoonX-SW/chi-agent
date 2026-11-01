# Provider timeout 对账：实现与证据

更新：2026-11-01。基于 main `dac6080`；代码在 `codex/reconcile-provider-timeout`。**正式 `state-v2` 未修改**，pending 仍在。

## 1. 实现

- `go_chi_journal.reconcile_provider_timeout()`：
  - 只接受 external state 中 failed attempt 的 chi_timeout pending request；
  - 通过 `inspect_provider()` 校验 Console 200、session SHA、body bytes、时间、tokens、cost；
  - 在 `reconciliations/` 保存原 accounting/provider/event 三份副本与 SHA；
  - 清空 `state.pending`；request 仍 pending/unknown、attempt failed、run seal 原字节不变；
  - 事件 `chi-go-provider-reconciliation-v1` 记录 request ID/tokens/console cost/reason。
- `_validate()` 接受 `reconciliations`，校验事件/副本 hash、目标、请求 SHA；篡改/重复拒绝。
- CLI `go_chi_entry.py reconcile-provider`：external、无 Key、无网络。
- `inspect_provider` 支持真实 Console `stream=false`、`firstTokenAt/timeToFirstTokenMs=null`，返回 request/session 元数据。

## 2. 真实 round 17 副本试结算

正式状态：`runs/real-external/state-v2` 保持 pending。
副本：`runs/real-external/state-v2-test`（复制后执行）。

| 字段 | 值 |
| --- | --- |
| provider request | `01a196e9-2bf4-7c19-a984-fba43d6b9b21` |
| body bytes | 1,274,867（与 dispatch 一致） |
| session SHA | `7bc5b6…`（与 dispatch 一致） |
| tokens | 369,422 input / 8,192 output |
| console cost | 0.0603285 USD |
| 结果 | `reconciled_provider_timeout`，`settled=false` |
| state.pending | null |
| request status | 仍 `pending` |
| run seal | 字节不变 |
| reopen | `_validate()` 通过 |
| event SHA | `3798e5…` |

副本的 reconciliation 事件/accounting/provider 副本均在副本目录；正式 state 未改。

## 3. 测试

- 定向：`tests.test_go_chi_reconcile` 2 tests OK；`tests.test_go_chi_inspect` 通过。
- 全量：`Ran 468 tests`，2 个既有环境错误（缺 `anthropic`），8 skipped。
- 合成覆盖：正常对账、provider session mismatch 拒绝、账本不变、seal 不变、reopen。

## 4. 边界

- 工具不把请求写成 settled，不补 charged/list/allowance，不伪造 response evidence。
- `execution_allowed=true` 仅解除该 pending 对新 attempt 的准入阻断，不是原请求重试授权。
- 不自动重发、不换 candidate/账根；official_reward=null。
- 业务成功、临床正确性、官方分数仍未验证。

## 5. 下一步

1. 外部 Gemini 复审本工具（重点：仅清 pending 是否足够、seal 不变、billing incomplete、字段语义）。
2. 复审通过后对正式 `state-v2` 执行一次，保留事件副本。
3. 再评估 payer/CM/Y；provider 的 60s/8192 超时需要独立设计，不直接重试。
