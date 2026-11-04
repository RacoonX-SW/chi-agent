# 计分相关离线加固：实现契约与验收

本文件只定义未来实施和独立复审边界，不表示缺陷均已复现或功能已实现。范围/权限见[proposal](proposal.md)，勾选见[tasks](tasks.md)。不得读取隐藏答案或用旧局部verdict推断官方分数。

## 1. 源码事实、假设与已有修复

| 项 | 可核对事实 | 不能据此推出 |
| --- | --- | --- |
| P0旧例 | 后继学习记录明确payer002为`index`可选字段兼容问题；`go_chi_contract._canonical_calls`已有显式规范化，协议其他未知字段仍拒绝 | 当前存在一个未修“阶段不可用fatal”；应统一捕获错误变软 |
| 当前MCP错误 | `go_chi_mcp.MCPBridge.invoke`已返回受校验的业务错误，保留`returned_error`及来源；部分程序拒绝也已有结果闭合 | 所有错误都会杀run；无需区分结构、语义及未知副作用 |
| P1旧例 | `go_chi_guidance`已有instruction点名后续阶段的指导；payer004曾走MD，但只是已见开发证据 | 所有任务都必须MD；新硬清单能把剩余局部false变为官方通过 |
| P3状态来源 | `go_chi_state._apply_status`检查read/returned/scope，未显式区分业务状态读和本地文件读；`can_claim`看最后一次mutation，包含文件写 | 已发生所有跨类型误接收；未经反例确认就改全部状态语义 |
| 最终文本 | runtime对claim违例/未知有检查，未强制所有final_output都先claim；finally已有completion机械报告 | 再造一个同名检查器就能提升分数；所有未claim结束都是bug |
| 正式入口 | 包外operator有互斥开关；`GoChiHarness`当前命令无摘要/恢复开关，`install()`是明确的no-op供给契约 | 默认off路径有bug；可以静默启用恢复或自动下载安装 |
| D诊断 | entry失败时重写精简run_log，可覆盖runtime已有字段；原wire/journal仍在 | 旧账或原响应丢失；可因此改写历史文件 |
| P2/P5 | 开发Go患者辅助10次，与官方患者供应分开；context为byte上界估计；900秒准入、240秒主read及其他外层窗口不同 | 第11次正式患者交互必失败；估计token是真实token；1380秒都是可发新请求的时间 |

主要调用点：`scripts/go_chi_state.py`、`go_chi_tools.py`、`go_chi_runtime.py`、`go_chi_contract.py`、`go_chi_mcp.py`、`go_chi_entry.py`、`go_chi_harness.py`、`go_chi_delivery.py`、`go_chi_policy.py`及包外`role_operator/role_runner`。这是必要导航，不是授权把所有文件都改一遍。

## 2. A：完成来源、读写类型与退出接缝（P3优先）

### 怎么改

1. 先用合成case/工具结果冻结反例，区分业务资源状态、手册/政策证据和文件交付物；保持已有`effect=read/mutation`及写安全检查，新增完成判断的语义分类，不直接把文件写降为neutral以绕过unknown/claim保护。
2. 明确哪些同角色公开MCP读能作为指定case的业务状态来源。清单从固定公开catalog/schema/工具契约列出精确canonical名称并写入独立测试；不能由模型指定，也不能笼统认为所有MCP读都是状态读。政策查询和目录/手册/普通文件读可作其他证据，不能单独证明业务终态。未知类别按缺证据返回，不自动补成业务读。
3. `_apply_status`/完成检查拒绝错误类别、错误case、陈旧或非returned来源，反馈可定位的有限原因，不能把私有正文或任意异常插入错误码。报告展示业务状态来源的call_id/tool/kind/scope/顺序、最后业务写与文件写、缺少哪种回读。只显示程序可证的事实，不推断临床批准或官方结果。
4. 最后业务写之后需要相应业务资源回读；随后正常保存文件不应仅因其序号更新而强迫一次无关业务回读。文件落盘及未知写有自己的证据检查，不能借分类变化跳过。只有文件交付/只读任务不应被新规则无条件要求不存在的业务变更。
5. 复用现有completion评估，在claim反馈、成功/受阻的最终诊断中一致展示；避免重复实现两套判断。当前final_output不必claim的边界须明确保留。**本卡不引入最终文本后的自动补发、Runner重启或新硬门禁**；不能仅把run标failed就宣称阻止提前结束。若提出SDK内部纠正循环，先交独立有界规格，不在本轮实现。
6. 必要时补guidance及工具描述，明确文件交付证据与业务状态证据的用途。已有plans/gaps可提示未完成项；不为这张卡引入P1的新义务抽取schema。
7. 若report/persisted task-state语义或字段改变，显式版本化，说明旧格式如何只读解释；不按新规则追溯否定旧run，不迁移/重写旧task-state或accounting。历史v1报告保持原语义。

