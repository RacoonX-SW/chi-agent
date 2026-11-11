# 患者确认与绑定独立审核及开发回归

日期：2026-10-28（Asia/Shanghai）。基线为 PR #17 合并提交 `2b29a69dd9628586daa9481b11af6b8223b0b079`，GitHub 和 fetch 后 origin/main 均已核对，工作分支 `codex/patient-identity-binding`。一个 gpt-6.1-terra/high 实现并 Docker 自测，主代理冻结规格、独立审核、真实回归、教学和 GitHub。最终实现 `77c25b0` 离线独立通过，t019 正常完成且没有错患者副作用，t013 目标已提交但总请求耗尽；不是两题全通过或跨任务能力证明。

## 问题与有界方案

[M 基线](provider-two-task-baseline-review.md) 的 t019 先向非目标患者提交，随后才向目标患者提交，并达到轮数上限；目标案件局部程序检查/DeepSeek rubric 仍全 true。N 因此优先解决首次选择和后续跨患者副作用，不同时改上下文或增加轮数。

新机制由公开 observation registry、同 provider 的无工具语义确认以及程序化身份/实体/路径门禁组成。确认只使用完整公开 instruction、实际完整未过滤 roster 和已观察 chart；同 sex、DOB 年相差不超过 1 的年龄近邻先要求完整 chart。语义确认仍有模型偏差，不能用存在的引文证明任意医学语义正确；程序的确定范围是来源、完整性、候选集合、绑定和已观察实体关系。

确认复用现有 AsyncOpenAI/GuardedTransport/RealDevelopmentJournal，最多两次，计入同一 30 次 provider 请求与零重试。初始确认输出 8192；N-R2 根据真实失败仅将受控确认角色改为 32768，业务单次输出仍 8192。新增通用工具说明、确认 prompt 和该角色边界是机制变量，官方 base system prompt 和其他 profile/资源配置保持；不是“所有提示/执行参数未改”的比较。仅 K 自主 C 启用，正式入口/Claude/F.5 不在本轮恢复。

范围与验证契约见 [N 设计](../openspec/changes/provider-patient-binding/design.md)。原两题现为开发回归题，不作为新的未见任务泛化证据。每题新世界、独立 attempt、完整终态、确定性部分检查和原配置 DeepSeek 开发评审；旧结果和失败不改写，未知用量阻挡后续调用。

## 环境与历史基线

复用 M 的 Linux arm64 / Python 3.12 dev、controller、world 镜像和 H SDK / K PDF 卷，原依赖锁和任务资源不改，不安装或下载新依赖/任务。所有安装、调试、测试与运行均在 Docker，宿主机只用于编辑/Git/Docker。

