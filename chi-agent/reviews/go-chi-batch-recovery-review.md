# S：Go CHI 混批恢复与完整终态验证

日期：2026-10-29–30（Asia/Shanghai）。真实模型尝试均在 29 日；30 日完成离线收束。本轮按[有界规格](../openspec/changes/go-chi-batch-recovery/design.md)推进，工程/B 的通过不代替业务验收。

## 起点和范围

GitHub 实际核对 PR #22 closed/merged，合并提交 `575b6d1ae5d1f7944166e92a22ce33d3f9e46fc9`；fetch 后最新 origin/main 一致，旧分支干净，从该点建立 `codex/go-chi-batch-recovery`。R 失败/账目/原世界终态缺口保留，不追加开发到已合并分支。

用户批准上一轮提出的混批恢复、可靠捕获与账目接续方案，以及最多一个新 B、两次 t012 开发回归、两道预先冻结新题各一次。Go 额度按充足规划，不受 native 避峰限制；模型/共享50请求、零自动重试/回退、未知阻断、Extra Usage 关闭、USD/CNY 分账继续。Claude、Go 付费临床评审、t013/t019 和完整 Harbor/F.5 不在范围。

一个 `gpt-6.1-terra / high` 实现子代理先只读接点分析，收到完整规格后独占实现/测试/runbook，停写后由主代理固定候选并独立审核。主代理规格/独立审核/教学/Git；全部测试/运行在 Docker，已有引擎 29.5.3 / linux aarch64，不安装或改锁。

## 开发前冻结与旧证据

Docker 只按固定 tasks.jsonl 的五个兼容字段选择，排除原八题与 R 的 t012，从剩余四条取字典序前二，冻结 t014/t017；索引、规则和完整排除清单见 S 设计和忽略的 `runs/go-chi-batch-recovery-root/evidence/task-selection.json`。未读取 title/instruction excerpt/fixture 内容选题。仅从固定数据版本下载十个必要文件，约 10 秒完成，全部哈希和 provider/agent 服务元数据检查通过；不打印或交实现者/参赛 Agent 隐藏材料。

开始时保存旧 48,552 个文件与 30 个链接；两种 Key 仅检查存在，均为 true。用原只读 R 独立包完成旧 CHI/Q 全部请求、工具证据、seal 和 B receipt 审计，旧 CHI 主账原字节 SHA-256 `c6b69c6d73d6d507ae7f224625adfb9616d16675e9af984d7d935da8b1b52eb3`。旧两个 CHI attempts 的内容/失败/claim 保留，pending/halt=null；native 两账 pending=null。基线/旧账审计/资源预检均在 Docker 禁网且未调用模型，原始证据在本轮 evidence。

主代理发现固定 export 部分字段仅限目标案件，按源码补明确的运行前/后只读资源快照要求，避免将局部导出计数称为完整非目标审计。捕获器只保存资源；患者/案件归属和全量差异由主代理独立操作者脚本完成，不把控制器 complete 当作业务通过。

## 固定候选与实现

固定候选 `1f44ef564a5b4d8795b6f4fdd981cc78c5a68e01`；独立包 29 个 allowlisted 文件，manifest `3c1a91fe9554e9d84ddafef7f908759ee0643dcc37371c845905d6797610d637`，运行身份 `3b5098b55370620cbcf5d3420e0d190acdecffdd66d29b5498826852fa97a51d`。包位于忽略目录 `runs/go-chi-batch-recovery-root/exports/s-go-1f44ef5`，controller/snapshot 与操作者审核材料不在包内。固定源码/包与本机原工作区不可见的独立 preflight 通过；SDK/PDF/固定上游与 R 的身份逐字段一致，只有新 manifest 改变。

`ToolContract.accept_batch()` 仍先验证整批 schema/参数/ID/reasoning/历史；`run_chi.before_batch()` 只给有效确认混批全部 ID 标记统一拒绝，直接返回并跳过绑定副作用预查。本地/MCP dispatch 在 callback、绑定、claim、子请求、远程调用前分别记录拒绝证据及原 ID 结果，下一正常模型请求才产生新决策。旧 native/live 拒绝不改，50 共享上限和两次确认不放宽。

