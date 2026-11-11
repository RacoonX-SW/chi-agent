# 最小真实验证审批方案（草案、未授权执行）

建立：2026-11-04（Asia/Shanghai）。**本文件、PR及其合并均不是调用授权。** 它绑定[本轮候选清单](../../../reviews/validation-candidate-20261104.json)及[离线报告](../../../reviews/validation-preparation-review.md)，与[旧审批草案](../real-run-approval/proposal.md)分开。旧候选的已用许可、可选批次和后继attempt约定不迁移到本轮。下面B、S、R是依次可审阅的阶段，不是一揽子执行请求；当前仅建议批准B及其C1处置关联，S/R先完成接线再单独批准。

## 1. 固定候选及共用约束

| 项目 | 固定值 |
| --- | --- |
| 生产源码 | `0625c26dc9da453a3ac13bf537d156cad57dd940`，生产/测试/profile字节与已审`83e0ceb22f79c88699d6e44fdbfc85290e2445fa`相同 |
| 候选JSON文件SHA256 | `1846d79cd276aee9cb8414e9e80b78ac9639f227c3a2ae1a97bcefb9f3f9b1d2` |
| Go runtime identity | `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559` |
| Go bundle manifest identity | `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb` |
| release manifest SHA256 | `4b0c2f31553fac46cfa1ee1f6e8638e49e53377966e81267960f762518017d6a` |
| 模型/端点 | `deepseek-v4.1-flash` / `https://opencode.ai/inference/go/openai/v1/chat/completions` |
| 推理/重试 | thinking `{type:enabled}`、reasoning_effort `high`、自动重试0；禁止静默回退或改提供方 |
| profile/依赖/提示/工具 | 候选JSON及报告第2/5节的精确hash；固定vendor、SDK/PDF锁与source hash；只支持已验Linux arm64/Python3.12 |
| 费用 | `record_only`、null cap；input/output/cache（如有）及list/allowance/charged三项USD分列，缺字段null/warning，旧CNY分开；不是零费或余额证明 |
| 开关 | B全部关闭；S仅`chi-input-summary-v1`；R仅`chi-output-recovery-v1`；Y shadow全程关闭 |

所有失败、未采用摘要、无效续写、取消及HTTP错误都占实际已reserve/发送用量，不只统计成功。主/确认/summary/continuation **合计≤50**，确认≤2；患者辅助独立≤10，CM一般总HTTP≤60。本方案S/R选payer，患者辅助实际许可为0，HTTP≤50。B独立上限6，不给S/R另加摘要/续写请求额度。

本文物理HTTP上界指模型提供方请求；MCP/world工具调用另留trace，不能混作模型计费次数或漏掉工具副作用/清理证据。

允许参数仅限上述固定profile/用途常量、单独run/attempt标识和本文件指明的互斥开关。输出：B1024；CHI主/summary/continuation8192，确认32768，患者8192。context预算仍是原byte估计，摘要阈值4/5、保留2近期闭合批、每run最多1摘要且须留1后续main；恢复每链1、每run2。不得为触发改模型、high、提示、输出上限、context安全预算或输入截断规则。

时间沿现有policy：connect10/write60/pool60；主/summary/continuation read240、IO300；确认/患者 read360、IO420；B准入180/操作者360；CHI准入900、原entry操作者窗口1380；包外role_runner1500、operator2040秒。不是在到点强杀后立即判无在途；取消/硬中断按unknown与世界静止证据收尾。OpenCode路径不受DeepSeek官方直连避峰约束，仍无后台等待/自动唤醒。

## 2. G0历史准入：先决定，不清账

必须先补齐以下二者之一，才能连B也启动：

1. 提供可关联 `real-ext-payer-010` round1 的可信单请求结果/token及提供方结算材料，按受审流程处置；仅Console无匹配session或164ms失败不足以证明零发送。
2. 用户明确决定：保留旧unknown及不完整费用，限定允许本轮新identity、下列后继evaluation和**仅本次具体获准阶段**继续。记录决定原文/来源与新旧身份关联；不修改旧pending、不宣布已结算、不重发原请求。

待关联的旧事实：

