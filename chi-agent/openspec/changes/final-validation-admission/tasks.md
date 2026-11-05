# 最终候选冻结与准入准备任务清单（草案）

当前状态：离线准备完成，真实执行未授权。候选/审批/预登记见[proposal](proposal.md)，详细证据见[阶段报告](../../../reviews/final-validation-admission-review.md)。

## 0. 本轮已完成

- [x] 从最新 `origin/main=ec1a706…` 建 `deepseek/final-validation-admission`；核对工作区、其他 worktree 和单写入者。
- [x] 比较已审包内实现 `36db613…` 与当前树：42 个 `PACKAGE_FILES` 成员逐字节不变；新增包外 `go_chi_readiness_inventory.py`/测试单列。
- [x] 从当前树重建 Go/release/evaluation；记录 manifest/runtime/release/source_commit。
- [x] 隔离导出包无 Key 禁网 preflight；实际 `identity_verified`、runtime 匹配、upstream clean。
- [x] 固定摘要/恢复/Y off、模型/端点/high、依赖/镜像/资源供应和共享/辅助限额。
- [x] 生成机器候选清单、B 计划草案、G0 决策模板、九题预登记、污染/资源矩阵和审批草案。
- [x] 只读核对旧 S 账、payer-010 unknown/pending 和 state-abl-on2；未 rebind/迁移/核销/清 pending。
- [x] 更新阶段报告和 REVIEW_STATE 短状态；未覆盖旧候选/旧审批/旧导出。

## 1. 需用户另行决定/授权

- [ ] G0：payer-010 round1 未知结果/token 的可信结算证据，或明确保留旧 unknown 并仅授权隔离新 B。
- [ ] 新 B：按 `coding-b-plan-20261105.json` 的候选/evaluation/state/run/6 HTTP 精确批准。
- [ ] 九题资源：获取并冻结 9 题公开 instruction/tool_reference/world/manifest；当前 0/9 本地存在。
- [ ] 九题执行：按预登记和分阶段审批草案另行批准；本轮未授权。
- [ ] 正式 Harbor/官方患者/judge/发布：各自供应和授权，不由本清单勾选自动恢复。

## 2. 明确不随本轮启动

- [ ] 摘要/恢复真实探针、摘要接续、方案 B 选区上限、Y 实验。
- [ ] 额外已见题 C、九题后的 7 次机动或候选替换。
- [ ] 新清单硬门禁、加额度、全面重构、发布或官方评分。
