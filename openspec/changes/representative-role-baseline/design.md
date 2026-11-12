# V 有界设计

## 基线与用户决定

2026-10-30实际核对PR #25 merged，merge/fetch后最新origin/main均为 `c429ebec4d650fa56e65f2b2ded0a52851eb8c21`，工作区干净；从该点建立 `codex/representative-role-baseline`。一个Terra/high实现，主代理规格、选题、独立审核、教学与Git。

用户明确选择：医院另一流程先覆盖不提交/关单分支，复用单角色runner，仍标注为provider_new_referral，不声称不同医院任务族或E2E已实现。payer排除需要额外对话模拟器的P2P。随后用户明确授权本地CM患者模拟使用OpenCode Go/DeepSeek，并要求提交官方时保留Anthropic默认；只有该模拟用途恢复，Claude和付费临床评审仍暂停，不能通过绕过对话或模拟判分改成成功。

固定源 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，数据revision `5ce88104df2a91e057619eb70fb51f56fc5949eb`；公开索引101项、SHA256 `8751f9ae3132a861f389d85d66ba0cca5a52fddb17fe3e2ab4dc92f2804ccc91`。选题仅使用family/actor/kind/contract/terminal/path/输入文件数等公开元数据，不读title、instruction excerpt或fixtures答案择题。逐类按字典序第一项，明确排除历史已用/已读题和兼容依赖；原选择记录保存，不因结果换题/重复刷过。选择完成后先固定资源路径/字节/hash，再补读相关公开输入及操作者初始化契约。

## 固定范围与当前执行清单

- 三个代表题各一，不扩量；医院只覆盖关单分支，payer常规UM，CM全流程目标只做无模型接线/依赖盘点。
- 三个代表题的正式业务C **0**，Claude0、付费临床评审0。用户新增患者模拟授权后的最小真实Go清单仅为：当前独立审核候选自己的coding-B至多1次（6请求/1024）及一个自造、无临床资料的两轮患者对话probe（至多2响应），总上限8；不得把unused数量挪给新题/重跑/评审。先完成下述开发专用模拟器设计、离线/真实历史副本独立审核，再固定run/包/配置及载荷hash，显式接续旧历史后执行，不预填通过。若无需真实调用或未达到条件，保留0及具体未验证项。
- 先固定候选和主代理独立审核，再用真实官方源码/现有镜像对选定资源做无Key、无外网的新世界启动/角色只读MCP/初末导出/清理。每个代表场景最多一个最终独立环境预检；工程前置失败单独保留，不作业务重试或成绩。
- 代表题世界的准备探针不执行CM业务对话，不注入模型/judge Key。开发专用模拟器另用自造persona做独立两轮probe，不是CM代表题解题或完整trial；预检失败停止，不调用模型试错或静默替换。不得把“有工具schema”或开发模拟器通过写成业务实测/官方成绩。
- 后续真实批量须在后续规格固定候选、自己B、最多三个任务各一次、条件和停止规则，并按实际日期复核十一月隐私。当前不作此授权清单，不自动rebind真实历史。

## 冻结任务与最小资源

最终选择在任何详情/下载前固定于忽略的 `runs/representative-role-baseline-root/evidence/task-selection-v2.json`：

| runtime role | frozen task | family / contract | public input PDFs |
| --- | --- | --- | --- |
| provider | pa_t032_t032_o002_p01_new_referral_provider | prior_auth_provider / contract_v5 | 0 |
| payer | pa_t011_t011_o003_p01_intake_payer | prior_auth_um / contract_v3 | 4 |
| cm | cm_afib_moderate_anxious_001 | care_management / cm_v4 | 0 |

医院关单兼容元数据候选3项，payer非P2P且排除历史/本批其他PA同clinical case后11项，CM25项，各取字典序第一项。payer首次候选t008与历史已读provider_t008同case，v1原记录保留；在未下载/未读详情时加入跨family同case排除得到v2，不依据任务结果调整。另排除本批provider t032对应的payer case，避免同批角色复用。CM代表题仍只做离线目标；后续新增的Go患者probe使用自造材料，不将其写成该代表题live兼容或业务通过。原Anthropic调用继续暂停。