- 旧root：`runs/real-external/state-abl-on`；accounting SHA `1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef`；`eval-abl-on` / `real-ext-payer-010` / round1，request SHA `2fa28297a8d01af62f89a6604ac2d1b8b8a32dc19e6dee171bad61f125030b0e`，结果/token未知。
- 历史后继root `state-abl-on2` / `eval-abl-on2`，accounting SHA `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9`；C1所选来源未闭合其特定授权。用户若有既有决定来源可补链接/原文；不能因本轮新许可回写历史授权已存在。
- 拟用后继：`evaluation=eval-vprep-20261104`，host state=`/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/runs/validation-live-20261104/state`，容器映射`/state`。**尚未初始化，不因路径新就获得准入。** 在获得上述具体决定前不创建真实journal或迁移旧账。

G0记录放拟用运行目录的 `admission-decision.json`：旧root/hash/run/round/request、历史后继缺口、处置选择、批准来源原文、候选清单SHA、准许stage/run/次数、新state/evaluation。它是操作者的授权证据，不伪装成程序已有跨root账户登记或结算事件。后续各阶段共用这一明确获准的state/evaluation，禁止因新unknown再换root。若首次路径已被占用，停止报告，不自动改名绕过。

Go用途/隐私使用用户既有决定，无需再次确认；不把该决定或本审批当成OpenCode官方许可/ZDR条款证明。

## 3. B：新身份最小coding-B（当前建议审批项）

**用途/输入**：只验证当前包的真实Go coding工具往返、reasoning回放、用量/费用与B收据；固定自造`add(a,b)`修复题，`inspect_code`、`verify_patch`及工具结果只来自包内常量。没有CHI任务、手册、患者、MCP、world、旧轨迹或隐藏材料进入输入。

**入口/身份**：隔离release的 `package/scripts/go_chi_entry.py coding-b`，本文件第1节精确bundle/runtime。拟定run=`vprep-b-001`、task=`synthetic-coding-b`、attempt=`attempt-1`、evaluation=`eval-vprep-20261104`。在Docker/Python3.12中，受审挂载/环境就绪后对应argv为（**草案，不在准备轮运行**）：

```sh
python /package/scripts/go_chi_entry.py coding-b \
  --bundle-sha256 de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb \
  --evaluation-id eval-vprep-20261104 --task-id synthetic-coding-b \
  --attempt-id attempt-1 --run-id vprep-b-001 \
  --history-mode external --output-root /state --logs-dir /runner-logs/vprep-b-001
```

只供应隔离包、固定只读vendor/依赖卷、获准的state与独立log父目录；运行时只注入必要 `OPENCODE_API_KEY`，不挂`.env`或其他provider/judge凭据。先复核包、依赖及无Key preflight；Extra Usage保持关闭，若无法证实或响应非go billing则停止。本轮没有读取/验证实际Key、额度或控制台。

**次数**：1逻辑B；最多6物理provider HTTP（main≤6，确认0、summary0、continuation0、患者0）。正常预期不等于固定3次；真实模型若偏离协议立即按原门禁停止，不补到成功。

**成功证据**：两指定工具按原契约完成且最终verification:pass；全部真实响应/usage留证结算、pending/halt为空、run/seal/新identity B receipt有效；保存每物理request/response hash、模型/路由/session、tokens、三项USD完整性和退出码。成功才可为同identity同state的后续CHI提供B准入。**不证明**摘要/恢复、CHI业务、患者/官方Harbor或官方分数。

**停止/收尾**：任一非预期响应、length、未知结果/token、网络/取消/凭据/计费异常、持久化错误、6次/时间上限即停止，失败同样计数；不自动第二次B。留存run/日志/receipt是否生成、pending/failed/known费用，不补造成功收据；容器退出且owned容器不存在，日志和state保留可读。B无world或患者，清理不应删除旧历史。仅费用字段缺项且token可信按原warning策略记录，不写费用0。

**需明确批准**：G0处置及关联 + 本候选/上述evaluation/state/run的1次B、最多6HTTP、固定用途/参数/收尾。批准B不会启动S/R或任何C。

## 4. S：输入摘要端点兼容（以后单独审批）

**准入依赖**：G0明确覆盖S、B成功且收据仍适用、无新pending/halt/未确认清理；先完成报告第8节DeepSeek的包外开关接线及GPT定向离线审核。包外 operator 已支持透传（精确版本、互斥、缺省关闭），但**本项仍需独立授权，尚不可直接执行**。仅operator改动且内包逐字不变可沿本候选；包变则重建/新B/重绑方案，不能自动套用本许可。