`audit-history` / `rebind-history` 先核验当前包/SDK/上游，再锁定并完整审计旧 Q→CHI；旧主账以原 SHA 原字节归档，历史 attempts/证据/seal/receipt 保持，通过迁移链按历史身份核验。新身份必须获得自己的 B，旧 attempt/run 的唯一性跨来源延续。中断标记和异常件阻断，不自动修复。

`go_chi_operator.py` 一次执行一个受审 JSON 配置。先校验资源/镜像、在无 Key/禁网只读子容器做包预检，再创建服务；初始 export 和两侧 SQLite 只读快照完成后才读取 Go Key。runner 静止后捕获末态/两侧快照，固定官方 checks 用 `include_semantic_judge=False`；主错误、捕获和清理错误分列，缺证据不会成为整体 complete。参赛 runner 没有 `.env`、socket、fixtures/expectations 或评审挂载。

## 自测、失败与独立复验

实现者自测完整原始输出没有落文件，只有子代理会话返回；以下耗时按其工具返回记录，不补造日志。首个错误环境未遮蔽真实 data/runs，虽然挂载只读、未人为读取题文/轨迹/Key，但不能断言所有旧测试没有访问既有资源；后续改用隔离 tmpfs，主代理付费前完整旧指纹比较已证实原文件未改变。

| 尝试 | 结果与处理 |
| --- | --- |
| Go CHI unittest 首次 50 项 / 0.851s | 1 fail + 1 error：新完整账审先拒绝坏/缺 B receipt，旧断言预期错误码过时；另一个未发布收据的合成 B 被错误标 complete。改两条断言/合成状态，生产逻辑未因该次改动；53 项 / 0.920s 通过 |
| controller Go CHI 55 项 / 0.869s | 通过；新增控制器后 56 项 / 0.863s 首次 1 error，文件路径误用只接受目录的检查器；生产 `_inside` 改用 `_check_components` 后 56 项 / 0.873s 通过 |
| controller 全量 unittest 303 项 / 11.003s | 13 errors：确认包括缺 pytest 的收集错误和只读 runs 写入错误；输出截断且未保存，不能声称知道全部十三项细节。转回现有 dev pytest 和临时 data/runs |
| dev pytest 首次 collection | dev 缺 docker.types，控制器测试明确 skip，并在已有 controller 镜像单独验；最终 dev 409 passed、1 skip、150 subtests / 19.01s；之后新增一项 controller-only 测试 |
| 最终 controller 专项 | 3 项 / 0.003s 通过：缺依赖预检、失败 runner 捕获/清理与主错误保留、两侧快照独立失败。未实测真实世界/旧账/模型，由主代理接续 |

主代理使用固定 Git 快照、网络禁用、源码/vendor/SDK/PDF 只读、data/runs/tmp 独立 tmpfs；完整日志保存在 `evidence/candidate-1/`。以下均未调用真实模型：

| 独立检查 | 实际证据 |
| --- | --- |
| 首轮四个 Docker 启动 | 快照缺忽略的空 data/runs/vendor 挂载点，四个进程均在启动前 exit 125；保留四份首日志。补空目录后同候选执行 |
| 全量与 controller | 409 passed、2 skipped、150 subtests / 19.26s；controller 单独 3 项 / 0.005s 全过，覆盖两个 dev skips |
| 混批与 R 真实响应回放 | 三种顺序的十工具混批、重复同名同参不同 ID、非法 schema/重复 ID、R 第四响应共六例通过；全部拒绝→下一正常请求自主新 MCP 动作/预算更新，混批无 started/claim/确认。首个独立脚本误要求恢复后的正常 MCP 也不能留 observation；修正审核断言后通过，未改候选代码，失败日志保留 |
| 原 R 账副本迁移 | 19 项通过：两次来源、原字节保留、旧 B 隔离/跨源唯一性、Q/CHI 锁、缺件/篡改/链接/孤儿、写入及清标记中断、未结束 attempt 阻断；生产历史写入零 |
| 请求门禁故障边界 | 七组通过：50/51、未知用量、取消/零重试、已知截断、无效但已知计费响应证据/篡改、普通/转义秘密清理 |
| 操作者输入/依赖 | 六类坏配置在 Docker client/Key 前阻断；真实缺 SDK 的 controller 在 httpx import 阶段失败，入口 main 未到达、Key/world/model 均零 |
| 真世界无 Key 捕获 | t012 只启动 world，不创建参赛 runner，预期主错误 credential_missing 保留；前后 2202 provider/0 payer 资源及权威 export/hash 完整、业务无变化、真实 Docker ID 已确认清理。7.947s，其中 readiness 6.667s，旧 CHI 主账原字节不变，不补作 R 终态 |
| 资源差异检查器 | 六类合成输入通过：无变化、目标、非目标、未解析、删除、患者重归属；未解析不会默认无副作用 |

