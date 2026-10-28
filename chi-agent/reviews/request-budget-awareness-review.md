# 请求次数反馈与 50 次开发上限审核

日期：2026-10-28（Asia/Shanghai）。基线为已合并 PR #18 的 `88fa271081ac337cd1d547200ce202295e21d844`，分支 `codex/request-budget-awareness`。一个 gpt-6.1-terra/high 实现并 Docker 自测，主代理规格、独立审核、教学、真实验证和 GitHub。最终实现 `98e01ee` 独立通过，两题均正常结束且只影响目标患者；t013 的服务地点检查失败仍保留，不能称两题业务全通过。

## 问题与组合实验

[N 报告](provider-patient-binding-review.md) 的 t013 主请求 29 加确认 1 耗尽共享 30，末段仍查询案件/信箱，尚未完成声明/最终回复；t019 第 27 次调用完成工具、第 28 次才输出最终回复。当前 claim_done 是普通返回标记，固定 SDK 默认继续调用模型。30 为自有开发配置，固定官方参考 runner 默认 50 且可调；不是 SDK 固有极限或已核对官方规定的 30。

用户授权本轮同时采用 K C 50 次共享上限与每次主请求的可信状态提示，属于组合变化，不能把效果单独归因于提示或放宽上限。限定 K C：保持 provider profile/旧账身份、模型/思考、主输出 8192/确认 32768、最多两次确认、资源/依赖/镜像、零重试与未知用量阻断；不迁移正式入口/历史 J，不改完成工具终止语义，不硬预留或为题目写停止答案。详见 [O 设计](../openspec/changes/request-budget-awareness/design.md)。

## 环境及旧历史

复用 Python 3.12 和既有 dev/controller/world 镜像、SDK/PDF 卷与锁；本轮不新增安装/下载，不重做 G/H。费用接续 N 全部历史的峰值保守估算 83.907990 CNY，非账单；原始失败、claim、评审和费用不清零。运行前已在 Docker 离线冻结既有文件指纹，两套 pending=null、controller clean，证据 `runs/request-budget-root/prior-files.json`。具体候选与实际结果在下文记录，原文/秘密/数据不上传。

## 固定候选与独立审核

固定候选 `98e01ee152028a3d99267b38cd90245bbad24c1f`。新增 `scripts/request_budget.py` 定义仅 K C 的不透明 capability、50 次限制、反馈版本/格式及当前是否已有完成声明记录。`_worker_run()` 为 K C 的 SDK 模型包装 `get_response()`，在每次调用时临时附加新鲜系统段，保留原 Agent.instructions/input；确认直接走原 client，不经过这层包装。controller 与 worker 均由相同常量给 SDK 配置 50，guard 仅在真实 K accounting/run schema、c-once、已验证策略/能力及源版 system prompt 一致时接受覆盖。

guard 独立重算运行状态，拒绝缺少/陈旧/重复提示、变造 base prompt 和额外 system 消息；普通 user/tool 中伪装预算的文本不获得权限，也不被误当可信控制段。共享请求计数在 reserve 后、实际发送前递增，确认也计入；每个主请求记录 `request_budget_feedback` 的版本/hash、已用/当前/剩余、声明状态/模式及软提醒。该字段仅进入逐请求 journal，不污染 aggregate pending 的原严格结构；旧 profile/ExecutionPolicy SHA 保持。

主代理读候选时提出两处必要补查：额外 system 消息的相互矛盾提示，以及 wrapper/SDK 耗尽早于下一次 guard 时停止原因丢失。实现代理补齐拒绝及耗尽标签，并用固定 SDK/官方循环覆盖“含确认”和“全主请求”两种 50 次耗尽，均为 50 settled、pending=null、没有第 51 次、primary_error=provider_request_limit_reached；没有改变完成工具语义或把耗尽记成功。

实现子代理曾因自身额度中断；用户要求继续后恢复同一 Terra/high 完成，未换模型或引入第二实现者。代码停止后，主代理从 Git archive 只读快照、无网络/凭据/socket、空 data/runs 的 Python 3.12 dev 容器独立通过 **324 tests / 143 subtests**。另编写 6 组独立检查：旧 profile/policy 身份、新模块入 K 身份；包含本次的计数/声明语义；缺失/陈旧/重复/额外 system 与 user 伪提示；未授权/B/default 的 50 次覆盖拒绝；两次确认计入 50 且无第 51 次；提示不能绕过未知用量。全部通过。

独立证据 `runs/request-budget-root/evidence/candidate-1/{pytest.log,independent.json}`，脚本 `check_independent.py`。真实运行前逐文件核对当前实现等于快照，固定任务资源、profile/模型、依赖锁和镜像与 N 一致，仅检查 Key 存在而不输出；实验身份 `experiment.json`。来源 `k-c-request-budget-v1`、反馈 `k-c-runtime-feedback-v1`，软提醒条件为当前请求之后剩余≤5。base system prompt 本体保持，其临时附加内容是显式实验变量，不宣称整体输入提示未改变。

## 全部真实尝试与终态对照