**入口/资源/用途**：`role_operator.py --config <新固定配置> --config-sha256 <实际SHA>` → `role_runner.py` → 本候选 `go_chi_entry.py live --input-summary chi-input-summary-v1`。包外 `role_operator` 已支持两开关透传（精确版本、互斥、缺省关闭）；以下探针配置仍为草案，执行须另行授权。禁止填历史 tri-on2 配置假装开启。role=payer，task=`pa_t030_t030_o002_p01_triage_payer`，run=`vprep-s-001`、attempt=`summary-probe-1`，上述同evaluation/state；输出=`runs/validation-live-20261104/summary`。报告第5节的公开instruction/reference/手册/world及manifest/image hash为资源清单；Agent只见公开输入和正常工具观察，隐藏初始化资料留官方服务、不解析答案选动作。每次新world，不续用旧业务状态。

**验证问题**：自然达到原阈值时，真实端点是否接受无业务tools的固定摘要请求/JSON schema，并返回可被程序接受的候选；随后真实main是否接受带checkpoint的历史视图并保留工具/保护真值。模型自主走原公开任务，操作者不代选动作、不让隐藏expectations进入提示。

**次数**：1逻辑CHI run；逻辑SDK step至多50（summary不算SDK step）；物理 `main+confirmation+summary≤50`，summary≤1且占50、confirmation≤2，continuation0、患者0。触发1摘要时main最多49（若同时2确认则最多47）；未触发summary则≤50主/确认。费用分母包括任何无效候选和未采用摘要。

**成功证据**：summary request来源选区/保护hash及output_schema、已知usage先结算、schema/echo/source/reduction校验、checkpoint安装、下一真实main wire及返回、原SDK/证据历史保留、无保护状态变更；context/wire/summary trace、journal/seal及run_log可相互对应。仅端点兼容有证据；仍需人工逐条对原source核对事实、否定/不确定性、遗漏和“行动完成”陈述，才能限定评价本样本忠实度；程序引用合法不证明语义忠实。字符/byte减少不证明token/净费用收益。

**未触发/停止/清理**：一次run正常终结或先到原50/准入时间/失败即收口；没有summary则“未触发，兼容未覆盖”。无选区、摘要视图超限、无效/未节省候选、length、protected变化、未知/取消/落盘失败依原策略停止，不再追加run/summary或改阈值。没有续写救摘要。初末capture/资源hash、world_quiescence、broker_drained（payer无患者）、runner退出及owned world/runner/net删除证据均需确认；若MCP仍可能在途，标unproven并阻止后续。原始日志保留本地，公开仅元数据。

**需明确批准**：接线审核后精确config/hash及G0对S的授权关联、上述一次payer业务载荷/最多50HTTP、只开summary、新world/有权限资源及清理；不是自动获得两能力或收益实验许可。资源漂移先报告，不换题。

## 5. R：输出恢复端点兼容（以后单独审批）

**准入依赖/入口/输入**：与S的G0/B/无新unknown/接线审核要求相同；可不采用S，但不能在S失败未知或清理未证实时继续。相同已见t030公开资源，另起全新world；同state/evaluation，run=`vprep-r-001`、attempt=`recovery-probe-1`，输出=`runs/validation-live-20261104/recovery`。新固定operator配置只开 `output_recovery=chi-output-recovery-v1`，最终进入包内 `live --output-recovery chi-output-recovery-v1`；summary、shadow关闭。

**验证问题**：主用途自然出现完整已结算且usage可信的length时，端点是否接受精确partial历史或整批regenerate派生视图，后续完整响应能否回到原SDK/工具契约。模式由实际响应形态决定，不能给模型伪造截断、拼工具参数或主动重启整题。只证明实际触发的模式和工具闭合；另一个模式未触发就保留未覆盖。

**次数**：1逻辑CHI run，逻辑SDK step至多50；物理 `main+confirmation+continuation≤50`，每链continuation≤1、每run≤2、confirmation≤2，summary0、患者0。两次continuation与两次confirmation均发生时main≤46；不是50+2+2。每次失败/未采用续写仍计入。