一次只读镜像核对因自动审批审核服务容量不足未执行（非安全性否决），通过相同审批流程重试成功；未绕过审批。首次 Docker socket 沙箱失败后正常经审批使用，均无 API 请求。

## 真实运行前冻结与迁移

`evidence/frozen-candidate.json` 保存同一候选的 31 个运行/操作者源文件 hash、全部依赖、镜像、资源身份、提示/预算条件和五个付费配置；另一个无 Key 捕获配置不是模型 attempt。主代理付费前重新比对 48,552 旧文件、30 链接全部不变，冻结源码/配置一致，四套账 pending/halt 为空；331 文件 / 26,879,068 bytes 新材料扫描无配置秘密，仅准备 Go 单 Key 的临时 0600 文件。原 `.env` 两 Key 保留。

显式 audit-history 与 rebind-history 都成功，旧主账按上列原 SHA 归档，两个原 attempts 原样保留，转换到受审新运行身份；均在 Docker 禁网、不读 Key、不发 API。随后开始唯一新 B，具体真实结果在后续更新。

## 首次真实 B：已知费用的协议兼容失败

`s-go-b-20261029-001` / evaluation `s-go-recovery-20261029` / synthetic-coding-b / attempt-1。操作者耗时 3.928s（预检后到清理），runner exit=1，已确认移除。只有一个真实 Go 请求，HTTP 200 / 1921ms，输入 396、输出 30；余额实扣 **0 USD**、价目价值 **0.00007740 USD**、套餐消耗 **0.00005805 USD**，不可相加。没有工具执行、没有 claim/B receipt、没有自动重试。

返回合法的单个 `inspect_code({})`、assistant/空 content/tool_calls，但完全没有 `reasoning_content`。Guard 保留 wire 与 `chi_tool_batch_invalid` 诊断，过严的工具响应类型校验将可选字段视为必填；B SDK 异常外包装又将主码写成 `chi_entry_failed`。这是接入工程兼容故障，不能说模型选错业务动作、不能用旧 final 可选兼容代替工具阶段证据。随后 Docker 禁网完整全历史审计通过，pending/halt=null，失败/请求/费用/原配置保持。

按 S 兼容修订先离线实现并固定新候选，保留已有字段的精确回放和缺字段的真实无字段表示，坏类型/历史篡改仍拒绝。必要实验有限增至第二个且最后一个新 B≤6，不增加/替换四 C，总上限首已用1+后B6+四C200=207；没有收到有效 B 前不启动 C。原四 C 配置不覆盖，后续在同一修复候选另冻结并注明替代关系。第二 B 再失败即收束，不再自动追加。

## 第二候选的独立审核与新 B

修复候选固定为 `32c24b79c4234954030a3f65c35f2d2d198fadf8`。相对首候选只修改三个生产文件及包内 runbook：Guard 对缺失/null reasoning 使用固定 SDK 的无字段历史表示，字符串原样保留；ToolContract 允许无字段但拒绝任何非字符串值；B 包装层保留具体 guard 错误码。原 HTTP wire 不修改，合法字段的历史删除/替换、无字段时的注入仍拒绝；不改任务提示、工具、模型、预算、账本或 controller。

