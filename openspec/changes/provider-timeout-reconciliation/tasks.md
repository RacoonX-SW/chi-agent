# Provider timeout 对账执行清单

- [x] `reconcile_provider_timeout()`：严格 provider 记录/账本/请求校验。
- [x] `reconciliations/` 保存原 accounting/provider/event 副本与 hash。
- [x] `_validate()` 接受 reconciliation 事件，拒绝篡改/重复/目标不符。
- [x] request 保持 pending/unknown、attempt failed、seal 不变；只清 state.pending。
- [x] CLI `reconcile-provider`，external、无 Key、无网络。
- [x] `inspect_provider` 支持真实 Console 的 stream=false、firstToken null；返回 request/session。
- [x] 合成测试：正常、provider mismatch、seal/账不变、reopen。
- [x] 真实 round17 状态副本试结算成功；正式 state-v2 未改。
- [ ] 外部 Gemini 复审。
- [ ] 复审后对正式 state-v2 执行；保留副本/事件。
- [ ] 结算后再评估 payer/CM/Y；不自动重试 provider。

## 明确不做

- 不把 request 改成 settled、不补三项 USD、不伪造 response。
- 不重发原请求、不换 candidate/账根。
- 不证明业务成功/临床/官方分数。