### 怎么验收

- 同case正常业务写→相应新业务读→状态更新→claim可记录；同一流程最后保存合法交付文件不产生无关业务回读要求。
- 新文件读、政策读、目录读、错误case读、旧业务读、returned_error/refused结果不能冒充新业务状态；拒绝更新不得部分修改state。
- 业务写后仅读文件仍缺业务回读；已经业务回读而交付文件写失败/效果未知，仍按现有规则拒绝虚假完成，不能借分类逃逸。
- 只读/仅文件任务与无mutation的合法路径不被一律判失败；不以model自填文本或case_id证明来源合法。
- unknown写、跨患者/case、claim后的写、重复写保护与既有预算原样有效；保留旧schema/旧历史反例。
- 模型直接输出final_text而未claim的合成路径：报告如实表达机械完成/缺证据/受阻，与同状态claim诊断一致；无额外HTTP、无Runner重启、无自动补动作。若仍不能防止提前退出，报告明确列为剩余行为限制。
- 实际SDK+MockTransport至少覆盖一条正常及一条错误来源/结束路径，不能仅断言配置对象或mock掉状态校验。

## 3. B：工具契约对齐与有界错误分类（P4，条件性P0）

### 怎么改

先建立所有自有local工具的schema/description/实际接受条件对照表，覆盖路径、role/case绑定、参数类型和界限、状态来源、只读/写/unknown前置条件。MCP只核对公开名称映射、schema及我们控制的wrapper错误处理，不扫描官方隐藏实现/判分规则。

发现不一致才最小修改实现或description；以公开承诺和安全契约选择修哪一侧，不为让测试通过放宽权限。可共用同一公开规则来源，但验收正负例必须独立构造，不能从同一实现生成期望值。不能新增按题的phase过滤器。

P0先核实错误实际发生层：协议结构/调用ID/参数schema→guard整批预检；业务前置条件→已验证工具调用的结果；传输/副作用未知→原停止门禁。既有`index`兼容和业务错误返回只做回归；没有当前未修反例，就交回“不改及理由”。

若确有**通过全部协议校验、未派发且可由可信公开业务状态判断**的拒绝错误被误判fatal，可在本卡有界修复：程序拥有拒绝原因与计数，每个tool/args/相关业务状态指纹最多2次、run累计最多3次；超过原样停止，不因换工具名或中性读取重置累计次数。既有停滞主要处理重复读，须先确认是否覆盖refusal事件，不能仅复用变量名。每次拒绝写入完整tool结果闭合与同账证据；后续正常模型请求仍占50，不是HTTP自动重发。实施前冻结新增原因枚举及兼容读法。

混合批次必须先完成整批结构/schema预检，之前零派发；不得先写后发现后半项无效。不明依赖或副作用的批次不能伪装成安全可恢复拒绝。不把schema错误、未知工具、重复ID、未闭合历史、角色/case越界、取消、未知usage或持久化错误降为软错误。

### 怎么验收