实现者本次自测全部落盘：22 passed / 11 subtests / 1.49s，以及 Go CHI+旧 Go 83 passed / 2 skipped / 14 subtests / 2.73s，均无真实 API。主代理独立审查差异，在第二 Git 快照隔离 Docker 全量验证 **412 passed、2 skipped、157 subtests / 18.66s**。八类独立 SDK 检查通过：原保存失败响应及 null/empty/string 各三轮工具往返，四类坏类型各一个模拟请求即阻断且保留正确码；全部历史篡改拒绝。六类混批检查在第二候选再次通过，未重跑无关 G/H 或 t013。

新包仍 29 个 allowlisted 文件，manifest **`c38e013e9261e73b5ede9da54293755c9c0d3236cb677aaa73ccc44e3250ca17`**，runtime **`91f0f382ce79235b1174c7322e8d1f3804d629d23816566f471f4f2ed6cf2eeb`**。独立只读/无 Key/禁网 preflight 通过，与首候选除 manifest 外依赖/上游身份相同；`frozen-candidate-2.json` 保存 31 源文件和新五配置，并明确原四个未运行 C 配置的替代关系。原文件不覆盖，三题资源和其余实验条件不变。

付费前比对旧 48,552 文件/30 链接，仅规格允许的 CHI 主账改变；原主账归档原字节验证通过。560 文件 / 32,056,938 bytes 新产物扫描无配置秘密，单 Go Key 临时文件权限 0600、内容仅在 Docker 验证匹配。两 Key 保留，全部 pending/halt=null。新来源先 audit-history 再 rebind-history，三个旧 attempts 保留，首来源主账 SHA `c9f37ff0d452cbb50f912ad5cfa3cfc504cf421975f3366f01801370c27b244a` 归档为第二件；完整两级来源链和旧请求/工具/seal/收据均审计通过。

最后一次新 B `s-go-v2-b-20261029-001` 成功：3 次实际 Go 主请求，输入 **1,383**、输出 **125**，余额实扣 **0 USD**、价目价值 **0.00016955 USD**、套餐消耗 **0.00012717 USD**；`inspect_code`/`verify_patch` 各执行一次，四个 started/returned 事件，无自动重试、claim=false，生成本来源有效 B 收据。操作者 **6.951s**，runner exit=0、已按真实 Docker ID 确认移除。主代理随后禁网完整审计旧 Q/CHI、新收据及逐请求证据，通过且 pending/halt=null，才启动同候选四次 C 的第一个。B 成功仅证明固定 coding 工具协议，不代替 CHI 业务验收。

## 第一次 t012：确认子请求超时，后续三次阻断

`s-go-v2-c-t012-1-20261029-001` / evaluation `s-go-recovery-20261029` / attempt-1。原世界/资源、新候选及冻结参数不变，runner 自主执行，没有人工业务指导。8 次主请求 HTTP 200 并结算；第 9 个实际请求为单独 `local-confirm-patient` 触发的确认子请求，约 **60.023s** 后 `chi_timeout`，未获得响应/可信 usage，主账保留 **pending={本 run, round:9}、halted=null**。这是传输超时及未知结算，无法进一步归因到提供方根因；不把它称为错误业务动作、零费用或请求未送达。

19 次工具开始：`local-fs-list` 3、`local-fs-read` 7、`chart.search_patients` 1、`chart.get_patient_chart_by_patient` 7、`local-confirm-patient` 1；18 次返回，确认工具因子请求超时失败一次。没有业务写工具、claim=false、没有确认成功绑定。模型读取多个候选病历后，已知主请求输入逐渐增至 260,137 tokens；这是本次上下文规模，绝非百万上下文实测。此次没有触发有效确认混批拒绝，真实恢复效果仍只有离线覆盖，不能宣称已在真实 C 证明。

