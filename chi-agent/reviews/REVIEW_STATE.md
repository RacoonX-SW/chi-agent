# 审核接续状态

更新：2026-10-29。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | S 首候选独立离线/旧账迁移/真世界无 Key 捕获已通过，新 B 首个已结算响应因工具阶段缺可选 reasoning 被过严契约拒绝；四 C 未启动。正在按[兼容修订](../openspec/changes/go-chi-batch-recovery/design.md)离线修复、重固定/审核；全部尝试见 [S 报告](go-chi-batch-recovery-review.md)，R 原失败/终态缺口不改 |
| 协作 | 默认一个 GPT-6.1 Terra / high 实现子代理、主代理独立审核；第二个按明确并行收益启用，纯文档由主代理完成。历史 Luna 派发不改写。现行职责见 [协作约定](../../COLLABORATION.md#当前协作方式2026-10-27) |
| 上次独立审核候选 | R `5b60b3122bf8c689b47750c5681a7a5a188d8443`；关闭首候选 R1–R4，独立离线技术检查与新 B 通过，C 业务未通过。包/运行身份及证据只见 [R 审核](chi-go-evaluation-entry-review.md#返工候选的独立通过范围) |
| 上次通过的实现提交 | R 同上 SHA 仅限技术接线/离线与 B，不代表 CHI 成功。P t013 当前开发检查已收束，Q coding 历史保留；official_reward=null，旧失败/claim/费用不变 |
| 存储与验收身份 | 实现验收身份保留上列 SHA；文档提交、PR 和合并提交不代替实现验收。Git 与上传流程见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | PR #22 已实际核对合并，fetch 后最新 `origin/main` 为 `575b6d1ae5d1f7944166e92a22ce33d3f9e46fc9`，从该点干净建立 `codex/go-chi-batch-recovery`；主代理规格/独立审核/Git，唯一 Terra/high 写实现 |
| 环境目标与实际 | R 复用 Python 3.12、既有镜像/SDK/PDF 卷，无安装/改锁/重建/G/H 重做。t012 原世界与捕获修正检查的新初始世界均已清理；后者没有 Agent/模型请求，不补作原终态 |
| 本地开发预算 | record_only/null cap 不变。R 本地 CHI 固定在旧 Go 账根的 chi-evaluation 子目录，运行全程审计/持旧 Q 锁；旧账原字节保留。最终已完整审计 CHI/Q 证据且 pending/halt=null，native K/review pending=null；未知用量阻断、零自动重试 |
| 后续费用规划 | native 规划维持 P 后口径；Go 余额实扣、价目价值、套餐消耗分列 USD，订阅固定费另计，不混 CNY 或清零。累计及本轮金额仅见 [R 报告](chi-go-evaluation-entry-review.md#环境包与用量口径)，账户其他消费/余量未核清；不自动恢复 t019/Claude/F.5 |
| DeepSeek 调用时段 | [避峰约定](../../COLLABORATION.md#deepseek-api-调用时段2026-10-28)仅适用 DeepSeek 官方 API 直连；经 OpenCode 调用 DeepSeek 可全天安排已授权工作，Go较充足额度用于后续按阶段重排实验。仅文档执行，不新增程序时钟门禁或自动唤醒 |
| 付费验证范围 | S 原 1B+四C 规格的首 B 已用 1 请求失败；按必要兼容修订另限修复候选一次 B≤6，仍仅两次 t012 和 t014/t017 各一次 C≤50，全轮≤207，第二 B 再失败则收束。先新候选独立审核/显式迁移，不自动重试。Go 用途未确认用户知悉；t013/t019、Claude/付费临床评审暂停 |
| 正式提交前置 | F.2–F.4、G/H 历史离线范围保留；R 可独立导出并从外部输入运行，原 stock harness 不自动选用。完整 Harbor 类型/配送及 F.5 最终冻结仍未验证 |
| 本轮验证 | S 首候选 `1f44ef564a5b4d8795b6f4fdd981cc78c5a68e01` 独立离线技术检查通过；一次 B 协议兼容失败、用量已知且完整审计 pending/halt=null，不代表业务通过。修复候选未定，尚无其 B/C。详细数值/身份只见 S 报告 |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | [PR #21](https://github.com/xsw932187210-cell/chi-agent/pull/21)与 [PR #22](https://github.com/xsw932187210-cell/chi-agent/pull/22)均已核对合并。S 完成后推送新分支并建 base=main PR，由用户审核合并；主代理不 merge/auto-merge。十一月隐私人工复核，未声称官方支持非编码 CHI |
| 未验证项 | Go 非编码 CHI/临床评审支持、十一月 ZDR、1M 上下文和精确上游快照/账单/长期缓存；P/O 稳定因果收益、未见迁移、最终批准/临床裁决/官方得分；完整 Harbor/F.5、CHI 源码身份迁移、OpenSpec CLI、真实硬取消/daemon 故障 |
| 真实运行 | R 新 B 成功；唯一 CHI C 运行到读取工具后因确认混批中止，无人工代选、无重跑。Go 开发评审尚未切换。Q/native 历史保留，Claude 调用为零，official_reward=null |

接续材料：

- [A 独立审核与实际接入证据](bootstrap-baseline-a-review.md)
- [B 离线独立审核与真实接入缺口](bootstrap-baseline-b-review.md)
- [C 离线执行控制独立审核](bootstrap-baseline-c-review.md)
- [模型/官方 runner 接入层独立审核](model-runner-integration-review.md)
- [真实 B 运行准备独立审核](b-live-preflight-review.md)
- [本地与评测预算策略分离独立审核](evaluation-budget-policy-review.md)
- [评测专用入口与干净目录包独立审核](evaluation-entry-bundle-review.md)
- [官方启动接点与独立安装复现审核](official-launch-reproduction-review.md)
- [真实 B/C 接入与首次试跑审核](real-b-c-ungraded-review.md)
- [Terra 与多次 C 开发尝试审核](c-development-retry-review.md)
- [DeepSeek 本地开发评审审核](deepseek-development-review.md)
- [两个新 PA provider 任务的固定条件基线](provider-two-task-baseline-review.md)
- [患者确认与绑定独立审核及开发回归](provider-patient-binding-review.md)
- [请求预算反馈与 50 次开发上限审核](request-budget-awareness-review.md)
- [公开字段依据提示与付费验证收窄](referral-field-guidance-review.md)
- [OpenCode Go 适配、全部尝试与独立审核](opencode-go-provider-review.md)
- [Go CHI 外部入口与独立包审核](chi-go-evaluation-entry-review.md)
- [Go CHI 混批恢复与终态验证](go-chi-batch-recovery-review.md)
- [DeepSeek 评审的数据来源与审批证据](../docs/docker-workflow.md#deepseek-开发评审的数据来源与审批证据)
- [实现子代理与独立审核](../docs/subagent-workflow.md)
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
| 2026-10-26 | F 预算策略分离与 trial 隔离 | `ab4cd870cc2fea2e32fd5cdf99ee7e513b5994cc` | `5c65d15a05e39c194b1efbddf14683eedeac3ded` | F.2–F.4 离线通过；F.5 和真实调用未完成 | [预算策略独立审核](evaluation-budget-policy-review.md) |
| 2026-10-26 | G 评测专用入口与干净目录包 | `07c377cb173ce2a3eb5447742e547f97547c0610` | `d4003cac37cad5396ef9b977914ff07c5367a0e1` | 固定默认 record_only/干净包离线通过；F.5 和真实启动未完成 | [专用入口/包独立审核](evaluation-entry-bundle-review.md) |
| 2026-10-27 | H 官方启动接点与独立安装复现 | `0ca299b8856a5d385b330569c49c0be6e213e32a` | `f562f60a1ecb1f35d716c7e06cede89083b6ad10` | 空卷安装/实际外部输入与日志离线通过，首审 R1 关闭；F.5/API/C/判分未完成 | [启动/安装独立审核](official-launch-reproduction-review.md) |
| 2026-10-27 | J 真实 B/C 接入与首次试跑 | `9b917f08a465091456329a1dd2d14c2f47a8b266` | `ba6786717a624d328d3f9bc1296392f9637888da` | 最终修复离线通过；前一候选真实 B 成功、唯一 C 启动失败；未重试/未判分 | [真实 B/C 审核](real-b-c-ungraded-review.md) |
| 2026-10-27 | K Terra 与多次真实 C 开发 | `3cca5f89de205cb8b608d4bded345e426577461f` | `2b6058d76232eccaa968c19d761993e93c34e1fb` | 独立通过；旧历史不变、当前 B3/C2 完成，业务状态已提交/付款方处理中，无评分 | [多次 C 审核](c-development-retry-review.md) |
| 2026-10-27 | L DeepSeek 本地开发评审 | `b44ce46384c37353c11f90044e696d7daceadbdb` | `c275bd5a5688d7736c70ea929cbb2286746d256e` | 独立通过；新 C 权威捕获、确定性部分与本地逐项评审完成，旧历史/失败费用保留，官方分数 null | [L 审核](deepseek-development-review.md) |
| 2026-10-28 | M 两个新任务固定条件基线 | `dee5ae0f3616a57c529acb706fe4c829fa16074c` | `f28ea578760f1134afe3a44603d856a94f0e2b8c` | 测试修复后独立通过，生产同真实 c4716a0；t013 完成，t019 轮数耗尽且错患者提交，官方分数 null | [M 审核](provider-two-task-baseline-review.md) |
| 2026-10-28 | N 公开患者确认与实体绑定 | `2b29a69dd9628586daa9481b11af6b8223b0b079` | `77c25b04216bc492ed9cc25196abb2cf019d01ea` | 独立离线/新 B 通过；最终两题均只影响目标，t019 正常结束，t013 总请求耗尽；早期失败全部保留，官方分数 null | [N 审核](provider-patient-binding-review.md) |
| 2026-10-28 | O 可信请求预算反馈与50次开发上限 | `88fa271081ac337cd1d547200ce202295e21d844` | `98e01ee152028a3d99267b38cd90245bbad24c1f` | 独立离线/新B通过；两题正常结束且只影响目标，但t013服务地点检查失败；组合变化无单项因果或泛化结论，官方分数null | [O审核](request-budget-awareness-review.md) |
| 2026-10-28 | P 通用字段依据工具提示 | `a1aa625c3b9fbc36df2fd6bf57e67787b5f2e526` | `ed15c2bcfae7076f1165c92b6bf52b3fa16caa65` | 独立离线/新B通过，允许时段一次t013正常结束、仅影响目标，当前开发检查通过；费用上升，不推断稳定收益/泛化，官方分数null | [P审核](referral-field-guidance-review.md) |
| 2026-10-28 | Q Go/V4.1 Flash coding接入 | `dac0f2459718231aa7d1c67666ae85874d1227c6` | `5ea044dcefe1bad88fecb69c078078d22df06182` | 独立离线、真实响应回放和源码接续通过；保留首个本地协议失败，第二个真实coding闭环完成，CHI/1M/正式包不在通过范围 | [Q审核](opencode-go-provider-review.md) |
| 2026-10-29 | R Go CHI 外部入口与独立包 | `d5fa0508618ced14aae012dbf6f47143090d041e` | `5b60b3122bf8c689b47750c5681a7a5a188d8443` | 离线技术与新 B 通过；唯一 t012 C 模型混批失败且缺原终态，业务验收未通过；不追加付费，官方分数 null | [R 审核](chi-go-evaluation-entry-review.md) |

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
