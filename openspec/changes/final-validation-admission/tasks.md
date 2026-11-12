# 最终候选冻结与准入准备任务清单（草案）

当前状态：PR60/61/62/63/64 已合并；1800s 官方 2× 策略已实现并推送 [PR65](https://github.com/xsw932187210-cell/chi-agent/pull/65)（未 merge）；新 bundle `193c0a99…`、B-003/B-004 成功；429 state 原样保留；新隔离 state 的 1800b 尝试 20 settled+round21 pending `chi_transport_error`（699s，非时间上限），按停止条件中止；1800s 窗口仍未检验。旧 900s round4 pending 仍保留，其余 8 题未运行。候选/审批/预登记见[proposal](proposal.md)，详细证据见[准入报告](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/final-validation-admission-review.md)、[执行报告](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/final-validation-execution-review.md)、[1800s记录](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/agent-timeout-1800-20261106.md)及[九题执行记录](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/final-validation-nine-task-execution-20261106.json)。

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
- [x] 1800s 官方 2× 策略：依据 t015 task.toml 基础 900s、官方 `SubmissionRun.timeout_multiplier=2.0` 和实验配置 `agent_timeout_multiplier: 2`，将 `chi_admission_seconds` 调到 1800、role_runner 1900；代码/测试/profile/文档见 PR65 和 `reviews/agent-timeout-1800-20261106.md`。
- [x] 1800s 新身份与 B：重建 bundle `193c0a99…`、runtime `6858e5cc…`；新 state `retry-t015-1800/state`；B `final-b-003` 3 main settled、receipt/seal 匹配。
- [x] 1800s t015 尝试：`final-c-provider-t015-1800` 首请求 HTTP 429 `overloaded`，`chi_http_error`，`pending={round:1}`；无业务写、资源前后同 hash、清理确认。1800s 时间窗口未被检验。
- [x] 1800b 新 state + B：保留 429 state 不动，新建 `retry-t015-1800b/state`；B `final-b-004` 3 main settled、receipt/seal 匹配。
- [x] 1800b t015 尝试：`final-c-provider-t015-1800b` 20 settled+round21 pending，`chi_transport_error`（30.8s，无 response），699s；已建 case/大部分字段，差业务回读；非 1800s 上限；按停止条件中止。
- [ ] 1800b pending/重试：需等待提供方稳定，并决定新 state+B-005 或 429/transport acknowledgement；未解除前不自动重试。
- [ ] 429 pending 处置/重试：需等待提供方恢复，并决定确认 429 无 usage 后同 state `attempt-2`，或新建隔离 state + 新 B；未解除前不自动重试。
- [ ] 九题剩余 8 题：需先处置 t015 pending/unknown 或取得可信结算证据；未解除前不重跑、不追加同 state 运行、不换题。
- [ ] 正式 Harbor/官方患者/judge/发布：各自供应和授权，不由本清单勾选自动恢复。

## 2. 明确不随本轮启动

- [ ] 摘要/恢复真实探针、摘要接续、方案 B 选区上限、Y 实验。
- [ ] 额外已见题 C、九题后的 7 次机动或候选替换。
- [ ] 新清单硬门禁、加额度、全面重构、发布或官方评分。
