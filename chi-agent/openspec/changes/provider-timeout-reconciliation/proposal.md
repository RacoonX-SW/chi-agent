# Provider 超时与 Console 记录对账

建立：2026-11-01。真实批次 A 的 round 17 在客户端 60 秒读超时，但 OpenCode Console 记录显示服务端 HTTP 200、369,422 input / 8,192 output、cost 0.0603285 USD、67.7 秒；journal 遗留 pending。

本变更只解决“如何在不伪造响应、不改写 failed seal、不重试请求的前提下解除该请求的准入阻断”。它不把请求改成 settled，不补三项 USD 账单，也不证明业务成功。

## 范围

- `go_chi_journal.reconcile_provider_timeout()`：严格校验 provider 单请求记录与 pending request，写 reconciliation 事件，清空 `state.pending`，保留原 request 为 pending/unknown 与原 run seal。
- 事件保存原 accounting/provider 副本与 event 的 SHA-256；`go_chi_journal._validate()` 识别 `reconciliations` 并拒绝篡改/目标不符。
- CLI `go_chi_entry.py reconcile-provider`（external、无 Key、无网络）。
- `go_chi_inspect.py` 允许真实 Console 的 `stream=false`、`firstTokenAt/timeToFirstTokenMs=null`，并返回 request/session 元数据。
- 合成测试 + 真实 round 17 **状态副本**试结算。

## 非范围

- 不把请求写成 settled；不伪造 response evidence；不补 charged/list/allowance 三项。
- 不重发 round 17、不自动重试、不换模型/账根。
- 不改原 failed attempt、seal、tool evidence 或官方分数。
- 不证明业务成功、临床正确性或官方评分。