运行前建立旧 24,304 个文件的 SHA-256 清单，K 与 review 均 pending=null、controller clean；历史累计峰值估算为 47.756786 CNY。指纹与数字在忽略的 `runs/patient-binding-root/prior-files.json`，后续对照不重置旧费用/claim。2026-10-28 只读复核 [DeepSeek 官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，继续使用既有峰值未命中输入 2 / 输出 8 CNY 每百万 tokens，估算不等于账单。

## 固定候选与主代理独立审核

固定候选 `284a5249a752fd0ead8b9cb37268653558f8f81c`。主代理从 Git archive 导出只读快照，以无网络、无凭据、无 Docker socket、空 data/runs 的 Python 3.12 dev 容器独立运行完整回归：303 tests / 143 subtests 通过。测试包含真实 SDK 与固定官方主循环的 8 请求合成成功链：roster→近邻 chart→单独确认→同客户端/transport/journal 的无工具子请求→建案/表单写入→完成，以及混合确认/写入在实际后端前拒绝。没有改旧测试来假装“全部拒绝就是成功”。

主代理另用自造三个候选及实体关系做 21 项独立检查，覆盖未确认写入、过滤/单页名单、未见年龄近邻、roster/chart 人口属性冲突、被截断证据/伪造分块、unknown/重复候选、伪造 task 或跨患者 chart 引文、歧义/两次上限、跨患者/未知 order、case、source document、form 与工具、合法同患者源材料、共享 form 模板按 case 配对、返回身份冲突后封锁。21/21 通过。

另仅回放 M 原始日志中已向 Agent 提供的公开 MCP 查询及其真实可见格式，不使用 expectations 或隐藏目标。两份 65 人完整名单均被识别，t013 的 5 个、t019 的 7 个已见 chart 都能验证可见性；t013 的旧观察未覆盖全部年龄近邻，因此预检拒绝并要求补查，t019 已观察集合可构建确认输入。该回放验证格式/完整性机制，不等于真实模型已经选对患者。

首候选实现：新增 `scripts/patient_identity_binding.py`，在 `live_development.py` 的响应批校验、MCP 最终派发、原始结果登记及 local workspace 写/edit 接入；受控 observation 分块回读避免扩大文件权限。确认使用同一个 client，purpose 与 provider round、prompt/evidence hash、原始结果和绑定/拒绝事件存 run journal。首候选的 `b_provider_transport.py` 仅将 reserve 后 observer 纳入异常边界，并补 CancelledError；未知保留 pending，响应使用量已经结算后取消不改成未知，不改变路由/价格/重试。后续 R2 的角色预算/元数据改动见下文。

独立证据在 `runs/patient-binding-root/evidence/candidate-1/{pytest.log,independent.json,public-replay.json}`，主代理脚本为同根 `check_independent.py` / `replay_public_observations.py`。实际运行前逐文件核对 participant 与快照一致，profile/base system prompt/镜像均与 M 一致，记录在 `experiment.json`。新确认 prompt SHA-256 为 `db97f01e14979855773b448b6cb0fc6d5ccf72d5a3c25eb5ae006f8756549287`，协议版本 `patient-binding-public-observations-v1`。

首轮真实反馈发现 N-R1：提示“每个 candidate chart”未明确要求覆盖整个 roster，确认器两次都只返回已见 8 人，而程序要求 65 人；笼统 invalid_confirmation 反馈不足以纠正。首笔另有一条 chart 引文在序列化源和字符串叶子均不存在，程序拒绝正确，未为通过放宽引用。两次语义选择都指向目标患者，不代表协议和证据已合格。

同一 Terra 仅修确认协议/反馈与针对性测试，固定第二候选 `e1444e88ebf547d3f43da6479c76b72f83b67ac9`：v2 显式给完整 ID 列表/数量，要求 matches/mismatches/unknown 三数组严格分区，覆盖、重复/交集、未知、选择不一致和引文错误分别反馈。主代理从新只读快照、空 data/runs 独立通过 304 tests / 143 subtests 和 23 项自造故障检查，新增精确复现 65 人仅报 8 人必须返回 missing=57，以及选择他人不自动绑定。证据 `evidence/candidate-2/{pytest.log,independent.json}`。

v2 不改模型、输出/轮数、确认次数、依赖或引文门禁。实际使用前核对 source 与快照一致，重做必要 B，旧 B/失败 C/失败评审的 1,314 个文件另存指纹，在 `first-attempt-files.json`；旧实验身份保存 `experiment-284a524.json`，修复后为 `experiment-e1444e8.json`。v2 确认提示 SHA-256 `4b9bbf6d989ed037d57734b95ecfe57275cc8858a67d6bfc677a928449972218`。后续运行不是重复旧 claim，也不删掉失败求全通过。

第二次 t013 在第 9 次 provider 请求（首次付费确认）后失败；该请求 input=44,233、output=8,192，usage 已结算，传输校验返回 `response_invalid`，SDK/工具外层显示 Connection error。旧日志没有保存 finish_reason，无法确定实际终止原因或断言输出全部用于思考，更不能据这一文字诊断网络故障。N-R2 明确记录这项证据限制，并修订角色预算/反馈契约；不改 base profile 或全局放宽上限。第二次 B/C/review 的另 1,314 文件先冻结于 `second-attempt-files.json`，两套账目 pending=null 后才继续实现。

第二次失败评审曾被自动审批以“可能真实患者/临床敏感数据”拒绝，未执行请求/创建 claim。主代理先在无网络 Docker 校验精确载荷来源及配置秘密缺席，固定官方源码 `docs/kaggle-challenge-overview.md:13` / `competition-rules-draft.md:75` 明确只含模拟患者、无真实患者数据或 PHI。载荷 16 文件/48,776 bytes，仅 adapter 生成的基准材料；携用户明确 DeepSeek 开发评审授权与核对证据重新获批后才执行。没有换目的地、绕过审查或发送秘密，证据 `review-payload-audit.json`。

N-R2 最终候选 `77c25b04216bc492ed9cc25196abb2cf019d01ea`：K C 内部 ContextVar 仅为源代码构造、材料 hash 一致的精确无工具请求授予 32768；其余请求仍按原 profile。pending 必须同时为 K、purpose=patient_confirmation、整数 32768 和有界 wire；旧结构仍按原界。确认 usage 和安全 response_metadata 先写逐请求 journal，再清 aggregate pending；故障注入验证两次写入之间崩溃仍有磁盘 pending，不自动恢复。合法 usage 的 length/空/格式错误在工具层返回具体 refusal，保持未绑定，不再由传输异常误报网络故障。

主代理首读 R2 差异发现响应绕过普通业务校验后遗漏 assistant 角色核对，同一 Terra 补齐 role 与 deprecated function_call 拒绝；没有增加第二实现者。固定最终 Git archive 在禁网、只读、无凭据/socket、空 data/runs 的 dev 容器独立通过 **316 tests / 143 subtests**、原 23 项身份/实体注入，以及主代理另外编写的 8 项 SDK 检查（可信角色/精确 wire/恢复主上限、length/空/无效 JSON/错误或缺失 role/函数调用/tool_calls），每项均验证已结算、未绑定、无自动重试和显式第二次确认可成功。官方循环合成链还验证错误响应时业务写后端为 0，以及正常绑定后能建案/保存表单。

独立执行首次因只读 archive 缺空挂载点而未启动容器；补齐空目录后才运行测试。主代理 SDK 脚本首次漏登记 validated dispatch，被真实 journal 正确拒绝；补齐夹具派发身份后 8/8，未放宽生产门禁或关闭 journal。这些审核夹具问题与真实 C 失败分别保留。证据 `evidence/candidate-3/{pytest.log,independent.json,confirmation.json}`、脚本 `check_confirmation.py`，实验 `experiment-77c25b0.json`。

实际调用链在 `live_development._worker_run()` 为 K C 建立 PatientBinding：MCP 原始成功结果由派发监控交 `observe()` 登记，普通模型看到的截断内容由 `_visible()` / observation 分块回读核对。`_live_tools()` 的确认回调调用 `confirmation_input()` 预检，再经同一 AsyncOpenAI → GuardedTransport → RealDevelopmentJournal 发送/结算；SDK 响应经格式和 `assess()` 的候选/引文校验后才绑定。之后每次派发和文件写入在共享锁内复查 `check()` 的归属，返回身份冲突则封锁。终态由原 `_capture_review_input()` 保存，评审侧独立核对，不把隐藏目标回灌这条 participant 链。语义是否合理、程序是否按约束执行、任务是否正常完成是三份不同证据。

## 全部真实尝试与完整世界对照

全部已发生尝试均记录，后续候选另列，不把失败抹去。tokens 为 provider 的 input/output（包含所报告的生成用量）；费用用峰值保守公式估算，不等于缓存折扣后的账单。

| attempt | 源码 | 结果 | provider 请求 | 工具调用 | input / output tokens | 耗时秒 | 估算 CNY |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `n-b-20261028-001` | `284a524` | smoke_completed | 3 | 2 | 4,923 / 176 | 4.245 | 0.011254 |
| `n-c-t013-20261028-001` | `284a524` | runner_failed，30 次请求耗尽，未绑定 | 30（含确认 2） | 49 | 5,857,146 / 38,373 | 244.208 | 12.021276 |
| `n-review-t013-20261028-001` | 同捕获 | incomplete / verdicts_invalid | 1 | 0 | 16,435 / 2,270 | 10.829 | 0.051030 |
| `n-b-20261028-002` | `e1444e8` | smoke_completed | 3 | 2 | 4,893 / 164 | 3.529 | 0.011098 |
| `n-c-t013-20261028-002` | `e1444e8` | runner_failed / response_invalid，未绑定 | 9（含确认 1） | 17（16 returned，1 unknown） | 423,249 / 12,407 | 66.897 | 0.945754 |
| `n-review-t013-20261028-002` | 同捕获 | incomplete / verdicts_invalid | 1 | 0 | 15,967 / 1,727 | 7.639 | 0.045750 |
| `n-b-20261028-003` | `77c25b0` | smoke_completed | 3 | 2 | 4,895 / 181 | 3.802 | 0.011238 |
| `n-c-t013-20261028-003` | `77c25b0` | runner_failed，总请求耗尽；目标已提交 | 30（含确认 1） | 49 | 5,762,188 / 26,176 | 143.318 | 11.733784 |
| `n-review-t013-20261028-003` | 同捕获 | complete，目标局部 4/4 | 1 | 0 | 51,870 / 5,314 | 25.062 | 0.146252 |
| `n-c-t019-20261028-001` | `77c25b0` | completed_ungraded，目标已提交 | 28（含确认 1） | 42 | 5,345,654 / 38,968 | 246.040 | 11.003052 |
| `n-review-t019-20261028-001` | 同捕获 | complete，目标局部 8/8 | 1 | 0 | 62,474 / 5,721 | 23.780 | 0.170716 |

前两次 C 完整终态均为 0 case/service_request/submission，确定性部分检查均 0/9，DeepSeek 没有合格逐项 verdict；不能称业务成功或改进有效。C1 的 49 工具调用均 returned，但真实 create_from_order 被门禁拒绝；C2 的 unknown 是确认本地工具未正常返回，9 个已发模型请求均 settled，不是未知用量。C1 两次确认费合计 0.283458，C2 为 0.154002，均已包含 C 行总额。

耗时口径：B 为说明材料生成至清理结束；C 为 claim 落盘至清理结束；review 为目录创建至结果写出，均排除此前准备，不代表整轮开发耗时。安全汇总 `actual-summary.json`，完整日志/终态/评审/结算保留在既有忽略目录，不上传原文。

最终源码 t013：第 11 次 provider 请求为有效确认，input=44,269、output=7,695、finish_reason=stop，费用 0.150098（已含 C 总额）。该实际输出低于原 8192，因此不能将本次有效确认单独归因于提高上限。主循环占 29 次，确认占 1 次，下一请求被总 30 次门禁拒绝，保留 runner_failed/round_or_history_invalid；没有增加轮数或再跑同题求正常退出。

其完整导出只有目标患者的 1 个 case、1 个 service_request、1 个 submission，case=submitted、intake=in_progress；provider determination/问卷/状态转换亦可沿 case 归到目标患者，其他患者业务实体为 0，确认绑定 hash 在结束后 grader 侧核对目标为 true。部分确定性 9/9、DeepSeek 局部 4/4 true，但 runner 未正常结束，故不记完整任务成功。capture manifest SHA-256 `3b81fb0c7285408224eb14d9d194883ca5d8922990afd145f4fcc11f8140eda9`，`terminal-comparison.json` 保存全业务集合的数量/归属对照；只读 audit 不算错误业务写入。

最终源码 t019：同一源码/模型/提示/配置，首次付费确认在第 8 次请求正常 stop，input=57,655、output=13,772，费用 0.225486（已含 C 总额）；实际使用超过旧 8192，但不能用单次运行估计成功率。27 次主请求加 1 次确认后正常退出，工具均 returned。完整终态为目标患者 1 case/1 service_request/1 submission，case=submitted、intake=in_progress，问卷/阶段轨迹/状态转换都归到目标案件，其他患者业务实体为 0。绑定与隐藏目标的匹配只在运行结束后核对；部分确定性 9/9、DeepSeek 局部 8/8 true。capture manifest SHA-256 `a313912f918b993739fc4a5247b0b838afb0af2cf082c4749639badd86e09a10`。付款方尚无最终 determination，不称最终批准。

工具计数包含门禁前拒绝的模型调用，不等于后端实际副作用。三个 B 各有 smoke_lookup / smoke_transform 各 1 次；四次 review 都无工具。四个 C 的逐工具计数如下（按发生顺序编号 C1=t013-001、C2=t013-002、C3=t013-003、C4=t019-001）：

| 工具 | C1 | C2 | C3 | C4 |
| --- | ---: | ---: | ---: | ---: |
| chart.search_patients | 3 | 1 | 2 | 2 |
| chart.get_patient_chart_by_patient | 8 | 7 | 7 | 7 |
| chart.list_candidate_orders | 0 | 0 | 1 | 0 |
| cases.list_cases | 0 | 0 | 1 | 1 |
| cases.create_from_order | 1（拒绝） | 0 | 1 | 1 |
| cases.get_case | 0 | 0 | 1 | 2 |
| people.list_ordering_providers | 1 | 0 | 1 | 1 |
| forms.list_required_forms | 0 | 0 | 1 | 1 |
| forms.save_form_response | 0 | 0 | 1 | 1 |
| forms.validate_form | 0 | 0 | 1 | 0 |
| docs.upload_evidence | 0 | 0 | 1 | 1 |
| docs.list_case_documents | 0 | 0 | 1 | 2 |
| docs.create_submission_bundle | 0 | 0 | 1 | 1 |
| auth.submit_authorization | 0 | 0 | 1 | 1 |
| auth.check_status | 0 | 0 | 1 | 4 |
| auth.finalize_provider_determination | 0 | 0 | 1 | 0 |
| inbox.list_messages | 0 | 0 | 2 | 2 |
| local-confirm-patient | 8 | 3 | 3 | 1 |
| local-read-patient-observation | 8 | 0 | 0 | 0 |
| local-fs-list | 7 | 2 | 10 | 3 |
| local-fs-read | 11 | 4 | 11 | 8 |
| local-sleep | 2 | 0 | 0 | 2 |
| local-claim_done | 0 | 0 | 0 | 1 |
| 合计 | 49 | 17 | 49 | 42 |

复现使用 README 的 Docker 函数，依次 `rebind-source`、`k-b-smoke --run-id n-b-20261028-003`，然后两题 `c-run --task-id <固定任务ID> --run-id <上表ID>`；每个 C 后 `deterministic --input-dir runs/development-review-inputs/<ID>` 与 `review --input-dir ... --review-id <上表评审ID>`。本地包装仅复用已有镜像/挂载，位于 `runs/patient-binding-root/{live-control.sh,review-control.sh}`；没有新增依赖、下载或重做 G/H。

## 历史、计量与清理对账

主代理独立核对起始 24,304 文件只改变四个允许的聚合/当前 B 指针；两轮修复前额外冻结的各 1,314 文件全部字节不变，旧 B receipt 均以原字节归档。原始失败、claim、捕获、评审和旧费用未删除。旧 source 的捕获使用变更前已经通过的输入校验、不可变指纹及本轮独立来源核对；不伪装成它们仍满足当前源码身份。最终源码两份捕获重新通过当前 `_input()` 全校验。

本轮 **110 个已计量请求**：3 个 B 共 9、4 个 C 共 97（包括 5 个确认）、4 个 review；**163 次工具调用**，162 returned、C2 的 1 次本地确认 unknown。所有模型请求使用量均已结算，本轮峰值保守估算 **36.151204 CNY**。K 全历史 245 settled，加 J prior 3 和 review 全历史 8，共累计 256 个已计量请求、**83.907990 CNY**；不是实际账单，也不包含 Codex 开发代理用量。两套 pending=null、controller clean，逐请求 tokens/cost 与 adoption/累计费用及 review receipts 一致。

按精确 ID 用只读 Docker API 复核 7 个 runner、4 个 world、4 个 network 全部不存在；未按名字清理其他资源。对账脚本 `reconcile.py` / 结果 `final-reconciliation.json`。全部真实尝试/失败及原始材料继续留在忽略目录，不向 GitHub 上传；GitHub 存储边界未扩大。

## 结论与下一步

本轮完成通用门禁实现、独立离线审核、必要源码级 B 和原两题开发回归。M→最终 N 对照：t019 从“两个患者均提交且轮数失败”变为“仅目标患者提交且正常结束”；t013 从“正常结束且目标提交”变为“目标提交但总请求耗尽”。两题最终导出均无非目标患者业务实体，但只支持这两道已见开发题的观察，不能称跨任务可靠性已证、不能把前两次完全阻断当作任务能力提升。模型非确定，且机制同时引入确认提示/协议与角色预算，不能用单次费用/耗时差异作因果或统计结论。

下一项有界通用改进建议是**让业务 Agent 显式看到包含确认子请求的剩余请求数，改善完成收束时机**：t013 的业务循环仍可能按主 turns 规划，实际总次数先耗尽；t019 在相同上限内能正常结束。先合成验证剩余计数、拒绝/确认也计入、最后请求保留及未知阻断，保持同一模型、任务资源、30 次上限和患者门禁，再用已见题作开发回归；冻结改进后用未参与调参的兼容任务验证迁移。不在本轮增加次数、自动重跑或为某题写停止答案。重复状态查询和上下文增长留作后续独立变量。

official_reward 始终 null；DeepSeek 局部评审不是独立临床/规则裁决或原版 Claude 分数，最终付款方批准、未见任务、正式配送/F.5、真实硬取消/daemon 故障与 OpenSpec CLI 仍未补验。代码和文档经工作分支 PR 交用户审核；主代理未 merge 或启用 auto-merge。