以下均使用最终固定 participant `98e01ee`，每个新世界独立 attempt，隐藏评分材料不提供给参赛 Agent，运行中不人工代选业务动作。实际费用按既有峰值输入 2 / 输出 8 CNY 每百万 tokens 保守估算，包含 provider 回报生成用量，非实际账单。

| attempt | 结果 | provider 请求 | 工具调用 | input / output tokens | 耗时秒 | 估算 CNY |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `o-b-20261028-001` | smoke_completed | 3 | 2 | 4,897 / 187 | 5.008 | 0.011290 |
| `o-c-t013-20261028-001` | completed_ungraded；业务字段检查有失败 | 28（含确认 1） | 47 | 4,539,533 / 31,619 | 312.140 | 9.332018 |
| `o-review-t013-20261028-001` | complete，局部 4/4 | 1 | 0 | 51,663 / 2,838 | 15.398 | 0.126030 |
| `o-c-t019-20261028-001` | completed_ungraded | 30（含确认 1） | 48 | 4,356,441 / 24,914 | 215.869 | 8.912194 |
| `o-review-t019-20261028-001` | complete，局部 8/8 | 1 | 0 | 63,993 / 9,477 | 48.628 | 0.203802 |

耗时口径：B 为说明材料生成到清理结束，C 为 claim 落盘到清理结束，review 为目录创建到结果写出，均排除此前准备；不是整轮开发耗时。安全摘要 `runs/request-budget-root/actual-summary.json`，原始运行/终态/评审/结算留在既有忽略目录。

### t013：正常收尾，服务地点检查失败

27 次主请求/反馈加 1 次确认，全部 settled/工具 returned。确认在第 10 次请求正常 stop，input=44,282、output=7,273，费用 0.146748（已含 C 总额）。反馈从第 1 次的“之前 0、本次 1、之后 49”，到第 28 次的“之前 27、本次 28、之后 22”，均与实际 provider round 一致；第 27 次调用 claim_done，第 28 次为最终回复，最后提示为 claim_recorded。没有达到原来的 30，更未触发剩余≤5的软提醒，不能据此证明调高上限或低余额提醒是收尾改善的原因。

完整终态中绑定在 grader 侧事后核对为目标患者，只有目标的 1 case/1 service_request/1 submission，case=submitted、intake=in_progress，其他患者业务实体为 0。确定性部分仅 **8/9**，`new_referral.site_of_service=false`；DeepSeek 局部 **4/4 true**，二者覆盖不同，不能用局部 verdict 覆盖失败。模型在建案时显式传入 `site_of_service=rehabilitation_facility`，终态保持同值；未见预算传输代码篡改字段的证据，也不能排除提示变化/随机性影响其决策。只将此归为实际业务字段选择与部分检查契约不一致，不独立作临床裁决，不把隐藏可接受答案写入 Agent 或代码。

独立诊断 `t013-field-diagnostic.json`，完整实体归属对照 `terminal-comparison.json`，capture manifest SHA-256 `41aa6ad2bb8b2bff157ffc66dbece813615e069b73995c59f33cf97c35642051`。本题没有为取得全通过再跑。

评审前按已补开发文档做禁网载荷核对：固定官方模拟数据来源、`_input()` 身份/清理/账目和配置秘密缺席均通过，仅对 adapter 材料/提示发一次评审。审计覆盖发送端同一 canonical HTTP 消息正文（不含认证 header），字节数/hash与workspace对象分别记录；t013为208,652 bytes、request SHA-256 `7f0c2b83496f244761a29cbabcedfb4e42234e083e398d5518a30a58784fb13d`。证据 `review-payload-audit-t013.json`，不把单次审计当全局审批豁免。

### t019：正常收尾，局部检查通过

29 次主请求/反馈加 1 次确认，全部 settled/工具 returned。确认在第 17 次请求正常 stop，input=57,696、output=8,982，费用 0.187248（已含 C 总额）。反馈从本次 1/之后 49，到本次 30/之后 20，均对应实际共享轮次；第 29 次声明完成，第 30 次最终回复。一次确认前的建案被 patient_confirmation_required 门禁拒绝，未调用业务后端；确认后只有目标患者 1 case/1 service_request/1 submission，case=submitted、intake=in_progress，其他患者业务实体为 0。确定性部分 **9/9**，DeepSeek 局部 **8/8 true**，尚无最终付款方批准或官方 reward。

capture manifest SHA-256 `5db09053ba889e792bb007b803f376254b66b630679897dad2c15a57966465a8`。评审前消息正文审计为243,515 bytes、request SHA-256 `8b5fb92c05acfa86ce66515e7722eb276f7b6b2e310980a54ced36b41a8246d6`，证据 `review-payload-audit-t019.json`；两份准备审计的正文/workspace hash 均与实际 settlement identity 完全一致。

### 全部工具调用

计数包括门禁返回拒绝的模型调用，不等于实际后端写入。B 各调用 smoke_lookup / smoke_transform 一次，review 不调用工具。两题 C 如下：