- 每个local工具至少一条合法和边界非法输入，覆盖读/写/编辑、PDF读取、各role目录/共享路径、source版本及claim条件；确认描述承诺的有效输入确实被接受。
- 实际本地工具/bridge/guard接缝反例，不只字符串断言；name规范化碰撞、重复ID、错schema、坏JSON、未闭合批次仍在任何工具派发前fatal。
- 可选合法`index`被规范化；其他未知字段、bool/负index等保留原拒绝，不借旧修复开放全部未知键。
- 现有MCP业务错误返回后，tool历史闭合、模型能在同一Runner选择合法下一动作；对应合成已结算响应仍计使用量。
- 仅在新P0分支确需实现时：相同指纹/交替工具/相关状态变化及run总上限、refusal不派发、批次原子预检、预算耗尽、取消和落盘失败都覆盖；不得清guard.error、伪造settled或重启Runner。
- 仅证明协议/工具可用性，不证明业务分支选择正确。新恢复分支的真实发生率和分数收益仍未知。

## 4. C：正式配送与最终采用配置（Z6离线前置）

### 怎么改

核对干净导出包下任务instruction→role/MCP工具→模型设置→状态/日志回收的供应责任与实际字段；task-role关系只依公开任务元数据和canonical工具目录，不按task ID决定业务动作。固定官方源码/依赖/镜像/公开工具参考、合法资源供应、只含Agent所需凭据的注入接口、空日志及有明确准入的持久state/B供应。`install()`的no-op不是bug；调用方缺供给就明确失败，不加网络自动下载/Key搜索。

正式包不含开发operator/患者broker、旧账、Key、受限手册/数据副本或调参轨迹。CM正式患者供应与开发Go模拟器分列；不能据CM004的10次辅助用量提高正式患者额度或宣称官方模拟器兼容。已有干净包/组件证据可以按实际身份复用，不为填表重复重建所有旧环境。

最终开关默认保持off。E明确补齐摘要v2的包内/开发/正式透传与版本/互斥检查，但不默认启用；不能把包外接线当正式适配已完成。**除E明确规定的摘要开关外，本卡不新增其他能力开关。** 主请求输出恢复的正式接线仍在未来拟采用时另立任务，本卡记录其现状。

### 怎么验收

- Docker/Python3.12禁网、无Key的隔离包preflight真实返回身份；真实identity/profile不能打桩绕过，不挂旧源码/runs冒充干净供应。
- 用真实Harbor组件的假environment/MockTransport离线走到实际entry参数或明确缺供给停止：三role各有正常装配与关键缺项反例；无真实world/Trial启动或请求。
- 缺/错task-role、MCP工具面、公开reference、可写state/log或依赖按明确阶段报错；缺凭据的负例不得从宿主env搜索其他Key。
- 最终off配置的正式/开发入口一致；E支持的v2透传实际到达launch及guard，未支持的主恢复开关如实列出；如果包外controller依赖尚未锁定，写明重现缺口及最小补齐建议，不全面升级依赖。
- 包manifest逐成员、runtime、旧evaluation及release wrapper的source_commit变化分别比较；不把wrapper改变混成内包改变。
- 固定SDK/Harbor输入、结果/trajectory/context、失败传播与owned资源命名/清理的离线证据；真实兼容、取消在途和官方成绩仍未验证。

## 5. D：安全诊断保留、已有计划指导及余量测量（P5/P1轻量部分）

### 怎么改

entry在runtime已写有效run_log时，保留已有受支持版本、有限安全cause、计数、usage及completion/context信息，另补外层失败；无有效日志时写明确fallback。读取须有界、校验schema/允许字段，不原样合并任意文本或未知键。保留首个失败与cleanup/日志失败的层次，不覆盖wire/journal或旧run文件；不把无法落盘当成功。

用已有plans/gaps与guidance提示公开instruction明确要求、条件分支、剩余工作和受阻项，不要求全题MD或某种结果。此为指导优化，不引入新的“义务清单”“instruction引用”持久schema或硬claim门禁。若未来新增P1：需分别处理引文出处/条件与否定/覆盖完整性/完成证据；16项只能作为待验证软上限，溢出不得静默截断或直接判trial失败；final_text绕过反例必须纳入独立设计。

