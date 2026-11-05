# 最终候选冻结与准入准备任务清单（草案）

当前状态：PR60/61/62 已合并（最新 main `dd438e9…`）；九题公开资源已冻结；新B `final-b-001` 已成功；用户批准九题开发C后，首题 `final-c-provider-t015` round4 `chi_timeout` pending，按停止条件中止，其余8题未运行。候选/审批/预登记见[proposal](proposal.md)，详细证据见[准入报告](../../../reviews/final-validation-admission-review.md)、[执行报告](../../../reviews/final-validation-execution-review.md)及[九题执行记录](../../../reviews/final-validation-nine-task-execution-20261106.json)。

## 0. 本轮已完成

- [x] PR60 已合并 `856e2f2…`；从最新 `origin/main` 新建 `deepseek/final-validation-execution`，未向已合并分支追加。
- [x] 按冻结 revision 获取九题公开资源、生成 9 份 role manifest 并通过资源 preflight；真实 world/MCP/模型仍未启动。
- [x] 从最新 `origin/main=ec1a706…` 建 `deepseek/final-validation-admission`；核对工作区、其他 worktree 和单写入者。
- [x] 比较已审包内实现 `36db613…` 与当前树：42 个 `PACKAGE_FILES` 成员逐字节不变；新增包外 `go_chi_readiness_inventory.py`/测试单列。
- [x] 从当前树重建 Go/release/evaluation；记录 manifest/runtime/release/source_commit。
- [x] 隔离导出包无 Key 禁网 preflight；实际 `identity_verified`、runtime 匹配、upstream clean。
- [x] 固定摘要/恢复/Y off、模型/端点/high、依赖/镜像/资源供应和共享/辅助限额。
- [x] 生成机器候选清单、B 计划草案、G0 决策模板、九题预登记、污染/资源矩阵和审批草案。
- [x] 核对 t022 公开 5 个 request PDF 与开发准入链原固定 4 个的缺口；`make_role_manifest`、`role_resource_preflight`、`role_operator._payer_projection` 三处统一为 1–20 有界计数，4/5 完整链正例及缺/多/重复/scope/symlink/hash 负例通过（manifest/preflight 24 passed；投影 14 OK；连同既有 controller 15 项为 29 OK）。
- [x] 只读核对旧 S 账、payer-010 unknown/pending 和 state-abl-on2；未 rebind/迁移/核销/清 pending。
- [x] 更新阶段报告和 REVIEW_STATE 短状态；未覆盖旧候选/旧审批/旧导出。

## 1. 需用户另行决定/授权

- [x] G0：用户 2026-11-06 明确选择保留 payer-010 旧 unknown/不完整费用，不修改旧 pending、不认定零发送或已结算，仅授权隔离新 B；旧 unknown 不结算。
- [x] 新 B：用户 2026-11-06 明确批准后执行 `final-b-001`；3 个 main HTTP 全 settled、receipt/seal 有效、pending/halt null；记录见 `reviews/final-validation-b-execution-20261106.json`。
- [x] 九题资源：按冻结 revision `5ce88104…` 获取 59 个公开文件并生成/通过 9 份 role manifest；t022 保留 5 份 request PDF、t023/t024 各 4 份。冻结结果 SHA `074fd38e…`；未解析 expectations 内容。
- [x] 九题执行启动：用户 2026-11-06 批准后执行首题 `final-c-provider-t015`；4 个 main（3 settled + round4 pending），240.022s `chi_timeout`，按停止条件中止；其余 8 题未运行。记录见 `reviews/final-validation-nine-task-execution-20261106.json`。
- [ ] 九题剩余 8 题：需先处置 t015 round4 pending/unknown 或取得可信结算证据；未解除前不重跑、不追加同 state 运行、不换题。
- [ ] 正式 Harbor/官方患者/judge/发布：各自供应和授权，不由本清单勾选自动恢复。

## 2. 明确不随本轮启动

- [ ] 摘要/恢复真实探针、摘要接续、方案 B 选区上限、Y 实验。
- [ ] 额外已见题 C、九题后的 7 次机动或候选替换。
- [ ] 新清单硬门禁、加额度、全面重构、发布或官方评分。
