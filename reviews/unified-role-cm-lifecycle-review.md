# W：统一角色操作者与CM开发链路审核

日期：2026-10-31（Asia/Shanghai）。规格见[W设计](../openspec/changes/unified-role-cm-lifecycle/design.md)。固定候选已独立离线通过，唯一当前B与三题各一次真实开发及最终审计完成。统一操作者与完整CM链路通过本地开发验收；payer业务终态未达预期，官方/临床评审未执行。

## 接续、基线与授权

主代理读取协作/学习/审核入口、README相关部分、V规格及[V报告](representative-role-baseline-review.md)，通过GitHub连接器核对PR26 merged，merge commit为 `5a621dc67afd8f0e26088b3b993615066a993229`。首次沙箱内fetch不能写.git/FETCH_HEAD；沿用户授权提升权限后fetch成功，再以ls-remote核实最新origin/main确仍为该SHA，从其建立 `codex/unified-role-cm-lifecycle`。没有沿已合并分支追加新任务。

开始时工作区并非交接所述干净：AGENTS.md与COLLABORATION.md已有用户修改，原diff保存于 `/private/tmp/chi-role-user-changes.patch`，完整保留，不归为W实现。用户授权一个Terra/high实现子代理，主代理负责规格/独立审核/教学/GitHub。实现者首次受账户用量限制中断，用户要求继续后恢复同一代理/模型，没有替换模型或增加写入者。

本轮仅授权规格内provider→payer→CM三题各一次真实开发，以及包身份变更时最多一次新B；离线候选独立审核在先。旧题复测、Claude、付费临床评审、F.5/配送/官方判分未恢复，official_reward=null。

## 独立历史基线

原始证据位于忽略的 `runs/unified-role-cm-lifecycle-root/`；操作者程序在operator-audit，审计在evidence，独立验证在independent，实现者自测在implementation，真实清单产物在actual。原数据/手册/persona/凭据/vendor/真实轨迹不上传。

主代理用V受审包、固定vendor、原SDK/PDF卷，在Python3.12 controller中禁网/无Key/原目录只读，取得只读Q锁后调用原Q `_validate()`/`_audit_runs()`及CHI `inspect_history()`，完整审计来源迁移、wire/seal/ack链。当前identity `b29d6ecfdb7503fd0caecfd413aa06b8dd09cc6b0d4d71581b5951b33c5b3e60`，主账SHA256 `8b89b9cdd89294d15cce3b09141424f20bbed0c5a33d1f04f824ea08b3999bee`；pending/halt=null，唯一旧S第9请求留档且未结算。未再次ack/settle/replay/删除。

保存当前Q/CHI全部511个普通文件的size/hash和逐字副本于 `evidence/history-baseline.json`、`evidence/history-copy-original/`；已核对V当前B receipt及其identity有效。W若改变包身份，该B不能自动跨身份复用。首次独立审计脚本误以为attempt自带identity，在读取B字段时KeyError停止；未写原历史、未创建副本、无模型/世界副作用。修正为读取原B receipt.identity后通过，完整副本逐字核验完成。

`evidence/environment-baseline.json`：Docker内确认vendor HEAD及工作树干净；V三个manifest仍逐项满足固定revision/闭包/hash（provider7/payer11/CM6文件）；dev/controller/world镜像完整ID和原model/PDF卷一致，镜像未含模型Key。仅检查本地OPENCODE_API_KEY与DEEPSEEK_API_KEY存在性，保留后者，不输出秘密或将其注入world。

实现者早期禁网测试曾因dev镜像不含Anthropic而在收集时失败，随后改用原world venv和V既有只读测试依赖完成对应测试，没有新增安装。实际锁定Uvicorn0.54的 `serve()` 使用 `capture_signals`，单设旧 `install_signal_handlers` 不生效；实现者据固定源码修正broker信号接管，仍待最终独立验证。以上均为开发中发现，不能作为当前候选通过证据。

## 当前人工外部条件复核

