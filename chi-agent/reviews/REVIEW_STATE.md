# 审核接续状态

更新：2026-10-25。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | 按用户同意的建议精简协作约定；仅文档变更，不迁移环境或改实现。bootstrap-baseline/A 已独立验收并由用户合并；B/C、参赛模型 API 和官方判分仍暂停 |
| 协作 | 默认一个 Luna High 实现子代理、主代理独立审核；第二个按明确并行收益启用，纯文档由主代理完成。现行职责见 [协作约定](../../COLLABORATION.md#当前协作方式2026-10-25) |
| 上次独立审核候选 | `a173409416cf111ec2f2cc45247aa592b5ddd77e`，见 [A 独立审核](bootstrap-baseline-a-review.md)；离线与真实接入分层记录 |
| 上次通过的实现提交 | `a173409416cf111ec2f2cc45247aa592b5ddd77e`，仅 A 环境/无模型只读接入及受影响离线代码；D0 通过身份仍为 b7f8941，不能扩大为 Agent 任务或用户完整验收 |
| 存储与验收身份 | 实现验收身份保留上列 SHA；文档提交、PR 和合并提交不代替实现验收。Git 与上传流程见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | `codex/simplify-collaboration` 从最新 `origin/main` 的 `03fedf9` 建立，开工时工作区干净；保留全部历史学习记录与阶段报告，本轮 PR 见回复及附件 |
| 环境目标与实际 | 开发/调度目标对齐官方 Python 3.12；实际开发/调度镜像仍为 3.13，官方任务镜像为 3.12，尚未执行迁移。后续环境变更须更新镜像/依赖并验证 |
| 参赛预算 | 首轮 B/C 合计 5 元人民币的规划不变，写代码另计；当前未恢复付费运行 |
| 当前 A 离线证据 | 固定 git archive 快照；Python 3.13.17 与 3.12.15 / aarch64 各 115 项项目测试、19 subtests 和 6 项独立方法通过；A controller 20 项锁定依赖 uv pip check 通过，Compose 校验通过；离线检查无网络/无 socket/无真实凭据 |
| A 真实证据 | Python 3.12.15/arm64；30 个实时工具；cases.list_cases({}) 返回有效空列表；新世界独立复验与自测 schema/响应哈希一致；两次正常清理且证据保留 |
| PR 与下一步 | 已核对 [PR #2](https://github.com/xsw932187210-cell/chi-agent/pull/2) 合并至 `origin/main`（`03fedf9`）。本轮约定 PR 交用户审核合并；之后按授权决定环境迁移或下一阶段，B/C、模型 API 与官方判分不自动恢复 |
| 未验证项 | OpenSpec CLI、其他架构、真实 daemon 中断/网络故障的全部清理分支、模型往返、无评分 Agent 入口及判分认证；正常清理已实测，异常/超时用合成检查 |
| 真实运行 | 无真实 trial、官方 reward、实测模型用量/费用；当前真实入口因缺核算依据仍阻断，ungraded 另明确 unsupported |

接续材料：

- [A 独立审核与实际接入证据](bootstrap-baseline-a-review.md)
- [实现子代理与独立审核](../docs/luna-subagent-workflow.md)
- [D0 接续 Prompt](../docs/d0-handoff-prompts.md)
- [当前交接规格](../openspec/changes/bootstrap-baseline/handoff.md)
- [本地与 GitHub 工作流](../docs/github-workflow.md)

每轮审核记录“已审”和“已通过”的实际身份；当前无同一候选未提交的实现差异。普通问答不默认创建子代理，不因 D0 通过自动启用后续阶段、付费调用或后台唤醒。

| 日期 | 阶段 | 基线 SHA | 已审候选 SHA | 结论 | 报告 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 | D0 首审 | `c660e2699b8b972c9aa1d114a3e4d63510b8985e` | `01a044fe237aff7ddcafc3332e9444d443c41999` | 未通过，R1–R8 待返工 | [首审固定报告](https://github.com/xsw932187210-cell/chi-agent/blob/ff2e23d72fe1ae37b41872fbae655a1498c592e0/chi-agent/reviews/bootstrap-baseline-d0-review.md) |
| 2026-10-25 | D0 复审 | `ff2e23d72fe1ae37b41872fbae655a1498c592e0` | `c4b410a954bde9dbef64671a1c8079d90b68b79e` | 未通过，关闭五项，剩 R2/R3/R5 | [复审固定报告](https://github.com/xsw932187210-cell/chi-agent/blob/35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9/chi-agent/reviews/bootstrap-baseline-d0-review.md) |
| 2026-10-25 | D0 双 Luna 交付验收 | `83f3a8b425276cd7e987aeeb77c6a194bb79ec87` | `b7f894130df93ded69496576b83e6dcdcab7e56b` | 当前开发目标下离线代码验收通过；无真实任务/官方判分/用户完整验收 | [本轮独立验收](bootstrap-baseline-d0-review.md) |
| 2026-10-25 | A 双 Luna 交付验收 | `d1c9f991eda9548974838f72578078f9f9b05757` | `a173409416cf111ec2f2cc45247aa592b5ddd77e` | 官方环境及无模型只读 MCP 通过；PR #2 已由用户合并，B/C/判分暂停 | [A 独立审核](bootstrap-baseline-a-review.md) |

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