只下载所选task必要的instruction、task.toml、公开tool reference/输入PDF，以及world初始化所需的manifest/expectations/world和被其引用的必要材料。先从固定revision列文件元数据，再固定明确下载清单；不下载全部101题、不拉最新revision、不静默升级SDK。fixtures/world/expectations只供授权初始化/运行后的操作者，不传给Agent；公共PDF来源必须能与所选输入元数据/manifest对应，不能把评分目录PDF当输入。

固定文件清单为：provider5个基础文件；payer5个基础文件加所选 `fixtures/request/` 下4个官方输入PDF；CM的instruction/task.toml/manifest/expectations加共享 `care_management/shared/tool_reference.md`；另PA provider/payer两个共享world及CM共享 `healthverse-cm-curated25-v1.json`。不下载judge/solution/tests目录。PA world优先从原固定镜像按官方Git blob/字节数核对后复用，不重下；其余按显式下载清单取得，先核对blob/大小并计算SHA256，后解析内容。

payer的request PDF虽然在源数据fixtures/request下，固定官方 `ServiceContext._materialize_incoming_request_pdfs()` 会复制到payer角色workspace `incoming_request/`。优先验证该公开投影与已有workspace allowlist/锁定PDF读取器可用，避免无必要增加Agent可读fixture范围或新输入接口；不能把整个fixtures挂给runner。

现有world镜像仅有PA provider/payer世界和t018，CM world缺席。使用只读、hash绑定的最小资源投影，不改固定vendor/镜像内原源码；如需要派生环境，只加固定所选资源，明确新镜像身份且不发布含受限资产的镜像。不重做G/H，不改SDK/PDF锁，所有下载/安装/调试/测试/执行均Docker。

## 允许的最小代码接线

1. 包外role-aware资源manifest与预检：明确family、task actor→runtime role（care_manager→cm）、task目录、world来源（shared/per-task）、世界hash、公开输入与初始化/评分材料的分界。所有path/hash/schema/角色矛盾在Key、模型/世界副作用前拒绝，禁止仅替换provider常量或默认回退世界。
2. 包外无模型环境预检/导出：复用既有Docker控制/固定原源码bootstrap和MCP；按角色选择唯一端点、核验实际世界/资源/导出来源，CM显式处理per-task world路径和导出结构。捕获provider/payer资源表与必要CM资源，不用只看目标的export证明全局无变化；停止进程后留终态与清理错误，按本轮owned身份清理。
3. 若公开payer输入依赖本地PDF而现有allowlist不可读，最小扩展显式公共输入manifest/只读路径，预检绑定role/task/files/hash，禁止链接、越界、重复/任意目录、fixtures/judge/hidden或非预期文件。复用锁定PDF读取器；旧无新参数入口保持旧边界。工具应能按公开输入清单发现/读取自己的文件，不因此看见评分材料或其他角色workspace。先用合成资料测边界，不能按实际题文改策略。
4. 角色纯检查调用固定官方入口且显式禁用semantic judge；若cm_v4独立branch/导出不支持则如实“未验证”，不能调用默认verify_task/WorkspaceJudge/Claude来填空。无模型初始世界检查不是任务完成成绩，不输出reward=1或0。

本轮仅接受所冻结的shared world；per-task world输入显式拒绝，不用共享world静默回退。后续需要per-task来源时另冻结其路径/初始化和导出契约。CM导出按固定`WorldService._export_cm_state()`的原始形状处理，世界身份来自实际挂载的fixture manifest与world文件，不能给export补造world_id；PA原捕获契约不放宽。

优先新增包外小模块/命令而非改写旧provider操作者；确需扩展共有入口则保持旧config/资源兼容并给明确类型。保留原evaluation_entry live拒绝，既有Go SDK/工具循环、50共享请求/最多2确认、8192/32768、B6/1024、患者门禁、record_only/null cap、费用缺项null/warning、零自动重试/回退均不变。不得给agent硬编码期望终态、病种答案或隐藏rubric。

## 用户新增：本地Go患者模拟、官方Anthropic默认保留

### 模型、接口与隔离

固定官方 `cm_outreach.send_message()` → `PatientSimulator.generate_response()` 使用 `anthropic.AsyncAnthropic`。开发层以显式opt-in的world bootstrap/类适配调用独立broker；不改vendor文件，不全局替换Anthropic SDK，不改判分器。无opt-in时必须仍使用原PatientSimulator，禁止因存在Go Key自动切换。开发bootstrap、patient adapter、broker及其配置都不进参赛bundle，官方world由官方正常提供，Anthropic默认与源码hash保持原样。允许在通用runner保留一个默认关闭的注入接口及必要通用账目验证，不允许参赛CLI/环境变量自动启用本地开发模拟器。

