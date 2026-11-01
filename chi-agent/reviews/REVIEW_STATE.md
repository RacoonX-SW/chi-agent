# 审核接续状态

更新：2026-11-01。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | F0–F6已合并。F7离线工具候选`fd617c3`经外部Gemini复审**通过（LGTM）**：manifest off/on/na 冻结、record严格校验、全分母汇总、CLI；451 tests（2个既有环境错误、8 skipped），**无真实实验/模型/判分**。待创建base=main的PR由用户合并。Z1–Z8、真实Z4/Z5仍待做；自动压缩设计搁置。证据见[F7报告](experiment-harness-review.md) |
| 协作 | OpenCode内Gemini子代理启动失败（`Insufficient account funds`）；用户切外部订阅Gemini审阅，OpenCode只用DeepSeek。F0–F3、F4–F6均由DeepSeek实现/自测，外部Gemini离线复审；用户最终验收/合并。现行专项与默认模型关系见[协作约定](../../COLLABORATION.md#当前协作方式2026-10-27) |
| 最新独立审核 | F7候选`fd617c3`/文档`bc2d1c2`经外部Gemini复审通过（LGTM）：限离线契约与Docker合成；未调用真实模型/API/判分/患者模拟器。此前F4–F6`efc9019`、F0–F3`5c1fa51`同样离线通过；均不能扩大为真实模型/业务/官方评分通过 |
| 上次独立审核候选 | Y最终HEAD `283ea63216251734fdc3fba86908eeb76c0feb98`（容量实现 `6ae9ee1c5072cc9f88af9236707e19afccf95f06`）此前已审，在既定限定离线范围通过。原 `33d3e412…` / `0bf6c441…` 未通过结论保持其历史含义，不能用新通过回写旧失败 |
| 上次通过的实现提交 | W `ad2569937e0afe649807669c70f86da97c708e86` 仅在统一本地操作者、同账CM、失败/终态/清理及固定一次开发运行范围通过；payer业务不符原样保留。不能扩大为临床批准/官方成绩，official_reward=null |
| 存储与验收身份 | 按用户要求上次通过实现身份仍保留上列W；Y限定离线通过单列，PR30已合并仅说明进入主线，不扩大为真实模型准入/业务或官方验收。文档/PR/合并提交不代替实现验收，见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | F0–F6已合并，`origin/main`=`4ade699`。F7分支`codex/f7-experiment-harness`，实现`fd617c3`、文档HEAD`bc2d1c2`；PR待创建，未合并。未改vendor/账目/历史证据；下次开始须再核对远端 |
| 环境目标与实际 | W复用Python3.12、V三角色固定资源、原world/dev/controller及SDK/PDF/U overlay，无新依赖安装/升级或G/H重做。SDK/源码/PDF/vendor逐字段与V一致；开发操作者/患者模拟器排除参赛包，官方Anthropic默认保留 |
| 本地开发预算 | record_only/null cap、原Go/CHI账根及Q→CHI锁不变；上次审计active pending/halt=null，本轮未重审真实账。唯一旧超时经用户批准留档，其原失败请求仍pending未结算，原账原字节保留；不再占用全局准入。新费用缺项保留null/warning，新的结果/token未知仍停止；不换账根、零自动重试/回退、Extra Usage关闭 |
| 后续费用规划 | Go继续record_only/null cap，费用缺项与token未知分别处理，三项USD分列且不混旧CNY；W实际费用/用量只见W报告。旧累计因S未结算仍不完整，不冒充已核清账户消费/余量；不恢复t019/Claude/F.5 |
| DeepSeek 调用时段 | [避峰约定](../../COLLABORATION.md#deepseek-api-调用时段2026-10-28)仅适用 DeepSeek 官方 API 直连；经 OpenCode 调用 DeepSeek 可全天安排已授权工作，Go较充足额度用于后续按阶段重排实验。仅文档执行，不新增程序时钟门禁或自动唤醒 |
| 付费验证范围 | 本轮规划新增真实请求0，不读Key、不启动题世界；W/Y旧清单已收束。补齐功能计划后，额度提案修订为最多40次C、16次coding-B及2响应患者probe，含机制对照/九题未见集，**待审尚未生效**；独立摘要请求不包含。启动时一次性固定实际范围/用途/额度，包内不逐步等GPT。t019例行付费/Claude/付费临床评审等暂停保持，F.5待启动 |
| 正式提交前置 | U已实证真实Harbor工厂/类型/SingleStepTrial与固定官方Docker环境接点；原stock仍不自动选用，官方CLI、经Harbor的真实Go推理、完整生产供应/状态配送及F.5未验，不等于正式冻结 |
| 本轮验证 | Docker/Python3.12全量`451 tests`：2个既有环境错误（缺`anthropic`）、8 skipped；新增15个F7测试，定向15 tests OK。manifest字段/off-on配对/比较、全分母、跳过/阻断、缺日志/用量、候选不一致、重复/计划外、official、by_role、CLI均通过；外部Gemini离线复审通过（LGTM）。无真实实验/模型/判分；详见[F7报告](experiment-harness-review.md) |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | PR28–PR34均已合并。F7分支已推送、外部Gemini复审通过，待创建base=main的PR由用户合并；合并后进入Z1正式配送离线准备。真实Z4/Z5运行仍需用户一次性确认任务/候选/资源/次数 |
| 外部条件复核 | 本轮内置浏览未取得当前Kaggle Rules正文，概览索引与上次Rules解释冲突，强制材料/全量公开评测要求未重新确认；Go官方页面DeepSeek月度ZDR脚注仍只到2026-10-31，CHI非编码用途/十一月条件未确认。见[Z0来源与处置](../openspec/changes/project-completion/design.md#4-z0尽早解决会改变整个计划的外部条件)，不因额度较多自动放行对应载荷 |
| 未验证项 | payer终态不符的充分原因、业务改进及证据核对原型收益、其他任务/跨任务统计稳定性、内容verdict/临床批准/官方分数；旧未知可信结算、Go非编码用途官方确认、十一月ZDR、1M/长期缓存；Harbor官方CLI/真实Go Trial/完整配送/F.5、OpenSpec CLI、controller硬中断/daemon故障；F0–F3真实模型使用/检索命中质量/claim门禁误伤/F0逐题抽样、claim后写真实行为；F4真实tokenizer/预算余量、真实MCP超时副作用、模型对停滞提示的遵守、自动压缩可行性、F4–F6外部复审；F7真实manifest/record、检查项映射、日志/用量字段 |
| 真实运行 | W固定当前B与三角色各一次完成，所有新请求已结算、零新增未知/自动重试/回退，owned资源及能力文件已清理。payer批准结果未通过固定终态检查，不改写；原Q/R/S失败及唯一旧未结算原样，Claude/付费临床评审0，official_reward=null。本轮F0–F3真实请求0、未启动题世界 |

接续材料：

- [F7 实验清单与全分母汇总](experiment-harness-review.md)
- [F4–F6 上下文、完成核验与失败处理](f4-f6-context-completion-review.md)
- [F0–F3 能力实现与离线证据](f0-f3-agent-capabilities-review.md)
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
- [Go 确认超时与未结算证据检查](go-chi-timeout-recovery-review.md)
- [真实Harbor启动预演与三题评分覆盖](harbor-launch-coverage-review.md)
- [代表角色接线与本地Go患者模拟](representative-role-baseline-review.md)
- [统一角色操作者与完整CM开发链路](unified-role-cm-lifecycle-review.md)
- [payer离线诊断与后续规格](payer-offline-diagnosis-review.md)
- [payer证据核对原型与开发shadow（实现者交付待审）](payer-evidence-prototype-review.md)
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
| 2026-10-30 | S Go CHI 混批恢复与完整终态 | `575b6d1ae5d1f7944166e92a22ce33d3f9e46fc9` | `32c24b79c4234954030a3f65c35f2d2d198fadf8` | 技术/独立包/新 B 通过；首次 t012 确认超时且用量未知，业务未完成，三 C 阻断未运行；旧证据保留，官方分数 null | [S 审核](go-chi-batch-recovery-review.md) |
| 2026-10-30 | T Go确认超时与未结算检查 | `25336ed774be934af1d7fc4765884d837e62ff15` | `c587b446a54833393c1feb7deaeb3ac6fca47bfb` | 用途等待/准入收尾/元数据/只读历史与导出检查离线通过；真实调用0，旧未知未核销，未新增B/C | [T审核](go-chi-timeout-recovery-review.md) |
| 2026-10-30 | T反馈费用记录与留档恢复 | `ce2aa1e29fcac4545a4af0846efee1ee64378305` | `721b14e17e37917d27f333d7aac6aaedfa99b9ad` | 独立审核/包/新B及一次回归、两次原冻结未见题的适用检查通过；旧未知留档未结算、历史不清零，官方分数null | [同一T报告](go-chi-timeout-recovery-review.md#pr费用反馈修订2026-10-30) |
| 2026-10-30 | U真实Harbor接入与评分覆盖 | `fd140bd805e906aa95c6afc1a1e76ab813c441e7` | `2c31a931f26ba70581ef4470fb83755037e0855c` | 独立组件/合成启动及三题只读盘点通过；真实模型0，内容/官方评分null，CLI/配送/F.5未验 | [U报告](harbor-launch-coverage-review.md) |
| 2026-10-31 | V代表角色与开发患者模拟 | `c429ebec4d650fa56e65f2b2ded0a52851eb8c21` | `410a5b4f31444afd85f2850986a17d547a90f015` | 独立资源/三世界/嵌套账与最小真实Go探针通过；正式业务C/临床评审0，官方null，完整CM编排另验 | [V报告](representative-role-baseline-review.md) |
| 2026-10-31 | W统一角色操作者与完整CM开发链路 | `5a621dc67afd8f0e26088b3b993615066a993229` | `ad2569937e0afe649807669c70f86da97c708e86` | 独立本地链路/历史/失败终态/清理通过，唯一新B及三题各一次完成；provider关单、CM闭环，payer终态不符；无临床/官方评分 | [W报告](unified-role-cm-lifecycle-review.md) |

历史未通过候选及原始合成证据保留；原始日志在忽略目录，不上传 GitHub。沿用一份 D0 交付报告，区分子代理自测与主代理独立证据。历史 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 仍不是已通过候选。
