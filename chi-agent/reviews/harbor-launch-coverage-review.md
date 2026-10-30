# U：正式启动接入预演与三题评分覆盖

日期：2026-10-30（Asia/Shanghai）。范围见 [U 规格](../openspec/changes/harbor-launch-coverage/design.md)。真实组件、合成模型响应、真实模型任务、官方判分分别取证。本轮未重跑 t012/t014/t017。

## 基线、授权与实际环境

GitHub connector 实际确认 [PR #24](https://github.com/xsw932187210-cell/chi-agent/pull/24) closed/merged，merge commit 为 `fd140bd805e906aa95c6afc1a1e76ab813c441e7`。本次 fetch 后最新 origin/main 恰为同一提交，本地无未提交改动，从它建立 `codex/harbor-launch-coverage`。首次普通 fetch 受 `.git/FETCH_HEAD` 沙箱权限阻止，经已有授权的受审 Git 路径完成；没有把历史 merge SHA 自动当作当前 main。

用户恢复的是启动接入预演与现有评分覆盖盘点。固定清单为真实模型请求0、真实业务任务0、Claude0、Go付费临床评审0；后续三类代表题不在本轮。默认一个 Terra/high 实现者，主代理规格、独立审核、覆盖盘点、教学与 Git。所有下载/安装/运行/检查在 Docker；旧 SDK/PDF 卷只读，固定 vendor 不修改，G/H 不重做。最小新增依赖、版本/hash及平台边界只维护于U规格和 `requirements-harbor.lock`。

本地原始证据根为忽略的 `runs/harbor-launch-coverage-root/`：`implementation/` 保存实现者尝试；`operator-audit/` 保存主代理只读审计程序；`coverage/` 保存三题盘点与原字节清单。凭据、wheel/vendor、世界/expectations、完整rubric、模型轨迹和评分输入不上传 GitHub。

## A：实现与真实组件验证

**固定实现 `2c31a931f26ba70581ef4470fb83755037e0855c` 在本轮真实组件接入与合成启动场景中独立审核通过。** 以下区分代码修复、真实组件、合成模型和未验证的正式配送。原FakeHarness单测仅为单元证据。

真实源码与开发演练已揭示以下接点差异，均由同一实现者修复后继续验证：

- `Trial._run_agent_phase()`在调用run之前以`agent.extra_env`进入真实环境作用域；只在run内部临时清空内部字典已太晚。新适配器向Trial暴露空执行overlay，非秘密metadata仍在实例中；调用方已有执行overlay/host凭据污染先拒绝，Go Key仅运行时逐次注入。
- Harbor会保存TrialConfig；因此Key不得经`AgentConfig.env`/extra_env或`--ae KEY=value`进入配置。演练用控制进程的专用合成Key，测试结束恢复；不会读取真实.env。
- 适配器在读取Key前通过真实环境执行同解释器的无Key包预检。原版父`_exec()`会把原stdout/stderr写debug，适配器改用真实环境exec并只保存字节数/hash/固定状态与安全码，不记录原输出。没有替换真实环境、Trial或工厂。
- 原薄适配器无条件提供三个tool-reference候选。实际世界entrypoint运行前后的路径形态不同：旧别名的父目录是链接，启动后标准asset文件本身也成为任务目录的符号链接；shell的`-f`会跟随，而runner完整路径检查会拒绝。适配器只传普通候选，预演调用方另把所选世界的公开参考供应到允许的`/input/tool_reference.md`普通文件并留身份；不放宽runner路径门禁，不复制隐藏评分材料。该供应hook属于操作者输入职责，不冒称生产适配器自动处理任意链接。
- `SingleStepTrial._sync_agent_output()`先下载日志，再对空context调用post-run钩子；原父类容忍缺失/损坏日志，成功进程码不足以证明有效结果。新钩子需严格检查结果、输出与trace，并保留runner主错。

控制侧用真实`harbor==0.20.0`的工厂、BaseInstalledAgent、AgentContext/ExecResult、SingleStepTrial和固定官方ChiBenchDockerEnvironment；最小overlay不声称安装了Harbor所有可选CLI/服务依赖。真实环境需要docker CLI，故只隔离增加固定Linux客户端。world使用原固定镜像的本地测试衍生层提供独立包/原SDK/PDF/vendor与测试HTTP边界，不作为配送包。

演练前置失败全部保留：默认Python缺pip、误写本地镜像名称触发拉取后中止、缺Docker CLI、Trial导入链的缺失依赖、合成task.toml格式不符、解释器shim拦截官方`-m/-c`健康检查、保存B状态的测试镜像继承临时CMD、tool-reference符号链接被安全门禁拒绝。原stdout不落盘的失败另保留哈希/安全诊断。它们是启动/测试工程失败，不是临床决策失败；没有真实模型请求或把失败计成reward=0。

主代理首审固定包`734a70ad…`（harness源SHA256 `59e73994d1c38b9b25a576b49f1aef1ece1c55ca3ee1ddb5da52e71ad6f040ea`）后交回同一实现者修正三项：测试driver笼统吞掉Trial异常，可能掩盖非预期恢复/清理错；日志校验接受只有user行的trace及缺少/异常metrics，父钩子仍可能静默不产trajectory；真实ATIF总量为3/2而run_result/context为6/4，原因是官方trace的ToolCallItem没有usage，父类只累计有usage的step。修正限于自有adapter/测试：严格契约与异常断言、真实类型校验，trajectory最终量取已验证全部已结算请求总量，缓存/费用未知保留null；未修改官方writer、评分器或旧结果。

### 固定候选与主代理独立复验

Terra完成返工，Docker目标检查11项及真实旧成功trace的临时副本检查通过，日志分别为 `implementation/review-r1-r3-tests-02.log`、`review-r3-real-trace.log`。子代理在最后收束回合返回额度限制；主代理未更换实现模型，核对已留下的完整返工代码并完成独立审核。主代理仅清理测试文件末尾空行、维护文档及Git，没有另一个实现写入者。

固定候选后从Git archive提取独立源码，并本地Git克隆同SHA的固定vendor；原项目源码目录不挂给预演controller或runner。控制侧8项最小overlay在全新目录按hash/no-deps安装，Docker客户端从同一已下载归档按固定hash独立提取；旧SDK/PDF只读复用，逐字段/source hash与T原身份相同。Python3.12.15/Linux aarch64，Harbor0.20.0、Docker客户端28.5.2、实际引擎29.5.3。

最终包仍31个allowlisted文件，manifest为 `8fcee0a7a40043784eb1ab802e7be2941a1a78b0de5911f6bb73bce83b73a64c`；运行身份为 `47c42fedf3f3d005018de28b6897f90981065db36458394a5ede33e0c078a2a0`。harness源码SHA256为 `12fb0d5dce724838f0546cf5b16cabb34931b32123ba477a5dbc4c89f0906239`，新增控制锁SHA256为 `c73a6836248549abf86afa9a4f1e5c7434ec2341d4f9654fe9a141be6b3ef4d2`。本轮没有把真实旧账迁移到新身份，也没有新真实B收据；后续真实运行须按该阶段的身份/门禁另行准备。

| 主代理独立检查 | 实际结果与证据 |
| --- | --- |
| 禁网全量回归 | **449 passed、3 skipped、203 subtests（19.94秒）**，含已安装真实Harbor overlay的类型/工厂/作用域及日志负例；`independent/all-tests-2.log` |
| controller补验 | 原dev缺Docker SDK而跳过的3项在controller内通过（0.004秒）；`independent/controller-tests.log`。中途口头“4项”为计数口误，以该日志为准 |
| 全新独立测试镜像/B | 从候选快照导出新包，复用原SDK/PDF/source，禁网下实际entry/SDK/guard自然完成3响应coding-B并生成receipt/seal；显式核对ExitCode及B产物再commit测试镜像，恢复原ENTRYPOINT/CMD；`independent/prepare.log`，新seed镜像 `4de98394322f…` |
| 正常真实SingleStepTrial | 无Key预检成功，2次合成HTTP驱动真实provider只读工具与最终回复；context/run_result/真实类型trajectory均6/4，cache/cost均null，无异常、verifier=null；`independent/trial-success.log` |
| 非零退出 | 测试shim以23退出，Trial精确记录`chi_runner_failed`，未发任务合成HTTP，不把空context当成功；`independent/trial-runner-nonzero.log` |
| 破损trace | 实际runner完成2次合成HTTP后由测试shim损坏trace，Trial精确记录`chi_runner_logs_invalid`；仅允许该已记录主错在真实recovery中再次抛出，其他异常均使driver失败；`independent/trial-corrupt-trace.log` |
| 输入/角色/日志/清理 | 原instruction与trace逐字一致；每场真实三角色各一次只读MCP，共9次探针调用，加两场模型驱动的provider工具调用；公开参考来源/3021字节/hash可核对。三场finish/result持久化、state/wire/seal、Key缺席及精确owned容器不存在均独立核验 |
| 最终包与历史 | `independent/final-audit.json`逐项核对新包来源、SDK/PDF/vendor不变，3个synthetic namespace完整审计，原Q/CHI来源与留档链复验、604个旧文件仍原字节。有效pending/halt=null，唯一旧未知仍未结算 |

主审独立模型HTTP共**7次合成响应**（自然B3 + 正常2 + 非零0 + 破损2）。各场state包含同候选B种子，不能把复制的B再次累计成新请求；这些合成tokens/USD都不进入真实Go历史或费用。所有真实推理、临床任务、Claude/Go付费评审仍为0。

主审另保留两项启动故障：Docker socket一度不存在，启动已有Docker Desktop后恢复，没有安装或改Docker配置；首次禁网测试在进程启动前因只读快照缺空data挂载点退出125，补空目录后重验。原日志为 `independent/cli-verify.log`、`all-tests.log`，后续成功日志分别带新编号，没有覆盖失败或把它计成业务失败。

### 此处通过了哪一层

真实调用链为 `Trial.create()` → 真实AgentFactory载入包内`GoChiHarness` → 真实官方Docker环境start/setup → adapter无Key preflight → 真实environment.exec启动包内`go_chi_entry live` → `run_chi`/SDK/ChiGuard/真实MCP → 原日志下载 → 严格post-run hook/真实Harbor trajectory → 原Trial finalize/stop。角色探针、普通公开输入供应和删除前state下载是测试操作者hooks；没有patch工厂、Trial、环境exec、SDK守卫或B收据。HTTP响应及两条故障为明确的test-only shim，测试代码未进入参赛包。

这证明了固定平台上的真实Harbor组件启动接点及异常/收尾，**没有执行官方CLI/stock注册选择、通过Harbor的真实Go推理、真实judge或最终配送**。固定世界/依赖/包在预演前由调用方供应，`install()`仍不自动安装；生产资源供应和外部持久状态闭环仍属F.5。真实取消/超时只有受控单元边界检查，本轮未把daemon短暂缺席冒充在途硬故障/硬取消测试。完整配送、官方判分与业务稳定性不因此通过。

## B：三题原终态及历史的只读核验

使用 T 的 `t-go-fee-c-t012-20261030-001`、`t-go-fee-c-t014-20261030-001`、`t-go-fee-c-t017-20261030-001` 原结果。Docker禁网、项目/原历史只读挂载、输出仅在新的 `coverage/`。核对冻结配置hash、每题资源identity、初末capture manifest、export/expectations/world hash、四份资源快照、attempt/已结算请求、runner退出、捕获和清理；重新调用官方纯程序检查，结果与原orchestration逐项相同。无新世界、无模型、无判分、无旧结果改写。

复用现行 Q `_validate()` / `_audit_runs()` 及 CHI `inspect_history()` 完整审计原账、source transitions、wire/seal和唯一 acknowledgement 链；原锁以只读 fd 持有，避免构造器尝试写入原锁/目录。主账仍为 `3814a9452869ef36e5be93c3fdc051348be6909741be4125c02e4181630bb362`，唯一旧 S 第9请求仍未结算、留档完整，有效 pending/halt=null。没有再次 acknowledge、settle、rebind 或重发。历史USD完整性继续保留未知，不与native CNY合并。

两次字节快照证明本次核对的 **604个文件**（Q/CHI历史、T三题/探针结果目录及两份native主账）前后相同；清单在 `coverage/historical-byte-manifest.json`。这次604文件范围与T原49,544文件/30链接保留审计不同，不能把较小范围说成重新验证了所有旧目录。旧大范围证据仍见[T报告](go-chi-timeout-recovery-review.md#pr费用反馈修订2026-10-30)。完整输出为 `coverage/coverage.json`。另外用Docker SDK只读查询三题原runner/world/network的精确ID，九个资源全部已不存在；记录在 `coverage/existing-cleanup.json`，未清理或操作其他资源。

首轮盘点程序错误地假设每题都有超过2项rubric，在只读断言处停止；保留 `coverage/attempt-1.log`。随后核对固定expectations与官方 `PaUmJudgeAdapter._build_rubrics_contract_v5()`，改成检查实际baked条目数加2项提交内容rubric；第二轮通过，日志 `coverage/attempt-2.log`。此失败暴露了实际覆盖差异，没有修改任务、结果或评分器。

## 已验证、未验证与不适用

三题均为 `provider_new_referral` / provider / `contract_v5`，显式阶段为 `new_referral`、`provider_pre_submission`，另始终执行cross-stage。下表的“程序检查”是固定官方函数的适用部分，“内容rubric”尚未执行模型评审，二者不能相互换算。

| 原任务 | 已验证的适用程序检查 | 程序不适用 | 固定资源生成的内容rubric | 本轮内容评审 |
| --- | --- | --- | --- | --- |
| t012 | 8/8 | 1 | 2项提交内容；baked临床证据列表为空 | 2项均未验证 |
| t014 | 8/8 | 1 | 2项提交内容；baked临床证据列表为空 | 2项均未验证 |
| t017 | 9/9 | 0 | 4项证据 + 2项提交内容 | 6项均未验证 |

已验证的8个共同程序项为：唯一匹配的ServiceRequest、procedure code、所需diagnosis codes、service type、site of service、目标案件创建、目标案件状态、forward transitions。t017另验证所要求的文档种类存在。源码为 `verifier/stages/new_referral.py`、`provider_pre_submission.py`、`cross_stage.py`，调度入口为 `verifier/task_runtime.py::collect_all_verifier_checks(include_semantic_judge=False)`。

程序不适用的确切项是 `provider_pre_submission.required_documents_present`：t012/t014的固定 `required_document_kinds=[]`，官方分支显式返回not_applicable。t017该列表非空且检查为true。payer intake/triage、nurse/MD review、P2P、outcome、appeal、e2e及CM检查在这三题的显式任务阶段外；其未执行由任务范围决定，不能当作失败，也不能当作已通过其他角色。adapter输出中存在同名空stage结构不代表那些阶段已执行。

额外本地资源归属审计对全部provider/payer资源表逐条语义比对，重现T的27/24/28条变更均关联目标患者，无非目标/归属不明/混合变更。该证据补足目标export不能证明非目标未变的盲点，但它是自有资源审计，不能冒充官方rubric。原业务终态仍submitted/in_progress，不等于临床批准或最终付款方裁决。

未验证的内容项由固定 `judge/pa_um_adapter.py` 和 `judge/sanitization.py` 生成：三题各2项提交内容rubric分别考察ServiceRequest与病历的临床一致性、LMN/表单叙述是否限于真实记录；t017另4项临床证据rubric。所有10项仍待模型评审，材料存在不能推定其内容正确。t012/t014空baked证据列表触发官方submission-only回退；这表示固定数据/评分契约此处未覆盖独立证据rubric，不能把临床完整性记为不适用、已验证或推断不存在临床要求。未自行补写/移植其他题的隐藏要求。

官方 `collect_all_verifier_checks()` 默认还要经 `PaUmJudgeAdapter.build()` → `WorkspaceJudge.judge()` → `judge.<rubric_id>` verdict合并，再由 `verify_task()` / `build_scorecard()` 聚合。三题均eligible且 `should_run_workspace_judge=True`；这次只调用禁用semantic的纯检查，没有执行judge或聚合。若把局部checks直接交给聚合器，可能得到局部全过的数字，也不能当作官方reward；本轮不生成该伪分数。official_reward保持null。

## 评分材料就绪与下一步

另一次Docker禁网检查用manifest校验的捕获world为官方adapter提供只读world lookup，禁用无关本地bundle/policy发现，三题均成功构建官方judge input；原病历文档/证据索引可读且只关联目标。source evidence条目分别4/4/5，source files为6/6/7。它们是评审输入可用性，不是任何临床verdict。完整材料和来源hash只在本地 `coverage/materials.json`，不进入runner包。

盘点也检查了旧native开发评审helper的纯输入构建函数 `development_review._build()`，没有进入发送端：t012/t014因其额外“baked evidence必须非空”前置条件返回 `rubrics_invalid`，而官方adapter可以构建2项submission-only输入；t017可构建19文件/6rubric的输入。这是将来恢复开发评审时需先离线修正或明确绕开该旧helper的兼容缺口，本轮不扩大修改、不用付费调用试错。不能据此说t012/t014模型评审失败，也不能说Go评审已接线。

本轮盘点得出的后续验证需求为：

1. 当前三题缺少10项实际内容verdict；若恢复评审，先明确使用原版Claude判分还是独立开发评审，分别保存原结果和非官方标签，不重跑业务任务。当前二者仍暂停。
2. t012/t014的证据rubric覆盖缺口来自固定资源，要在后续规格中明确如何取得合规的内容评估证据；不能自造官方评分项或把空列表当临床通过。旧helper的前置兼容先离线处理。
3. 后续再以公开元数据冻结医院侧另一类流程、payer和CM各1题；这些用于覆盖不同流程/角色，不会自动解决既有临床verdict缺口，也不在本轮调用清单。
4. 稳定性仍需固定条件、保留失败的小批量证据；当前两道未见题仅提供有限迁移样本，没有重复性统计、全赛道泛化、临床批准或官方成绩。

## 用量与交付边界

本轮实际模型调用与模型费用均无新增；没有消耗订阅额度来增加实验数量。历史费用/null/warning、一个旧未知及三项USD口径全部保留，订阅固定费另计，不与CNY相加。Go非编码用途仍无官方明确确认，用户知悉并授权开发；不声称百万token实测，十一月隐私按实际日期人工复核。

README、包内runbook、OpenSpec、学习账本及唯一REVIEW_STATE按职责更新；所有真实与合成原始轨迹留在忽略目录。F.5最终冻结、对外配送、原版Claude判分和Go付费临床评审继续暂停；不操作Antigravity、不新增后台轮询/自动唤醒。完成分支提交/推送和base=main PR后交用户审核合并。

显式上传清单为17项源码、测试、锁和职责文档，Docker内检查UTF8/大小/常见凭据模式/本地链接，未读取.env，不包含world、rubric原文、轨迹、vendor、wheel或测试镜像。首次只挂项目子目录导致父COLLABORATION链接不可见，保留`independent/upload-audit.log`；只读按真实仓库布局重验通过，见`upload-audit-2.log`及元数据清单。