**成功证据**：原length响应/可信usage先留证结算、许可parent/root/history/response hash、准确mode/ordinal、真实continuation wire与响应、完整批次原门禁和下一请求工具结果闭合。带工具的原length整批零accept/dispatch；完整新批次才执行。保存context/wire/recovery trace、journal/seal、物理请求与逻辑step映射。不能证明稳定业务改善、另一恢复模式、患者确认length可恢复、摘要组合或官方分数。

**未触发/停止/清理**：一次自然run在正常终结或原50/时间/失败界限收口；无length则“未触发，恢复兼容未覆盖”，不追加run。第二次length（同链）、非主触发、未知usage/网络/取消、history/protected变化、超预算、坏工具/重复写/落盘失败按原错误停止，无第三笔接续、无摘要救场。收尾证据与S相同，确认无跨患者/越界写；不明工具副作用或清理失败阻止任何后继。

**需明确批准**：G0对R关联、接线后的精确config/hash、一次payer/最多50HTTP、恢复用途及同账许可/清理；不因B或S通过自动获准。

## 6. H：正式Harbor路径的后续准入准备（真实次数0）

当前离线已有本候选release/preflight、资源身份、实际文件供应检查、harness正常/失败抽验；旧U报告仅提供其固定候选上的真实Harbor组件+合成HTTP证据。`supply-plan.offline.json`的 `/tmp` 状态路径与MCP主机是离线布局检查，未连接MCP，不能直接当生产plan。

下一步离线必须固定：最终采用能力（可都保持off）、支持角色/具体公开任务与污染记录、实际Harbor CLI/agent注册类、controller锁/镜像、官方world镜像及供应、模型依赖、空state/新身份B的持久注入、实际公开reference普通文件、owned资源命名/日志回收、取消/失败传播与清理脚本。Harbor的非秘密config中不得放Key；专用控制进程在运行时注入必要凭据，官方患者/判分凭据与Agent分隔。`install()`仍no-op，调用方负责供应，不以模型包启动成功证明已安装完整官方环境。

真实最小正式路径拟每支持角色最多1逻辑Trial，优先复用预先冻结且尚未污染的Z5任务；每run一般共享50+辅助10≤60，provider/payer无患者则≤50，需B时另计≤6。**这些是后续范围上界说明，本文件未选正式任务/生产plan、未请求这3次许可。** CM采用开发Go患者只能标开发模拟器条件，官方Anthropic患者和judge另需合法环境/授权；默认off的GoChiHarness没有两开关透传，如最终采用则需独立包内接线/新身份/新B。官方reward仍null。

## 7. 分层结论与审批文本

| 结论 | 取证要求 | 本提案边界 |
| --- | --- | --- |
| 新身份coding兼容 | B真实工具往返+新receipt+已知usage | 只申请第一步时不做CHI |
| 摘要/恢复端点兼容 | S/R实际触发，真实wire接受及后继闭合 | 未触发写未覆盖；不凑齐所有模式 |
| 摘要忠实度 | 逐项对照原source的事实/否定/遗漏/不确定性与行动归属 | 可对S已产生材料离线分析，限定该样本；不能据schema通过升级 |
| 净费用收益/业务效果 | 固定条件、完整用量和全部失败分母，纳入summary/continuation成本的对照 | 本轮不申请额外off/on、Y、付费临床或复测；S/R单次费用不能证明净收益 |
| 正式复现/官方分数 | H完整供应/真实Trial/状态清理，官方judge/主办方结果另证 | 本文件未授权H或判分/提交 |

若将来三个阶段均分别获准且候选不变，上界为1B+2CHI、**106物理HTTP**，不是本次一揽子申请。当前推荐的可直接批准文本为：

> 同意保留payer-010 round1的结果/token未知及不完整费用，不修改旧pending、不认定零发送/已结算；本决定仅关联候选清单SHA1846d79c…及eval-vprep-20261104、上述新state，允许执行vprep-b-001一次coding-B、最多6物理HTTP，参数/用途/记录/停止/清理按本草案。对旧eval-abl-on2的历史授权缺口仍保留，不回写已获准。暂不授权summary/recovery探针、业务C、患者、Harbor/Trial、判分或发布。

若用户希望先取得可信结算记录，选择G0路径1并暂缓B；不能把无答复或PR合并视为路径2同意。S/R须在包外接线审核及具体config/hash完成后再次分别决定；未达依赖不执行。任何新unknown都停止本evaluation及涉及同账户的后继真实验证，保留原账/失败/费用并继续离线工作。