操作者 **142.519s**（readiness 5.583s；不含创建记录之前的独立包预检），runner exit=1。首错误保留 `chi_timeout`；原世界权威初始/末态、expectations/shared-world 和四份资源快照均保存，主代理逐 hash 独立核验通过。provider 前后均 2,202 行、payer 均 0 行，全部业务资源语义差异为零；该证据限 resources 表，审计 trace/工作区文件另列。八项适用确定性检查均 false、一项 not_applicable，未形成目标业务状态，没有临床判分或官方得分。runner/world/network 均按真实 Docker ID 验证已移除，capture_error/cleanup_error=null。

第九请求的持久占位保留，完整源码/来源链/历史请求/工具/seal/收据的**结构和证据审计通过，但财务用量不完整**。既有 audit-history/rebind-history 因 `chi_migration_history_unsettled` 拒绝，不能称为全部 settled。另用同一包在无 Key/禁网环境验证新 coding-b 入口，返回 `chi_usage_unknown`，未创建证明用 attempt。主代理没有再调用 Go/native/判分 API；没有删 pending、重建账根、静默回退或自动重试。

因此第二次 t012、t014 和 t017 均为 **not_run / prior_request_usage_unknown**。三个独占输出路径/attempt 均不存在，冻结配置保留在 `remaining-runs-blocked.json`；原未运行首候选配置也保留。它们不是业务失败、也不是验收通过。解除阻断需要可信提供方结算证据和单独受审的对账方案；当前未实现自动对账，界面整数 0% 或笼统额度充足不足以核销未知请求。t014/t017 仍未向参赛模型和实现者展示或执行。

### 逐请求与费用

以下耗时为响应读取到 Guard 收尾的诊断毫秒，含校验/记账；HTTP wire 的纯读取时间另在原 evidence，约少 14–31ms。B1 只有一个请求，主诊断 1937ms。表中的未知值不计入已知累计，不估成零。

| run | 轮次/用途 | 输入 / 输出 tokens | 诊断 ms | 结果 |
| --- | --- | --- | --- | --- |
| 首 B | 1 / main | 396 / 30 | 1937 | 已结算，契约拒绝 |
| 新 B | 1 / main | 396 / 30 | 2023 | 已结算 |
| 新 B | 2 / main | 449 / 74 | 1535 | 已结算 |
| 新 B | 3 / main | 538 / 21 | 1530 | 已结算 |
| t012 | 1 / main | 10924 / 115 | 5989 | 已结算 |
| t012 | 2 / main | 11758 / 114 | 6175 | 已结算 |
| t012 | 3 / main | 13925 / 126 | 4793 | 已结算 |
| t012 | 4 / main | 15920 / 127 | 3245 | 已结算 |
| t012 | 5 / main | 73102 / 1043 | 14620 | 已结算 |
| t012 | 6 / main | 187451 / 1080 | 13295 | 已结算 |
| t012 | 7 / main | 218880 / 354 | 8338 | 已结算 |
| t012 | 8 / main | 260137 / 1110 | 16094 | 已结算 |
| t012 | 9 / confirmation | 未知 | 60023 | 无 HTTP 响应，用量未知，阻断 |

| 尝试 | 已知输入 / 输出 | 余额实扣 USD（已知） | 价目价值 USD（已知） | 套餐消耗 USD（已知） | 操作者秒 |
| --- | --- | --- | --- | --- | --- |
| 首 B 失败，1 已结算 | 396 / 30 | 0 | 0.00007740 | 0.00005805 | 3.928 |
| 新 B 成功，3 已结算 | 1383 / 125 | 0 | 0.00016955 | 0.00012717 | 6.951 |
| 首 t012 失败，8 已结算 + 1 未知 | 792097 / 4069 | 0 + 未知 | 0.12110542 + 未知 | 0.09082907 + 未知 | 142.519 |
| 本轮共 13 发起、12 已结算、1 未知 | **793876 / 4224 + 未知** | **0 + 未知** | **0.12135237 + 未知** | **0.09101429 + 未知** | **153.398** |