包外只读提取已选必要run的元数据，按候选/角色/任务/模拟器条件分组，不能混合历史版本当一个样本：实际prompt/output/reasoning token、byte估计及比例、模型与工具耗时、总墙钟、新请求准入余量、主/确认/辅助数量、重复读与完成拒绝。默认先用现有CLI/报告，不为盘点新增包内分析功能。没有九题数据就写未测；小样本不发布虚假的稳定p95或私有通过率。

### 怎么验收

- runtime完整日志+外层异常时，安全cause/计数等有效字段保留，primary与cleanup错误分别可见；无日志/损坏/过大/未知schema日志有明确fallback，不掩盖实际失败。
- 合成secret/任意异常内容不进入公开安全字段；原wire/账/seal在核查前后字节不变。旧日志读法和新日志版本语义分开。
- 指导对可选MD、患者拒绝/不适用/受阻等公开分支保留合法性；不用task ID或旧false值生成要求。缺证据的计划不得显示为“程序已验证完成”。
- 测量至少复核一组真实已存元数据与一组缺字段/失败/unknown合成样本；费用不完整保持null/标记，token未知不填零；程序分析只读且绑定同一hash快照。
- 报告明确240主read、300主I/O、900CHI准入、确认/患者用途窗口及1380/1500/2040相关层，按实际调用路径解释；不把byte估计称为真实token，不从单样本直接修改任何上限。
- 少一次拒绝/读/HTTP不等于整题得分提高；不以本卡改写既有14/14、26/28等局部结果。

## 6. 摘要问题的解释与本轮不改范围

摘要是一次独立模型调用：旧历史作为输入，模型生成摘要作为输出，然后下一main才能采用。大输入窗口和单次输出8192是两个约束；本次input=212561，而output=8192且reasoning=8192、最终content为空。不是输入被截成8192，也不是程序把输入上限改成输出上限。尚未产生可验证摘要，所以没有安装checkpoint，原历史未被替换。

既有输出恢复适用CHI主请求，默认关闭；仅在可信完整length响应、usage已结算、工具未派发且历史/预算满足时生成许可。无工具保留合法部分上下文再请求，有工具整批零接受/派发并从闭合历史重新生成；每链≤1、每run≤2，均占50，不保证模型语义连续。摘要用途明确排除，且首版与input_summary互斥。S探针只开摘要，故不能据本次失败判断恢复无效。[固定恢复契约](../project-completion/output-recovery.md)及[摘要观测](../../../reviews/summary-failure-diagnosis.md)保留各自含义。

方案B是限制送去摘要的选区体量，尚未实施；缩小输入不保证减少reasoning或得到正文，仍不在本轮。用户后续要求处理摘要截断，故增加下节E独立冻结摘要接续契约；它复用有界恢复思路，不直接打开现有主请求恢复器，不降high或提高8192，不因剩余额度追加探针。

## 7. E：摘要v2的最多一次有界接续（用户追加范围）

### 7.1 目标、版本和请求数

这是新增能力，不是修复v1在设计范围内的length停止。`chi-input-summary-v1`及已有S失败保持原义；新增显式版本`chi-input-summary-v2`，默认关闭，仍与`chi-output-recovery-v1`、Y shadow互斥。主请求恢复的旧mode/用途/次数不变，不把summary交给它的普通工具恢复分支。

v2每run最多1条摘要链，根请求内部`purpose=summary`最多1次；根可信length时，内部`purpose=summary_continuation`最多1次。用途只用于程序许可、journal和trace，不往外部API加任意purpose字段。传输重试仍0；这次派生请求是明确披露的程序恢复，不宣称“无任何自动追加”。

所有主/确认/主恢复/摘要/摘要接续物理请求合计≤50，辅助仍≤10，确认≤2；主恢复因互斥在v2 run中为0。两次摘要相关请求各自max_tokens=8192，模型/端点/thinking/high不变。总共可能生成最多两次8192，不是把一次上限暗改成16384，失败和未采用请求全部计入usage/费用。