开发patient adapter复用固定官方 `build_system_prompt()`、patient_profile、每条message的flipped_api_role、STOP解析和SimulatorResponse形状；send_message原有回滚、时间/轮次、持久化与终止语义仍由官方service执行。模型改变会改变患者行为/难度，必须记录为本地开发条件，不与原版模拟器结果混作官方分数或Agent单项收益。此功能验收后集中教学，单纯模型参数调整不另开课程。

Go固定 `deepseek-v4.1-flash`、`https://opencode.ai/inference/go/openai/v1/chat/completions`，使用已有锁定OpenAI SDK。患者模型与Agent/确认分别记录；保留稳定每段conversation session header和自有user agent，不冒充官方已验证coding client。为复用已实测Go生成契约，患者生成采用thinking/high、8192输出上限、read360/I/O420秒，不沿用Anthropic的1024作为DeepSeek reasoning+输出预算；这属于本地模拟器条件，不改官方限时/参数。拒绝tools、路由/参数篡改、非stop或空响应，已知usage先结算再拒绝内容；不人工截取/伪造患者回答，不自动重试/回退Anthropic或其他提供方。

辅助路径的外层等待须完整对齐：world到broker的HTTP等430秒，参赛侧MCP HTTP不少于430秒，MCP ClientSession显式450秒。锁定SDK的ClientSession默认5秒，不能只改HTTP后声称患者链等待已接通；用真实网络MCP配合超过5秒的合成生成验证。上述仅由auxiliary显式启用，普通MCP和原TIME_POLICY保持原契约；后续真正CM业务C的操作者总等待须在其运行规格另绑定，当前不默认扩大三题清单。