全轮 21 次工具开始、20 次返回、1 次失败，没有原版 Claude/付费临床评审。Q+R+S 累计 26 发起、25 已结算、1 未知，已知输入 1,047,973 / 输出 6,082，余额实扣 0 + 未知 USD、价目价值 0.16009249 + 未知 USD、套餐消耗 0.12006939 + 未知 USD。三列是不同口径，不能相加；不含订阅固定费、账户其他历史/余量或未得 usage 的请求。旧 CNY 保守口径仍为 121.571472（K 119.990746、review 1.569062、早期 0.011664），旧账未变且不与 USD 相加。

### 后处理尝试与最终证据

主代理首个 C 后审计使用要求 settled 的 audit-history，按规则被 unsettled 拒绝；随后改为持旧 Q 锁的只读结构/证据校验，不修改生产账或候选。该次检查最终 exit=1 是明确验证 unknown 阻断。一次离线审计 Docker 命令误加含多冒号的挂载，启动前 exit=125；修正后执行，没有 Key/模型请求。最终汇总首脚本把 Q 请求误当主账顶层，KeyError 后改从原 runs 文件汇总；两份日志保留，未改变任何运行结果。除此之外，第二候选全量/八类 SDK/六类混批、preflight、冻结、两次历史操作、新 B、归档及解包预检均一次通过；首候选/实现者的全部早期失败见前表。

最终在 Docker 禁网完成：旧 48,552 文件/30 链接逐项核对，仅授权 CHI 主账路径改变，其两级归档原字节及全部历史 attempts/失败/claim/费用/证据/seal/receipt 验证通过；31 源文件、五配置、三题资源身份与包不变；所有 S 标签的容器和网络为空；原 `.env` 两 Key 存在，临时单 Key 文件已删除。扫描 636 个新文件 / 42,323,582 bytes 未发现两种配置秘密。证据在本轮忽略目录 `evidence/final-audit.json`；新运行审核 JSON、逐请求诊断、原始日志、业务捕获及资源差异留本地，不上传。

独立归档为 `runs/go-chi-batch-recovery-root/exports/chi-go-entry-32c24b7-bundle.tar.gz`，**122,365 bytes**，SHA-256 **`d00489f98af3f0c7843c88c3a7849405fd4be16ba6825d7daaf0325a84ee0d8a`**。29 文件加 manifest 和必要空目录；真实解包后禁网、无 Key、原源码不可见的独立 preflight 与原包 JSON 完全相同。归档不含 vendor、任务、手册、凭据、controller 或运行证据；外部固定依赖/角色 MCP/公开输入仍须由调用方提供。它是可复现 runner 包，不表示 stock harness 自动选用、完整 Harbor/F.5 配送或正式最终冻结完成。

## 审核结论与接续

`32c24b7` 的源码差异、离线/故障/历史接续/独立包与新 B **在上述技术范围通过**；唯一新 C 因确认请求超时失败，业务未通过，剩余三次受未知用量阻断，完整本轮业务验收未完成。有效混批真实恢复、两题未见迁移、Go 付费开发评审、十一月 ZDR、非编码用途官方支持、1M、完整 Harbor/F.5 与官方评分不补作通过。Go 用途仍是用户知悉的未确认事项，官方来源与固定 harness/角色/启动核对见 [R 报告](chi-go-evaluation-entry-review.md#基线授权与事实核对)；没有调用 Claude，official_reward=null。

README 记录运行与费用读取方法；OpenSpec 记录有限修订及停止条件；学习账本记录完整调用链、失败归因及用户理解证据；最新状态只在 REVIEW_STATE。下一步交用户审核本轮 PR，后续先解决未知请求的可信对账，再另行冻结恢复计划，不能直接执行被阻断配置。文档/推送/PR 不改变上面的固定实现身份，主代理不 merge/auto-merge。

GitHub 上传清单为本分支 24 份源码/测试/规格/文档，staged patch 和全部允许文件秘密扫描通过。已创建并附加 base=main 的 [PR #23](https://github.com/xsw932187210-cell/chi-agent/pull/23)，由用户审核决定合并；源码验收身份仍为上列第二候选，PR/文档提交不代替业务验收。