进入v2根摘要前，至少剩3个共享名额：根摘要、可能的接续及至少1次后继main；即已用共享请求≤47。无法预留时在发根摘要前按明确限额错误停止，不先发再追加超额名额。未触发摘要的原main路径不受这项预留影响。此保守规则可能比v1更早停止，需作为新增取舍披露。预留1次main只证明有一次后继机会，不保证整题有足够剩余轮次。

### 7.2 唯一接续条件和派生wire

根摘要响应必须同时满足：正确route/model/assistant结构、HTTP200、完整可信JSON、usage先成功settle、`finish_reason=length`、无tool_calls/function_call及其他不受支持的内容；content或reasoning至少有一个合法非空字符串，可作为未完成上下文。未知usage/结果、网络错误、取消、持久化失败、任何工具调用或不可解析响应均不接续，沿原门禁停止。两者都无内容不发空白恢复。

程序在首个length被可恢复分支识别时进入v2状态机，不能先设置fatal再清除guard.error。现有v1仍原样拒绝。恢复前后再次检查源历史、selection/protected、程序工具记录/claim/case绑定及原run截止；期间不派发业务工具，不换source、模型、选区或阈值。

接续body由程序确定性派生：原根摘要的system和user（含原source、schema、selection/protected hash与允许引用）保持字节/规范化绑定；追加真实根响应的合法assistant部分reasoning/正文表示，再追加固定程序指令，要求完成推理后**返回一份完整的新候选JSON对象**。不得让模型直接拼接JSON后缀；部分正文可作为未完成上下文，但根正文与子正文不拼接成安装候选。不得把reasoning当最终摘要，也不宣称恢复模型内部思考状态。

固定接续指令应明确：旧source/保护真值/引用范围仍权威；部分内容不证明任何行动完成；不调用工具、不新增授权；仅返回原输出schema要求的完整对象。精确常量及body派生算法进入新版本身份，源引用与格式均可由严格reader独立重建；不从模型响应中接收新指令。继承route与合法请求头，不带失效content-length；不增加tools、response_format或API私有控制字段。

接续wire重新计量并按用途预留8192，不能只检查根摘要体量；源历史与部分reasoning一起超出原context预算即停止，不截字、不缩选区重试。总截止沿用原run起点；length不是超时重发的理由。

### 7.3 候选安装、证据及失败收口

根若正常stop且完整有效，沿正常v2校验安装，不发接续；根若stop但候选schema/引用/保护/hash/节省量不合法，直接停止，不借接续修复任意坏JSON。只有上述可信length允许接续。

接续必须正常stop、完整独立候选通过原schema/echo/来源引用及保护真值检查；最终派生main视图仍须节省≥1024 bytes、通过原context预算、保留最近闭合批次及完整SDK历史/工具保护。候选只作为不可信任务上下文，不升级语义忠实度。接续再length、空正文、tool_calls、非法候选/费用来源、unknown或落盘失败均立即停止；没有第二次接续、重新选区、原题重启或静默回退到无摘要main。

新增一次性permit与v2 event/evidence：至少绑定contract、run/identity、根round及原request/response evidence hash、selection/protected、派生wire hash、child round、采用的最终response round/hash和消费状态；准备→reserve/消费→settle→候选→checkpoint→后继main的顺序可严格审计。reserve前未消费许可，reserve后即使失败也不可重用。v1的`summary_round`单响应含义不重解释；v2明确root、optional child、candidate response及projection关联。主恢复permit不能用作摘要permit，反之亦然。

strict inspect、seal、包外run-summary及trace都须识别v2与新用途，逐笔计数/费用分列（main、confirmation、summary、summary_continuation），未知不能补零。原始body/evidence不修改。中断/已settled但无安装等状态仍可检查；不能只为让inspector通过改账。原v1 S证据用只读原hash核验、完整集合不变；新identity不能复用旧B。

### 7.4 开关接线和有限实现边界

