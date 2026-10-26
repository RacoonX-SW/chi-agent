# 审核接续状态

更新：2026-10-26。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | 真实 B 运行准备代码通过离线独立验收：source-pinned profile、通用受控传输、synthetic 请求账目和只读预检；见 [B 准备审核](b-live-preflight-review.md)。真实 API/C/判分继续暂停 |
| 协作 | 默认一个 Luna High 实现子代理、主代理独立审核；第二个按明确并行收益启用，纯文档由主代理完成。现行职责见 [协作约定](../../COLLABORATION.md#当前协作方式2026-10-25) |
| 上次独立审核候选 | `2244220638830dec3ef1bba36d562d7258870e79`，首审 R1–R5、已关闭 journal 和磁盘收尾问题已独立复验关闭，详情只见 B 准备审核 |
| 上次通过的实现提交 | `2244220638830dec3ef1bba36d562d7258870e79`，仅真实 B 运行准备的离线代码，不代表 provider/B 实际调用通过。接入层/C/B/环境/A 身份保留在各阶段报告 |
| 存储与验收身份 | 实现验收身份保留上列 SHA；文档提交、PR 和合并提交不代替实现验收。Git 与上传流程见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | 已核对 PR #7 merged=true，并从最新 `origin/main` `3d4f9db09d0a623b925ec0a3c43e29ff7f06e0db` 建立 `codex/live-b-preflight`；写入前工作区干净，继续一个 `gpt-6-luna` / `high` 实现、主代理独立审核 |
| 环境目标与实际 | 复用 Python 3.12 dev，SDK 在 Docker 独立可选依赖卷中安装/验收，固定包与环境身份见接入层审核；原镜像/两份基础锁未改，开发/调度对齐历史见 [环境审核](python312-alignment-review.md) |
| 参赛预算 | 首轮真实 B/C 合计 5 元人民币的规划不变，写代码另计；本轮仅 synthetic 核算，不消费或重置该预算，真实模型调用未恢复 |
| 本轮验证 | 最终模型层/基础 dev 全量、补充协议/预算/生命周期、实际进程退出/锁接力、README 与基础只读 CLI 均独立通过；数目/命令/限制只见 B 准备审核 |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | [接入层 PR #7](https://github.com/xsw932187210-cell/chi-agent/pull/7) 已合并；[B 准备 PR #8](https://github.com/xsw932187210-cell/chi-agent/pull/8) 已推送创建并附加本聊天，base=main、head=codex/live-b-preflight，待用户审核决定合并。即使准备通过也不恢复真实 API/C/判分 |
| 未验证项 | 真实 provider transport/认证、真实 tokenizer/framing/用量/价格/账单、官方世界中的 B/C 及判分认证；其他架构、OpenSpec CLI、真实网络/daemon 故障清理与硬取消仍未补验 |
| 真实运行 | 无真实 trial、official reward 或实测模型费用；新直接 runner 入口只完成离线验证，live 固定拒绝，原 cb/Harbor 的 ungraded gate 继续 unsupported |

接续材料：

- [A 独立审核与实际接入证据](bootstrap-baseline-a-review.md)
- [B 离线独立审核与真实接入缺口](bootstrap-baseline-b-review.md)
- [C 离线执行控制独立审核](bootstrap-baseline-c-review.md)
- [模型/官方 runner 接入层独立审核](model-runner-integration-review.md)
- [真实 B 运行准备独立审核](b-live-preflight-review.md)
- [实现子代理与独立审核](../docs/luna-subagent-workflow.md)
- [D0 接续 Prompt](../docs/d0-handoff-prompts.md)
- [当前交接规格](../openspec/changes/bootstrap-baseline/handoff.md)
- [本地与 GitHub 工作流](../docs/github-workflow.md)

每轮审核记录“已审”和“已通过”的实际身份；开发中改动不能替代固定候选。普通问答不默认创建子代理，不因 D0 通过自动启用后续阶段、付费调用或后台唤醒。

| 日期 | 阶段 | 基线 SHA | 已审候选 SHA | 结论 | 报告 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 | D0 首审 | `c660e2699b8b972c9aa1d114a3e4d63510b8985e` | `01a044fe237aff7ddcafc3332e9444d443c41999` | 未通过，R1–R8 待返工 | [首审固定报告](https://github.com/xsw932187210-cell/chi-agent/blob/ff2e23d72fe1ae37b41872fbae655a1498c592e0/chi-agent/reviews/bootstrap-baseline-d0-review.md) |
| 2026-10-25 | D0 复审 | `ff2e23d72fe1ae37b41872fbae655a1498c592e0` | `c4b410a954bde9dbef64671a1c8079d90b68b79e` | 未通过，关闭五项，剩 R2/R3/R5 | [复审固定报告](https://github.com/xsw932187210-cell/chi-agent/blob/35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9/chi-agent/reviews/bootstrap-baseline-d0-review.md) |
| 2026-10-25 | D0 双 Luna 交付验收 | `83f3a8b425276cd7e987aeeb77c6a194bb79ec87` | `b7f894130df93ded69496576b83e6dcdcab7e56b` | 当前开发目标下离线代码验收通过；无真实任务/官方判分/用户完整验收 | [本轮独立验收](bootstrap-baseline-d0-review.md) |
| 2026-10-25 | A 双 Luna 交付验收 | `d1c9f991eda9548974838f72578078f9f9b05757` | `a173409416cf111ec2f2cc45247aa592b5ddd77e` | 官方环境及无模型只读 MCP 通过；PR #2 已由用户合并，B/C/判分暂停 | [A 独立审核](bootstrap-baseline-a-review.md) |
| 2026-10-25 | Python 3.12 环境对齐 | `925d34b2b78c920b590f3bd8a43596f6ae327bdc` | `726e80e5dc7ca5025179131b5e90802e74efc7ed` | 开发/调度及无模型 A 回归通过；PR #4 已由用户合并 | [环境审核](python312-alignment-review.md) |
| 2026-10-26 | B 离线准备 | `e888377e428f5cdb9030b15ffb4325deb57e8365` | `6f9e9fadb89f9972f4483666489d83c9b371f67f` | 合成协议/核算及失败边界通过；PR #5 已由用户合并 | [B 独立审核](bootstrap-baseline-b-review.md) |
| 2026-10-26 | C 离线执行控制 | `4726444d21ba404e02d8fa1005b44b2f547c9a0f` | `6afd14af71dbbff43404490b0ba7c3e943f93e94` | 合成生命周期/单次 claim 及失败边界通过；真实 C 未运行 | [C 独立审核](bootstrap-baseline-c-review.md) |
| 2026-10-26 | 模型/官方 runner 接入层 | `4fe5092c74508ca1a96e6d27c53bd76ee384b9de` | `b5f60ddd744a4f60497bd1e19f4fec01f76fd2dc` | 固定真实包/官方循环的合成边界通过；真实 API/C/判分未运行 | [接入层独立审核](model-runner-integration-review.md) |
| 2026-10-26 | 真实 B 运行准备 | `3d4f9db09d0a623b925ec0a3c43e29ff7f06e0db` | `2244220638830dec3ef1bba36d562d7258870e79` | profile/guard/journal/preflight 离线通过；实际调用继续暂停 | [B 准备独立审核](b-live-preflight-review.md) |

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
