# 摘要生成预算修正执行清单

范围和验收见[proposal](proposal.md)；许可/当前候选见[REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。勾选不等于真实模型效果或官方验收。

- [x] 用户撤销PR57原E接续卡，PR57保留A–D；从最新main新建独立摘要预算分支。
- [x] 一个Terra/high子代理实现v2摘要32768，保留v1/其他用途及默认off，Docker离线自测；主代理补回原v1 SDK成功用例要求后，子代理追加并自测。
- [x] 主代理补齐包内runbook及旧摘要契约后继指针，明确候选JSON字节与生成token限制、正式harness暂不透传。
- [x] 固定最终候选，主代理按diff及实际接缝独立复验；新增失败或修改再复验相关范围。
- [x] 隔离构建Go/evaluation/release，真实identity/profile/preflight及新旧包差异核对，不mock核心校验。
- [x] 原v1/S只读严格校验与原hash集合保留，默认/用途上限/零额外请求/未知停止反例。
- [x] 单一[阶段报告](../../../reviews/summary-generation-budget-review.md)和REVIEW_STATE短状态、文档/暂存边界检查。
- [x] 提交/push/base=main [PR58](https://github.com/xsw932187210-cell/chi-agent/pull/58)，不merge/auto-merge。
- [ ] 用户最终合并；PR存在及合并状态以GitHub和REVIEW_STATE为准。

真实新B/摘要兼容/忠实度/费用收益/九题/Harbor/患者/judge/发布均未在本轮获准；不重跑原S、不迁移旧账或pending。