| 工具 | t013 | t019 |
| --- | ---: | ---: |
| auth.check_status | 3 | 2 |
| auth.finalize_provider_determination | 0 | 1 |
| auth.submit_authorization | 1 | 1 |
| cases.create_from_order | 1 | 2（1 次拒绝） |
| cases.get_case | 1 | 1 |
| cases.list_cases | 1 | 1 |
| chart.get_patient_chart_by_patient | 7 | 7 |
| chart.list_candidate_orders | 1 | 1 |
| chart.search_patients | 1 | 1 |
| docs.create_submission_bundle | 1 | 1 |
| docs.list_case_documents | 1 | 1 |
| docs.upload_evidence | 1 | 1 |
| forms.list_required_forms | 1 | 1 |
| forms.save_form_response | 1 | 1 |
| inbox.list_messages | 5 | 2 |
| local-claim_done | 1 | 1 |
| local-confirm-patient | 3 | 3 |
| local-fs-list | 3 | 6 |
| local-fs-read | 10 | 9 |
| local-fs-write | 0 | 1 |
| local-read-patient-observation | 0 | 3 |
| local-sleep | 3 | 0 |
| people.list_ordering_providers | 1 | 1 |
| 合计 | 47 | 48 |

复现沿用 README 的 Docker 函数，依次 `rebind-source` → `k-b-smoke --run-id o-b-20261028-001` → 各题 `c-run --task-id <固定任务ID> --run-id <表中C ID>`；每题结束后 `deterministic --input-dir runs/development-review-inputs/<C ID>` 和一次 `review --input-dir ... --review-id <表中review ID>`。本地包装为 `runs/request-budget-root/{live-control.sh,review-control.sh}`，没有为改进刷全通过追加尝试。

## 历史、反馈与费用对账

主代理独立对照初始 **29,561 文件**，只有 K accounting/controller/current-B 和 review accounting 四个允许指针变化，旧 B receipt 以原字节归档，旧费用、失败、claim、捕获和评审不变。所有新主请求的反馈均按已发送次数与此前已返回的声明记录重算，56 条全部一致；两次确认和 B 均不混入该反馈。提示正文可由固定版本格式器/hash 复现，原版重建 trace 的 base system prompt 不能代替每轮实际系统段的记录。

本轮 **63 个已计量请求**：B 3、两次 C 58（含确认 2）、review 2；**97 次工具调用，全部 returned**。本轮峰值保守估算 **18.585334 CNY**，全历史 K 306 settled + J prior 3 + review 10 = **319 个已计量请求**，累计 **102.493324 CNY**，非实际账单且不含 Codex 开发代理用量。两套 pending=null、controller clean，逐请求 tokens/费用、adoption prior、K 累计与 review receipts 对账一致。

按精确 Docker ID 只读复核 3 runner、2 world、2 network 全部不存在，不删除其他资源。当前源码两份 `_input()` 来源验证均通过，评审正文 hash 与发送身份匹配。脚本/结果为 `reconcile.py` / `final-reconciliation.json`；首次读取该审计脚本报不完整语法，核对落盘内容完整后重读运行通过，不涉及 participant 修改或额外 API。原始材料/秘密/手册/vendor/data 不上传。

## 结论与限制

工程层面，K C 的独立 50 次限制、SDK 同步、每次新鲜反馈与未知阻断已有固定快照/SDK 故障和真实请求证据。业务层面，两题都正常结束、只提交目标患者；t013 从 N 的总次数耗尽变为正常结束，但确定性检查从 9/9 变为 8/9，不能称任务整体更好。t019 保持正常结束及局部 9/9、8/8；局部 verdict 不能消除 t013 的确定性失败。

本轮 t013=28、t019=30，均没有发送第 31 次以后请求、没有触发低余额软提醒。50/51 次和软提醒边界只得到合成证据；真实结果不能证明额外额度有必要或阈值提示有效。增加上限、显示总数及完成流程提示一起改变，模型又有随机性，无单项因果/成功率结论。两题已成开发题，仍缺未见迁移验证。

N 最终 t013 为30请求/49工具/143.318秒/11.733784 CNY，本次28/47/312.140秒/9.332018；N t019 为28/42/246.040秒/11.003052，本次30/48/215.869秒/8.912194。用量/耗时变化不一致，且 N 总账含额外失败尝试，不能以阶段总费下降推断效率提升；动态系统段也可能影响前缀缓存，本轮没有真实账单或完整缓存成本测量。

下一项通用改进建议聚焦**申请关键字段的来源与提交前一致性核对**：记录/核对医嘱、病历、公开规则为服务类型/地点等字段提供的依据，以及服务请求、表单和证据包之间的一致性；不能把隐藏可接受值写成答案。先用多情境合成材料验证未支持/矛盾/缺失字段路径，再固定版本，用未参与调参的兼容任务检查迁移，同时保留患者门禁与预算约束。该建议未在本轮实施，避免继续只围绕已见 t013 调参。

official_reward=null，DeepSeek 语义确认/局部评审不等于独立临床或原版 Claude 判分。正式入口仍为原 record_only/null cap 配送准备，尚未接入本轮 K C 改进；Claude、F.5 最终冻结、真实硬取消/daemon 故障和 OpenSpec CLI 仍未补验。实现/文档通过 base=main PR 交用户审核，主代理不 merge/auto-merge。
