# 审核接续状态

更新：2026-10-28。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | N 实现、独立审核与原两题开发回归完成，待用户 PR 审核：公开证据确认及患者/实体门禁已接入 K C；t019 正常结束且无错患者提交，t013 目标提交但总请求耗尽。Claude/F.5 继续暂停 |
| 协作 | 默认一个 GPT-6.1 Terra / high 实现子代理、主代理独立审核；第二个按明确并行收益启用，纯文档由主代理完成。历史 Luna 派发不改写。现行职责见 [协作约定](../../COLLABORATION.md#当前协作方式2026-10-27) |
| 上次独立审核候选 | `77c25b04216bc492ed9cc25196abb2cf019d01ea`，N-R2 可信角色上限、结算元数据及错误响应边界经固定快照/SDK/患者实体独立检查通过，见 [N 审核](provider-patient-binding-review.md) |
| 上次通过的实现提交 | `77c25b04216bc492ed9cc25196abb2cf019d01ea`，离线实现和新源码 B 通过，原两题真实结果按上列限制；此前 N/M/L 失败、claim 和费用均保留，不称业务全通过 |
| 存储与验收身份 | 实现验收身份保留上列 SHA；文档提交、PR 和合并提交不代替实现验收。Git 与上传流程见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | PR #17 已核对合并，从最新 `origin/main` `2b29a69dd9628586daa9481b11af6b8223b0b079` 建立 `codex/patient-identity-binding`，写入前干净；一个 Terra / high 实现，主代理独立审核后运行 |
| 环境目标与实际 | N 复用 Python 3.12 dev/controller/world、H SDK 与 K PDF 卷及 M 固定资源，没有新下载/安装、改锁或镜像；G/H 安装和打包未重做。身份核对与结果见 N 报告 |
| 本地开发预算 | 沿用多次 C 和独立 DeepSeek 评审的 record_only/null cap；N 逐请求/旧账/累计对账通过，两套 pending=null、controller clean、精确资源已清理；未知用量仍阻挡接续，零自动重试；旧 capped/正式入口边界保留 |
| 正式提交前置 | F.2–F.4、G/H 离线范围通过，K 本地受控真实接入已跑通；正式评测包/官方 harness 的 live 配送及 F.5 完整冻结仍未完成 |
| 本轮验证 | 最终源码保持同一模型/提示/角色配置完成两题回归，完整导出均只影响目标患者；t013 未正常结束，不能只据局部 verdict 算成功。工程修复前全部失败和评审不完整均见 N 报告；两题已成开发题，无新泛化证据 |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | [PR #17](https://github.com/xsw932187210-cell/chi-agent/pull/17) 已合并；[PR #18](https://github.com/xsw932187210-cell/chi-agent/pull/18) 为本分支 base=main，待用户审核合并，未开启 auto-merge。下一建议为包含确认子请求的剩余请求提示/完成收束，须另立有界规格 |
| 未验证项 | 未见任务的患者匹配可靠性、t013 正常收束、最终付款方批准、独立临床/规则裁决与官方得分、Claude 认证、真实 tokenizer/账单、其他任务/架构、OpenSpec CLI、真实网络/daemon 故障与硬取消；同 provider 确认/局部评审不替代这些证据 |
| 真实运行 | N 均新世界/独立 attempt，完整终态和全部失败保留，无人工业务代选、无隐藏答案回灌；official reward=null，正式入口仍 record_only/null cap。详细结果只见 [N 审核](provider-patient-binding-review.md) |

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

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
