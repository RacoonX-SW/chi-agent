# 审核接续状态

更新：2026-10-26。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | B 规格与离线实现已通过主代理独立审核；仅合成协议探针，真实参赛模型 API、官方 runner 集成、C 和官方判分继续暂停。见 [B 审核](bootstrap-baseline-b-review.md) |
| 协作 | 默认一个 Luna High 实现子代理、主代理独立审核；第二个按明确并行收益启用，纯文档由主代理完成。现行职责见 [协作约定](../../COLLABORATION.md#当前协作方式2026-10-25) |
| 上次独立审核候选 | `6f9e9fadb89f9972f4483666489d83c9b371f67f`；首审未通过及返工证据同见 [B 审核](bootstrap-baseline-b-review.md) |
| 上次通过的实现提交 | `6f9e9fadb89f9972f4483666489d83c9b371f67f`，仅 B 离线协议/核算/失败边界；不能扩大为真实 provider、官方 runner、Agent 任务或用户完整验收。历史环境与 A 身份保留在原报告 |
| 存储与验收身份 | 实现验收身份保留上列 SHA；文档提交、PR 和合并提交不代替实现验收。Git 与上传流程见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | `codex/bootstrap-baseline-b-offline` 从已核对最新 `origin/main` 的 `e888377e428f5cdb9030b15ffb4325deb57e8365` 建立，开工时工作区干净；一个 `gpt-6-luna` / `high` 实现，主代理独立审核。历史学习与 A 验收证据保留 |
| 环境目标与实际 | 开发、调度 venv 与官方任务均实测 Python 3.12.15，当前验证架构为 aarch64/arm64；镜像、两锁与缓存复用身份见本轮审核，旧 3.13 镜像有备份标签 |
| 参赛预算 | 首轮真实 B/C 合计 5 元人民币的规划不变，写代码另计；本轮仅 synthetic 核算，不消费或重置该预算，真实模型调用未恢复 |
| 本轮验证 | 固定快照独立回归、补充边界、实际 CLI、原离线入口及 README 示例通过；首审失败和最终命令/结果集中在 B 审核，不由子代理自测替代 |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | [PR #4](https://github.com/xsw932187210-cell/chi-agent/pull/4) 已由用户合并至上列主线；[B 离线 PR #5](https://github.com/xsw932187210-cell/chi-agent/pull/5) 已推送并创建，base=main、head=codex/bootstrap-baseline-b-offline，待用户审核/决定合并。下一步先审核本轮产物/学习；真实 B/模型 API、C 与官方判分不自动恢复 |
| 未验证项 | 真实 transport、SDK/官方 runner 的思考历史与逐请求预算接入、真实 tokenizer/用量/价格/账单、无评分 Agent 入口及判分认证；其他架构、OpenSpec CLI 与真实 daemon/网络故障清理分支仍未补验 |
| 真实运行 | 无真实 trial、官方 reward、实测模型用量/费用；当前真实入口因缺核算依据仍阻断，ungraded 另明确 unsupported |

接续材料：

- [A 独立审核与实际接入证据](bootstrap-baseline-a-review.md)
- [B 离线独立审核与真实接入缺口](bootstrap-baseline-b-review.md)
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
| 2026-10-25 | Python 3.12 环境对齐 | `925d34b2b78c920b590f3bd8a43596f6ae327bdc` | `726e80e5dc7ca5025179131b5e90802e74efc7ed` | 开发/调度及无模型 A 回归通过；PR #4 已由用户合并 | [环境审核](python312-alignment-review.md) |
| 2026-10-26 | B 离线准备 | `e888377e428f5cdb9030b15ffb4325deb57e8365` | `6f9e9fadb89f9972f4483666489d83c9b371f67f` | 合成协议/核算及失败边界通过；真实 B、C、官方判分暂停 | [B 独立审核](bootstrap-baseline-b-review.md) |

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