包内entry接受显式v1/v2，不给旧profile版本静默升级；保留v1规则/常量及旧记录读法，新策略版本单列。包外operator与runner接受精确版本、默认不传，仍拒绝与主恢复/Y的组合。正式harness新增可选`CHI_GO_INPUT_SUMMARY`，缺省不传，只接受两个精确版本；在读取凭据及模型派发前拒绝空值/未知值，向entry仅透传一次。harness不转发Y，不顺带新增主请求恢复正式开关。

实施涉及原summary/guard/journal/runtime/entry/profile、strict reader/summary工具及必要外部接线；允许复用纯计量/派生/证据原语，但不统一重构所有恢复状态机。精确event字段及有限错误码在E的首个规格提交/实现自测中固定，遵守上述绑定和验收，无需逐字段问用户；不得把语义不清留给真实探针试错。

### 7.5 必须独立验收的正负例

- 根stop合法→0接续→安装→真实SDK下一次MockTransport main含checkpoint；根stop坏候选→停止、0接续。
- 根为本次S形态（reasoning-only length）→已settle→1接续→子stop完整候选→安装→main；另测length+部分正文但子返回完整对象，禁止拼接后缀。仅用自造候选证明协议路径，不冒充原真实失败已被修好。
- 根/子带工具、错model/角色、非法字段、缺usage、取消/网络/超时、无内容、source/protected变化、坏hash/引用、子length/空正文/坏schema、落盘故障：无额外工具派发、无第二接续、无错误checkpoint；未知pending按原规则保留。
- 直接调用/重复使用/跨run或跨用途permit、错父/root/response/wire、消费后的再次reserve等均拒绝；recovery与summary的permit不可互换。
- used=47可至多根48/子49/main50，used=48时触发摘要前不发根；完整wire超预算或时间余量不足不发送；未触发摘要不扣虚构请求，正常stop根不占子名额。
- SDK逻辑step与物理用途分别计数；根和子失败费用都在50分母内。合法tool历史及protected/claim状态不受接续影响，子响应不得直接成为业务工具批次。
- 实际operator配置/runner/entry/journal.launch与正式harness→entry的禁网接缝：精确v1/v2各透传一次、默认off、未知/空值/双开/shadow在凭据/模型派发前拒绝；不能只断言配置对象。正式entry使用临时合成B/state或明确无B负例，原state不写。
- 原v1摘要、主恢复的两mode及旧inspect/receipt/seal测试继续通过；原S120文件的只读集合/hash不变。新包真实identity/preflight/profile一致性及包成员比较，不mock核心校验。
- 原S响应可只读回放证明旧v1仍按原规则失败，以及v2进入允许的length分类；未实际请求端点，不能写“恢复成功”。真实兼容、摘要忠实度和净费用收益分别保持未验，未触发的真实探针也不得追加到触发。

## 8. 固定候选、独立审核和完成标准

每卡：现状反例→最小改动或不改理由→必要Docker/Python3.12禁网测试→固定提交。原始证据只读/本地保留；测试用自造case/文档/响应，不能拷贝隐藏期待结果。对低影响纯文档变更不新增镜像或镜像实现的测试。

影响guard/状态/序列化/持久化、工具入口或供应的改动须在实际接缝做独立正负例。身份/包比较、隔离包真实导入/preflight及profile一致性不可用mock替代；SDK HTTP仅用MockTransport，任何网外请求均不在许可内。测试资源独占，测试输出写隔离目录，不写真实state。

各卡适用检查通过后才跑一次必要受影响集成回归；新增失败/修改才重复相关检查，不默认每卡重跑全历史。已知anthropic环境缺项和skip单列，不写全绿。GPT对固定SHA按本契约复审；DeepSeek自测、commit、push或PR不等于通过。

完成必须有：A–E各项处理结论、实际测试证据、默认off与固定参数证明、v2新增用途/一次额外请求如实披露、内包/外层身份及旧B适用性结论、旧证据原样保留、未解决项/启用能力的额外准入；不要求凭本轮证明临床/官方得分或摘要/恢复真实兼容。最终候选真实B/九题的输入、状态、资源、费用和停止条件另行具体批准；离线通过不能自动启动。