北京时间2026-10-31人工查阅[Go官方说明](https://opencode.ai/v2/docs/console/go/#privacy)：DeepSeek不用于训练、0天留存仍带月度ZDR脚注，明确截止10月31日，十一月尚未确认。真实调用前还须按实际日期人工复核，不沿旧结论跨月放行；不新增程序日历门禁/后台唤醒。用户已知非编码用途尚无官方明确确认并授权开发，不能记成官方许可。端点与费用字段语义按[官方Inference API](https://opencode.ai/v2/docs/console/api/inference/)核对，三项USD分别记录。

## 固定候选与独立离线验收

候选 `ad2569937e0afe649807669c70f86da97c708e86`。实现者停写后主代理检查基线差异、新入口/调用者、锁定SDK/原服务调用代码，显式提交代码/测试/规格，再用Git archive与独立固定vendor克隆建立只读快照。32文件包manifest为 `fbf133e0ac0115ae2982b4de12ab05757c4c4cc51c000cd6e609244bb75d6e4d`，runtime identity为 `a66696e552a9164194b02d0e5191c68f15e4191cbdb0aaff0e31ffffd25c3a24`。包中仅go_chi_entry/mcp/tools三文件改变，所有开发操作者、bootstrap、broker与测试shim排除；SDK/SDK源码/PDF/vendor四字段与V逐项一致。

主链为 `role_operator.main()` → 原资源/包预检 → 本轮internal世界与公开输入 → `role_runner` → 原 `go_chi_entry.main(development=...)` 身份/公开路径/Q→CHI/B/封存 → `run_chi()`/原SDK工具循环。CM broker与runner同一进程/事件循环/journal/billing锁；原MCP与本地工具派发锁内检查fatal，同批患者失败后的排队动作也拒绝。世界仍由原entrypoint激活venv，经显式bind的开发cb装入adapter，再由原CM service管理会话、STOP、回滚与持久化。

包外TrackedServer记录每次MCP实际完整返回或未确认结束；不能用模型成功/exit0替代世界静止证据。模型在工具完成后失败仍抓权威终态；MCP取消后可能继续写入时标unproven，不将等待时长当证明。runner整体1500秒、broker启动30秒/收尾最多450秒、operator2040秒，原main/confirmation/患者HTTP/MCP内层策略保留。SIGTERM由runner处理，broker禁用Uvicorn0.54的独立capture_signals，账关闭前收束回调。

| 主代理独立检查 | 结果与证据 |
| --- | --- |
| 禁网全量 | **492 passed、3 skipped、203 subtests，25.95秒**；`independent/full-tests.log/xml`，复用U现有Harbor0.20.0 overlay及V测试依赖，没有安装 |
| controller补验 | 缺Docker SDK而跳过的3项全部通过，0.45秒；`controller-tests.log/xml`。实现者原全量另跳过的5项Harbor检查已由本次全量实际覆盖 |
| 三角色跨容器 | 真官方world、真SDK/MCP、合成HTTP且runner禁外网；provider10.318秒、payer14.272秒、CM12.031秒。初末原导出/两侧完整resources、角色端点、payer四PDF真实读取、能力文件删除与容器/网络ID404均通过 |
| CM正常与患者失败 | 正常6 main+1 aux，真实两消息持久化、STOP=patient_ended；主结果/下一反馈不含aux。可信usage的患者HTTP400场景5 main+1 aux、无下一主请求、消息回滚、失败原终态完整，12.430秒；`cross-container-sandbox-{cm,cm-failure}` |
| 完整历史副本 | 自然合成B和C后审计完整旧链；再独立副本模拟真实AuxTransport超时，父工具记failed/封存后pending仍可审计、下一attempt拒绝，新未知未ack；来源归档篡改拒绝，原511文件不变；`history-independent.json` |
| 实际网络布局 | 无Key的独立容器复现生产双网顺序，runner以bridge为源完成OpenCode TLS握手，world仅internal且外连受阻；HTTP/模型请求0，精确清理；`network-layout.json` |
| 配置拒绝补验 | 固定候选独立副本的8类错误均在Docker/凭据/世界访问前拒绝，含错误role/manifest/dev hash、输出重叠、dataset越界、期限/额外字段/重复键；`preflight-refusals/summary.json`，无源码改变/模型调用 |

独立运行命令均在Docker：归档准备用 `operator-audit/prepare_independent.py`；全量使用原world的 `/workspace/.venv/bin/python`、只读model/PDF/test-deps/U-overlay及独立runs；controller补验用 `/opt/a-venv/bin/python`。跨容器从archive源运行 `tests/role_cross_container_synthetic.py --role provider|payer|cm --scenario success` 及 `--role cm --scenario patient-failure`，四个空sandbox串行；`HOST_PROJECT_ROOT`各自指向其真实宿主目录。未用合成费用并入真账，也未重做G/H安装。

## 全部开发失败与修正

- 上述最早fetch权限、独立B字段读取、dev缺Anthropic收集失败均保留；无真实模型副作用。
- 实现者首次跨容器CM已经往返，但controller缺vendor导入使最终程序检查不可用；第二个隔离sandbox在导入时停止。修正为operator启动前预导入固定verifier，并补测试harness路径，原失败目录不覆盖。
- 实现者曾同时启动四个隔离场景，其中两项CM复用Docker名称；sandbox-010被resource_exists在创建前拒绝。其余007/008/009完成并清理后，011串行患者失败通过。该测试调度错误保留，不算生产模型失败或真实C；主代理独立四场景全部串行。
- 预审发现“整体失败就不抓终态”会丢失已完成工具的失败现场，改为按实际MCP在途证明；又发现仅下一HTTP检查fatal会放过同批后排写入，已在共享锁内补门禁并测试。取消后远端延迟写入及进程SIGTERM场景均在独立全量中覆盖。
- 主代理冻结汇总初次忽略JUnit将203个subtests计入tests总数，在任何配置写入/真实调用前断言停止；按698总项=492测试+3跳过+203子检查修正统计后完成冻结，未重跑测试或调用模型。

## 真实清单冻结与历史来源迁移

`evidence/offline-independent-acceptance.json`确认有界通过；`live-plan-frozen.json` SHA256为 `7eb735abcf968b0fc4fd5da4384b35efa956a601973e39eccf899e1d3fd2434c`，绑定候选、包、身份、4个唯一配置和人工隐私复核。身份已改变，因此只允许新B一次，不能复用旧B跨身份。北京时间10月31日13:33人工再次复核官方页面，仍只明确ZDR到当天，十一月未确认。

无Key禁网调用原 `rebind-history`，把原CHI主账以其原SHA完整追加到source-archives，11个旧attempt、旧wire/seal/ack及Q账保留。旧S第9请求未再处理。当前身份的新B与三题严格按冻结顺序逐项执行，没有重跑、追加其他题或用未用次数扩量。

## 真实Go运行与业务边界

每项结束后用禁网 `operator-audit/audit_live_progress.py <stage>` 独立核对完整Q/CHI历史、每请求用量/三项USD、原终态/资源及精确ID清理，前项条件满足才启动下一项。Key只从本地文件读取选定项并进入runner，DEEPSEEK_API_KEY保留；world环境/网络另取无秘密的实时inspect证明。只读live-layout观察器曾错误假设在途主记录已保存world_id/capability_sha256，KeyError停止；改按冻结run名称与owner标签解析，并实时比较宿主/world/runner能力文件hash，结束后再与最终主记录比对。未改变运行代码、模型动作或账目；controller硬中断/daemon故障的恢复仍未验证，不能把正常finally清理扩大为此类保证。

| 已完成运行 | 实际请求 | 累计输入 / 输出tokens | 操作者耗时 | 余额实扣USD | 价目价值USD | Go套餐消耗USD |
| --- | --- | --- | --- | --- | --- | --- |
| 当前身份B | 3 main | 1371 / 111 | 7.508秒 | 0 | 0.00015935 | 0.00009561 |
| provider关单分支 | 20 main + 1 confirmation | 4886284 / 31545 | 484.380秒 | 0 | 0.75126748 | 0.45076048 |
| payer | 26 main | 4059724 / 21965 | 333.221秒 | 0 | 0.62087691 | 0.37252613 |
| CM | 33 main + 10 patient_simulator | 3949782 / 32365 | 392.358秒 | 0 | 0.60086005 | 0.36051597 |
| 本轮合计 | **93** | **12897161 / 85986** | 各次耗时分列 | **0** | **1.97316379** | **1.18389819** |

这里tokens是跨请求累计，不代表单请求百万上下文测试。三项USD各自记录，不相加、不混旧CNY，也不包含订阅固定费；余额0只证明这些请求返回的计费记录，不冒充整个账户余额已核清。上述新请求均来源go、已结算，当前pending/halt=null；510项旧文件逐字不变，原CHI主账以原SHA完整归档，唯一旧S未结算仍保留。

provider在原世界新建一案并到closed，仍属于provider_new_referral的不提交/关单分支；全量资源变化没有提交队列变化。固定程序检查12项true、1项not_applicable；这不是新的医院任务族或官方/临床通过率。

payer工程链正常收口，程序检查22项true、4项false、11项not_applicable。false为 `md.audit`、`md.decision_exists`、`outcome.letter_types`、`outcome.target_status`。只读原终态确认目标case为approved、生成approval信，但未符合固定终态与信件类型检查；具体期望材料保留本地，不上传。原MdReviewVerifier还记录目标无MD决定/对应audit，不把这些raw false自动改NA，也不凭它们下临床结论；后续内容/原因评审须另授权。最早诊断查询曾按target_case.case_id过滤信件且统计全世界MD记录，随后按官方export.target_case_id限定目标，确认目标MD决定0、护士建议1。没有据评分材料修改Agent、改写结果或重跑payer；完整资源及全部Go费用原样保留。

CM在真实固定官方世界完成：一案closed、一份chart review、一份外联记录、一个ended会话、一份complete评估和一份finalized照护计划。会话真实保存10条care_manager和10条patient消息，因原状态机max_turns结束；不能改称真实患者主动STOP（STOP另由合成组件验证）。14项原程序检查true，临床内容verdict/官方reward仍null。本地患者条件为Go/DeepSeek，不能与官方Anthropic条件等同或归因为Agent单项改进。

CM主请求33次为3901866/28392输入/输出tokens，患者辅助10次为47916/3973；原SDK结果turns=33，未把辅助计入Agent反馈或主用量。辅助余额实扣0、价目0.00356889、套餐消耗0.00214134 USD，均在同一原账单列purpose及真实parent tool；没有第二个计费所有者或第11次患者付费请求。详情见 `evidence/cm-business-and-purpose.json`。

## 最终审计、教学与限制

`evidence/final-audit.json`确认93请求全部go/已结算、用量/三项费用完整，wire/response/diagnostic、claim/seal及真实辅助parent链完整，零新增未知/自动重试/回退。当前active pending/halt=null；510项旧Q/CHI文件逐字不变，原主账以原SHA留在0005来源归档，旧11个attempt/旧来源前缀/唯一ack原样。新主账SHA256为 `9060010ba5e487538fc3e79e025193b591e9e2ef883c92eb55d53c27598775b2`；历史累计仍因旧S未结算而不完整，不能称历史全部结清。

三题初末原导出、provider/payer完整resources、模型/容器日志与三项错误分层完整；真实world/runner内外网及Go Key隔离有无秘密inspect，CM宿主/world/runner能力hash一致，结束后能力文件删除。owned容器/网络按ID均404，无Key字节进入actual或操作者产物；SDK/PDF/vendor与V逐字段一致。原始成功/失败、题文/世界/expectations/persona/轨迹留忽略目录，不上传。

集中教学沿“操作者输入和身份→原entry锁/B→SDK主请求→MCP/官方service→同进程broker→辅助结算→原状态机→静止/原终态/清理”展开，结合患者失败回滚及payer工程完成但业务终态不符，区分工程收口、业务目标、临床正确性和官方分数。学习账本只记录关键链路/取舍/下一入口；用户明确范围和预算，代理执行实现与运行，没有新增用户独立源码复述/实践证据，不记掌握或安排小测。

本轮清单已收束，不因payer未达目标再跑一遍。后续可基于原证据提出公开策略改进和有界新规格；t012/t014/t017/t013不重跑，t019例行付费、Claude/Go付费临床评审、正式Harbor CLI/真实Go Trial/完整配送/F.5仍暂停。其他任务/跨任务统计稳定性、Go非编码官方许可、十一月ZDR、1M/长期缓存及controller硬中断/daemon故障均未验证。official_reward=null。

README、OpenSpec、唯一REVIEW_STATE与既有学习账本按职责维护；6份文档200条本地链接及代码围栏、git diff --check通过。`evidence/upload-audit.json`核对恰为16项允许源码/测试/职责文档，真实Key值缺席；题文/世界/persona/原评分材料/原始轨迹/数据/vendor未选入，具体期望值只留本地证据。

实现候选ad25699与证据/教学文档e60a790已显式提交并推送 `codex/unified-role-cm-lifecycle`，创建base=main的[PR27](https://github.com/xsw932187210-cell/chi-agent/pull/27)。交用户审核决定合并，主代理未merge/auto-merge；最终链接/清单提交仅为文档，不改变实现验收身份或触发重复B。收尾再次fetch核实origin/main仍是本轮基线。原AGENTS.md、COLLABORATION.md两项既有用户修改完整保留且未纳入PR，不把整个工作区称为干净。
