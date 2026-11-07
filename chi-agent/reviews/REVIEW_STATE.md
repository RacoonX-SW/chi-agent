# 审核接续状态

更新：2026-11-06。只保存接续所需状态；实现通过范围以对应报告为准，存储提交不能代替验收。

| 项目 | 当前状态 |
| --- | --- |
| 当前任务 | PR68（Gemini Pass）合并 `e3b58ba`；PR70（target null schema）合并 `1c008bb`。九题 nullfix 身份：bundle `b7e247f6…`、runtime `dafc9ce9…`、1800s、requirements off。B-011 成功；9 题中 **2 complete（t016 claim；t024 blocked/no claim）、6 failed、1 not_run**。`final-c-cm-asthma` round21 `chi_timeout` **pending 保留**，按停止条件 `final-c-cm-ckd` 未运行；无自动重试。详见[执行记录](nine-task-nullfix-execution-20261106.md)。 |
| 协作 | DeepSeek按用户批准实现 1800s 策略、更新代码/文档并执行一次新 B/C；本轮自查标为“执行者检查”，不冒充独立审核。未merge/auto-merge；429 后停止，用户决定等待/重试/对账 |
| 最新独立审核 | 包外返工`bfc1d8f`在限定离线范围通过，前置计数P1及重复反例P2关闭；`36c2c79`有条件通过、`83749ac`未通过保留原义。包内`36db613`及包外`8992af1`维持旧范围，`33e6eca`/`4613fd1`失败与`50dd338`条件结论不改写。详见[报告第8节](final-validation-admission-review.md#8-gpt-独立复审与历史结论2026-11-06) |
| 上次独立审核候选 | Y最终HEAD `283ea63216251734fdc3fba86908eeb76c0feb98`（容量实现 `6ae9ee1c5072cc9f88af9236707e19afccf95f06`）此前已审，在既定限定离线范围通过。原 `33d3e412…` / `0bf6c441…` 未通过结论保持其历史含义，不能用新通过回写旧失败 |
| 上次通过的实现提交 | W `ad2569937e0afe649807669c70f86da97c708e86` 仅在统一本地操作者、同账CM、失败/终态/清理及固定一次开发运行范围通过；payer业务不符原样保留。不能扩大为临床批准/官方成绩，official_reward=null |
| 存储与验收身份 | 按用户要求上次通过实现身份仍保留上列W；Y限定离线通过单列，PR30已合并仅说明进入主线，不扩大为真实模型准入/业务或官方验收。文档/PR/合并提交不代替实现验收，见 [GitHub 工作流](../docs/github-workflow.md) |
| 当前分支与接手改动 | 从`origin/main=8154148`新建`deepseek/agent-timeout-1800`，PR65 已合并 `dbbd356`；本轮从 `origin/main=dbbd356` 新建 `deepseek/p0-p1-validation` 记录 P0/P1，仅文档，不改代码/旧 state。 |
| 当前开发（requirements） | `chi-requirements-v1`（默认 off）、v4 state/completion、来源/claim 门禁已由 PR66 合并；P1 可发现性修复 `47b5417` 经 Gemini 独立复审 **Pass/LGTM，0 Blocker**，[PR68](https://github.com/xsw932187210-cell/chi-agent/pull/68) 已合并 `e3b58ba`。P1fix3 在真实 on-run 中完成并 claim（32 HTTP、451.8s、4/4 done）；默认仍 off，九题基线未启用。详见[P0/P1记录](p0-p1-validation-20261106.md)与[九题准入准备](nine-task-admission-20261106.md)。 |
| 环境目标与实际 | W复用Python3.12、V三角色固定资源、原world/dev/controller及SDK/PDF/U overlay，无新依赖安装/升级或G/H重做。SDK/源码/PDF/vendor逐字段与V一致；开发操作者/患者模拟器排除参赛包，官方Anthropic默认保留 |
| 本地开发预算 | record_only/null cap、原锁/未知门禁不变。用户明确保留payer-010 unknown/旧pending、不核销重发，特定批准同eval-vprep-20261104一次S（≤50HTTP、仅摘要）；本次许可已使用，旧B许可也已使用，不回写eval-abl-on2历史授权或旧未知结算。旧账hash未变；可信token费用缺项可null/warning，新未知停止，零重试/回退，Extra Usage沿既有关闭决定 |
| 后续费用规划 | Go继续record_only/null cap，费用缺项与token未知分别处理，三项USD分列且不混旧CNY；W实际费用/用量只见W报告。旧累计因S未结算仍不完整，不冒充已核清账户消费/余量；不恢复t019/Claude/F.5 |
| DeepSeek 调用时段 | [避峰约定](../../COLLABORATION.md#deepseek-api-调用时段2026-10-28)仅适用 DeepSeek 官方 API 直连；经 OpenCode 调用 DeepSeek 可全天安排已授权工作，Go较充足额度用于后续按阶段重排实验。仅文档执行，不新增程序时钟门禁或自动唤醒 |
| 付费验证范围 | 旧S许可1逻辑run/19main+1summary/20 settled不回写。B-001 3main/1387/124 known。900s t015 retry1：23 requests全settled，input2405369/output31755，list0.62085581/allowance0.37251349/charged0，`chi_run_time_limit`，无pending。1800s B-003 3main/1407/130；B-004 3main/1366/106；B-005 3main/1357/89；B-006 3main/1417/146；B-007 3main/1400/118；B-008 3main/1396/126；B-009 3main/1386/116；均receipt/seal有效。P0 C `final-c-provider-t015-p0`：34 HTTP，input4226254/output42870，list0.69348377/allowance0.41609026/charged0，complete。P1 C `final-c-provider-t015-p1`：37 HTTP，input5626924/output51997，list0.87326112/allowance0.52395663/charged0，`chi_run_time_limit`，requirements undeclared。P1fix C：2 HTTP，round1 settled/round2 pending HTTP429，input12699/output230（部分已知），list0.00215430/allowance0.00129258/charged0，`chi_http_error`。P1fix2 C：34 HTTP（33main+1confirmation）全settled，input5003188/output59671，list0.77538906/allowance0.46523340/charged0，`chi_run_time_limit`，requirements 7/7 done、claim null。P1fix3 C：32 HTTP（31main+1confirmation）全settled，input4363100/output43237，list0.68036482/allowance0.40821889/charged0，complete，requirements 4/4 done、claim 已记录。九题 nullfix：B-011 3main/1367/101；C 已启动 8 题、物理 HTTP 186、input20494515/output233047；t016 complete claim、t024 complete blocked；t015/t021/t022/t023/cm-anorexia/cm-asthma failed；cm-ckd 未运行；cm-asthma round21 pending。未自动重试；未执行摘要/恢复/患者/Y/Trial/judge/发布；旧unknown不结算、旧B不复用 |
| 正式提交前置 | U已实证真实Harbor工厂/类型/SingleStepTrial与固定官方Docker环境接点；原stock仍不自动选用，官方CLI、经Harbor的真实Go推理、完整生产供应/状态配送及F.5未验，不等于正式冻结 |
| 本轮验证 | 执行者检查（非独立审核）：P0 B-005 + t015 off：34 HTTP、393.6s、complete、claim、7/4/1；P1 B-006 + requirements on：37 HTTP、1829s、`chi_run_time_limit`、undeclared、claim null。修 schema/guidance（`47b5417`）：28 requirements/129 相关 OK/3 skipped，全量 654/18 skipped/3 既有 import error；新 bundle `454b048e…` verify/preflight 通过。P1fix：B-007 成功，C round2 HTTP429 pending（保留）。P1fix2：B-008 成功；C 34 HTTP、1805s、`chi_run_time_limit`，requirements 7/7 done、claim null。P1fix3：B-009 成功；C **complete**，32 HTTP、451.8s，requirements 4/4 done、completion v4 `mechanical_pass`/`observed`、claim 已记录、final output 已给出，业务 7/4/1，无 pending/halt，cleanup/quiescence confirmed。Gemini 独立复审 PR68 **Pass/0 Blocker**；PR68 合并 `e3b58ba`。PR70 target null schema 修复（105 相关/656 全量、3 既有 import error）合并 `1c008bb`；九题 nullfix bundle `b7e247f6…`/runtime `dafc9ce9…`，B-011 成功；8 题已启动：t016 complete claim、t024 complete blocked，其余 6 题 failed，cm-ckd 未运行；cm-asthma round21 pending 保留，无自动重试。旧900s/429/1800b pending 保留；Trial/judge/发布为0 |
| 历史 A 证据 | 原 A 的跨版本离线检查、官方 MCP 接入和异常分支范围保留在 [A 审核](bootstrap-baseline-a-review.md)，不被本轮环境回归替代 |
| PR 与下一步 | PR42–PR70已由用户合并：PR68 merge `e3b58ba`、PR70 merge `1c008bb`。[PR71](https://github.com/xsw932187210-cell/chi-agent/pull/71) 记录九题 nullfix 结果，base=main，未 merge/auto-merge。九题执行到 `final-c-cm-asthma` round21 `chi_timeout` pending 后停止；`final-c-cm-ckd` 未运行。结果：t016 complete claim、t024 complete blocked、t015/t021/t022/t023/cm-anorexia/cm-asthma failed；物理 HTTP 186、input20494515/output233047。下一步由用户决定：等待/新 state+B/显式 acknowledgement，或先修工具参数格式与 context/output 预算后新 bundle 重跑；不得静默清 pending、不自动重试、不换题、不换根。旧 t015 round4、P1fix round2 429 与旧900s/429/1800b pending 均保留，旧payer-010 unknown不变 |
| 外部条件复核 | 2026-11-01已读官方Rules正文：75道公开题；公开结果/75题audit packet非必需；必交Kaggle Writeup+私有可运行包+IEEE两栏≤5页报告，截止11/15 23:59 UTC（报名/组队11/7，结果11/23）；患者为模拟数据、无真实PHI；handbook受限且不得再分发。Go隐私/非编码用途用户明确不再确认，按用户决定继续，但不写成官方许可。来源：`https://www.kaggle.com/competitions/chi-bench/rules`；旧审批包保留历史，[新草案](../openspec/changes/validation-preparation/proposal.md)本身不授权，B/S各自具体批准及执行以对应报告为准，其他真实运行仍未获准 |
| 未验证项 | payer终态不符的充分原因、业务改进及证据核对原型收益、其他任务/跨任务统计稳定性、内容verdict/临床批准/官方分数；旧未知可信结算、Go非编码用途官方确认、十一月ZDR、1M/长期缓存；Harbor官方CLI/真实Go Trial/完整配送/F.5、OpenSpec CLI、controller硬中断/daemon故障；F0–F3真实模型使用/检索命中质量/claim门禁误伤/F0逐题抽样、claim后写真实行为；F4真实tokenizer/预算余量、真实MCP超时副作用与更长读超时值、模型对停滞提示的遵守、自动压缩可行性；Z1真实Harbor Trial/world镜像/依赖锁hash/state清理/凭据注入、F7真实manifest/record、Z6真实干净依赖安装/空状态/Harbor Trial/模型/清理 |
| 结构/可靠性判断 | C3闭包/C4用途核对保持；C5已核对completed/outcome→解析推荐→最终决定，原MD字段不单独证明绕过。会话支持/临床充分性、未锁环境依赖和外部编排动态计时未关闭；[架构评审](../docs/architecture-review.md)保留历史及后续指针，不搬目录/拆journal |
| 待讨论/核对 | 输入摘要本样本端点返回200但length/空正文被拒，端到端未通过，语义/收益未验；输出恢复真实探针未获准。payer-010仍未知，本次特定后继S决定不回写旧结算或eval-abl-on2授权佐证。九题首题t015旧900s round4 pending：240.022s transport timeout，provider log确认682.8s后200（524/600s+200/82.5s），未结算。900s retry1：942s `chi_run_time_limit`，23 requests all settled，无pending；已建case/大部分字段，差最终回读。1800s retry：首请求HTTP429 `overloaded`，pending round1；新 state 1800b：20 settled+round21 pending，`chi_transport_error`（30.8s，无response），699s，非时间上限；已建case/大部分字段，差业务回读。提供方连续429/transport不稳定；1800s窗口仍未检验。P0 1800s/off t015 已完成（34 HTTP、393.6s、claim、7/4/1）；P1 requirements on 37 HTTP/1829s `chi_run_time_limit`，requirements undeclared、claim null；已修 schema/guidance（`47b5417`，Gemini Pass，PR68 合并 `e3b58ba`）。P1fix C round2 HTTP429 pending（保留）；P1fix2 34 HTTP/1805s `chi_run_time_limit`，7/7 done、claim null；P1fix3 32 HTTP/451.8s **complete**，requirements 4/4 done、claim 已记录、7/4/1。PR70 target null schema 合并 `1c008bb`；九题 nullfix bundle `b7e247f6…`/runtime `dafc9ce9…`，B-011 成功；8 题已启动：t016 complete claim、t024 complete blocked、其余 6 failed，cm-ckd 未运行；cm-asthma round21 `chi_timeout` **pending 保留**，无自动重试。旧pending及`p1fix-on` round2不静默清。C5原21/22及md.signed_off=false保留，note交流陈述没有已识别的会话支撑，不改成业务通过或直接预定修法 |
| 真实运行 | W历史保留。2026-11-01 external：v2 B成功/provider超时已对账；v3 B3成功/payer 002工具批次失败/CM 002超时已对账。**v4（identity`f7d11712…`）**：B4成功；payer 003 complete（37请求、4项业务检查false与W相同）；CM 003 complete（患者未同意→停在outreach_complete；暴露workspace写路径被拒）。**v5（identity`c8cba721…`）**：B5成功；CM 004 complete（37+10请求、602s；写入0拒绝；14项检查全true、care plan finalized）。**v6（identity`55b55cd7…`）**：B6成功；payer 004 complete（35请求、664万入、26/28项true：MD audit与MD决定已转true；剩余letter_types/target_status由隐藏expectations定义，不在公开可推断范围，按26/28收口）。全部settled、pending=null、清理确认。Y未运行。0自动重试/换账根，official_reward=null。原Q/R/S/旧未结算原样；Claude/付费临床评审0。2026-11-06新隔离state：新B `final-b-001` 成功；九题首题 `final-c-provider-t015` round4 pending（`chi_timeout`），其余8题未运行，pending未清 |

接续材料：

- [最终候选冻结与准入准备](final-validation-admission-review.md)；[机器候选](validation-candidate-20261105.json)；[B计划](coding-b-plan-20261105.json)；[九题预登记](nine-task-preregistration-20261105.json)；[G0模板](admission-decision-template-20261105.json)
- [九题资源冻结](nine-task-resource-freeze-20261106.json)；[执行阶段报告](final-validation-execution-review.md)；[新B执行记录](final-validation-b-execution-20261106.json)；[九题执行记录](final-validation-nine-task-execution-20261106.json)；[1800s策略与429记录](agent-timeout-1800-20261106.md)；[九题审批草案](nine-task-approval-draft-20261106.md)
- [本候选唯一获准输入摘要探针：失败、用量、清理及后续任务](summary-endpoint-probe-review.md)
- [chi-requirements-v1 离线实现与验收](requirement-completion-gate-review.md)
- [P0/P1 实际验证：1800s t015 与 requirements on](p0-p1-validation-20261106.md)

- [本候选唯一获准coding-B：执行、账目与清理](validation-coding-b-review.md)

- [交付候选冻结与最小真实验证准入准备](validation-preparation-review.md)；[机器候选清单](validation-candidate-20261104.json)；[新审批草案（未授权）](../openspec/changes/validation-preparation/proposal.md)

- [全项目累计审核及R1/R2返工](project-cumulative-review.md)

- [输入摘要：实现与独立离线审核](input-summary-review.md)

- [C5 P2P公开路径、原证据回溯及独立审核](c5-p2p-public-path-review.md)

- [C4用途参数一致性及独立审核](c4-policy-consistency-review.md)

- [C1只读准入核查与C3包依赖闭合](c1-c3-admission-package-review.md)

- [C2输入计量与输出截断恢复：实施及独立审核](c2-input-output-recovery-review.md)

- [架构来源、Codex初核、模块导航与负责人](../docs/architecture-review.md)
- [可靠性治理工作包及验收](../openspec/changes/project-completion/design.md#15-可靠性治理与分阶段重构)
- [真实批次A执行记录：B成功、provider C超时未结算](real-external-batch-a-review.md)
- [真实运行一次性审批包（草案，未生效）](../openspec/changes/real-run-approval/proposal.md)
- [Z6 干净依赖安装与独立包预检](z6-clean-repro-review.md)
- [Z6 离线发布包与干净环境校验](z6-release-package-review.md)
- [Z1 正式配送供应与离线准入](go-chi-delivery-supply-review.md)
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