官方[Inference API](https://opencode.ai/v2/docs/console/api/inference/)按模型API族区分Messages和Chat Completions，不能仅换Anthropic的base URL；[Go说明](https://opencode.ai/v2/docs/console/go/)仍以coding agent流量为设计用途。用户此前知悉非编码用途未获明确确认，本轮又明确要求并授权开发患者模拟，不能写成官方服务用途已许可；十一月条件仍按实际日期人工复核。

### 单一计费所有者与预算

现有runner整个运行持Q→CHI锁，MCPBridge也在await工具时持dispatch锁。world不能另开同账锁客户端（会死锁），也不能另开不受历史门禁的账根。broker必须与runner/开发probe共享同一个计费所有者和CHI journal，Go Key只在此必要进程安全注入；world保持无Go Key、无外网，仅在本轮内部专网调用broker。

主HTTP与辅助HTTP共用单一异步billing mutex，范围为reserve→发送/读取→usage/证据→settle/诊断；broker不取得MCP/confirmation dispatch锁，不反向调用MCP。固定锁序是MCP→billing，主请求仅billing。broker内部端点有本轮短期能力token、唯一run/session/parent tool关联，严格JSON/字节/调用形状/并发/重放/超时检查，只允许CM患者purpose，地址/模型/生成参数由受审代码固定。token不写日志、不经工具暴露；不是Go Key，不做任意外网proxy。

新attempt以显式版本化契约追加 `patient_simulator` purpose；旧attempt/请求/launch/seal/ack/source archive按原契约逐字节保留，不把aux伪装main/confirmation。request round按实际发送统一递增。Agent主+确认仍共享50，确认最多2；环境辅助请求独立最多10，合计至多60，不能占用或伪造Agent剩余反馈。独立患者probe最多2次aux且没有正式Agent业务C；须有明确probe kind/launch，不伪装B或正式任务成功。

保持全局单一wire pending/费用策略，版本化审计合法的parent MCP tool在途+其aux wire在途关联；崩溃/超时/取消后必须能只读审计而继续阻断，不能把合法嵌套误判损坏或自动清除。aux token/结果未知、异常来源/余额实扣、损坏证据或共享fatal状态使后续主/确认/aux全部停止，即使world把异常返回为普通MCP错误也不继续。费用缺项仍null/warning，三项USD分列，不与native CNY相加。

### 必须先完成的离线验收

- 真实官方persona/session/service状态机与Go adapter的提示/role翻转/STOP/回滚一致；默认Anthropic类不变且不发请求；开发适配不在bundle。
- 同进程真实MCP→world→broker回调不死锁，能力token/角色/parent tool/重复/并发/越界请求在发外网前拒绝，broker正常与失败后完整停止/清理。
- main+confirmation 50、confirmation2、aux10及probe2独立边界与可信反馈，真实SDK合成响应0付费；可信usage先结算、费用缺项继续，非Go/余额额外扣费与新未知都阻断全部请求。
- 当前真实历史完整只读副本：旧ack/来源/seal/wire/账原字节保留，新契约显式迁移、合法嵌套inflight可审计、新未知无自动留档，重复attempt/响应/迁移篡改拒绝。原历史只读，测试不在真账试写。
- 固定候选后主代理独立复验上述边界和U默认接入回归；现有SDK/PDF只读复用，不加未锁新依赖。

### 最小真实探针及停止

通过离线/历史副本审核后，主代理另固定当前包/实现/配置/两轮自造persona载荷hash。载荷仅为自造预约时间对话，无真实或基准患者、手册、隐藏判分；使用固定官方prompt/ConversationSession链，脚本担任测试care-manager，不是参赛trial。最多1次自己的新coding-B（6请求/1024）和1次两轮patient probe（最多2实际响应，总上限8），每个run/attempt唯一，所有失败/用量/耗时/费用留档。患者先STOP则尊重结束，不凑两次。

先审计旧账/唯一旧ack，再按候选显式source rebind、自然取得本候选B；不伪造B/结算或改旧记录，不换账根。出现新的未知、坏证据/未清理或明确非Go额外实扣立即停止，后续probe不再发；无重试、无新自动留档、无挪用额度或扩成三题C。真实SDK接口响应完成也只能证明开发模拟器接点，不算CM业务/临床/官方判分。

## 历史、失败与验收

2026-10-31执行冻结：独立审核候选 `410a5b4f31444afd85f2850986a17d547a90f015`，包manifest `5600fd738481264781cd011b625731bee2b66e9eb64178121ca64d7607bd0af4`，runtime identity `b29d6ecfdb7503fd0caecfd413aa06b8dd09cc6b0d4d71581b5951b33c5b3e60`。固定最小清单 `runs/representative-role-baseline-root/evidence/live-plan-frozen.json` SHA256为 `1d76bb6a8b38b976a9745d11c320cd43be181f2c5838771afa9a6b5bb8b87ea5`，B配置 `5e8b403394a6ca5a8b6c84a284a08e3a64125b14e27803c8004235154335fceb`，patient配置 `41534d59f2394b64f22d60c92877a9972953ae0764d1a0aa19021eb1b7660dad`。第一轮自造请求的canonical JSON hash为 `390285f349ff27d4c4e95f40088dbf9c505e33fd0f27a8f5e2c0b2a36fe74a2a`；第二轮先冻结自造问题和追加已验证患者回复的规则，完整请求含首轮模型输出，只能在运行时留实际hash。仍最多B1（6/1024）+patient probe1（2/8192），不用完不转移用途，不是三题C或内容评审。

原T唯一旧超时留档链已解除有效global占位，旧请求仍未结算；不得重复ack/settle/删占位或重发。原Q/native账不改，CHI只有在候选/旧账hash核对后按原显式来源迁移追加，不改旧attempt，新未知不自动留档。无模型环境与合成账分开，所有成功/失败、资源身份、工具调用/耗时/hash、初末捕获与清理保留忽略目录。Go实际provider用途/十一月条件仍是既有边界；实际调用与结果只见阶段报告，不在规格预填通过。

一个Terra/high自测后停写，主代理固定候选、看diff/调用代码、独立Docker复验：三类资源身份/错误role/world/path/hash、缺资源/坏输入、公共PDF合法/非法边界、实际固定bootstrap/只读MCP与导出、正常/失败/清理、无Key和无评分材料进入Agent。不要编写复述文档的测试，已通过G/H不重复安装。

README只写运行；OpenSpec写边界与场景；学习账本记关键调用链/疑问与下一入口；REVIEW_STATE短摘要更正PR25已合并；详细实际证据集中 `reviews/representative-role-baseline-review.md` 一份。显式提交/推送base=main PR交用户合并，不merge/auto-merge，不新增重复交接文件。
