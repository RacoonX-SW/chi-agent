# S：Go CHI 混批恢复与完整终态验证

日期：2026-10-29（Asia/Shanghai）。本轮按[有界规格](../openspec/changes/go-chi-batch-recovery/design.md)推进；在实际证据完成前不预填通过。

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
