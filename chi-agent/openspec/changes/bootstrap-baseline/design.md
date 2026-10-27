## Context

当前增量为 K：GPT-6.1 Terra / high 实现、多次真实 C 开发尝试及旧账目/源码身份接续；当前授权和验收身份见 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。复用 Python 3.12 镜像、固定官方环境与已锁 SDK，不重写模拟器或评测器。历史章节中的 G/H/J 范围与旧暂停、5 元、单次限制只表示当时的授权；本轮新授权不启用官方判分，也不代表 F.5 最终冻结。

规划基线任务为 `pa_t018_t018_o001_p01_new_referral_provider`。其输入、静态工具和运行限制见 `docs/task-walkthrough-pa-t018.md`。该文档没有真实评分，不能充当完成基线的证据。

最新安排：用户当前暂缓本地 Anthropic 官方判分，先验证离线就绪、真实工具接入和无评分的 Agent 执行；正式判分留作单独暂缓项。部分 Claude 模拟对话也存在依赖缺口。以下涉及官方 reward/scorecard 的收集仅适用于确实运行了原版评分器的模式。参见 `docs/development-preparation-2026-10-21.md`。

2026-10-24 最新环境约束：项目依赖、下载与执行全部进入 Docker，宿主机不安装项目运行/测试依赖。Docker 内开发、任务调度与可交付镜像的设计见 [Docker 工作流](../../../docs/docker-workflow.md)，覆盖此前宿主机 `.venv` 方案；D0 的开发容器与离线检查在本次恢复范围内。

## Decisions

1. 自有代码与上游分开。上游源码放 `vendor/chi-bench/`，数据放 `data/`，运行结果放 `runs/<run_id>/`；均不跟随本项目公开提交。
2. 检查入口建议为 `scripts/check_readiness.py`，默认不发起模型调用或下载受限内容。检查失败显示具体依赖和解决入口，不伪造连通性。
3. 检查配置只记录存在性，不输出密钥、请求头或携带凭据的 URL。配置中以环境变量名引用密钥，不把值写进证据文件。
4. 基线入口建议为 `scripts/run_baseline.py`。通过 argv 调用固定版本的官方 CLI，不用 shell 拼接用户输入。实际 CLI 参数先查固定提交的文档及帮助信息。
5. 单任务优先采用已拆解的 `pa_t018_t018_o001_p01_new_referral_provider`，通过固定版本已支持的 `cb experiment run --dataset <完整单任务目录>` 选择这一题，使用单次尝试和并发 1。不能借全领域 submission 命令伪装成单题运行。模型和内置 harness 必须由实际可用配置指定；judge 的模型、投票数及实际覆盖设置分别记录，保持可比的官方协议。
6. 每轮真实评测使用独立目录，写实际退出码和上游结果来源。进程退出成功、任务 reward 为 1、以及本地证据完整是不同维度。
7. 运行前配置任务数为 1、有限的 Agent 时间/调用上限；若上游版本不支持某个限制，如实记录，并使用可控的外层超时。外层超时可能留下未知的 provider 请求结果，不能声称精确金额封顶。
8. 基线结束后收集判分与轨迹；Agent 运行期间不得读取 verifier-only 文件或隐藏预期。测试 fixture 不伪装成官方结果。
9. 静态工具说明已核对 8 个命名空间、30 个方法及部分枚举；实时 MCP schema 尚未获取。完整参数、工具实际可用性和返回结构以运行时为准；未观测到的字段不写为已验证。
10. 这一题的任务配置基础上限是 Agent 900 秒、verifier 1200 秒；记录实际生效值和外层限制。超时不是精确金额封顶，真实 API 调用须先确定预算和可用凭据。
11. 准备度按离线、工具连接、真实无评分执行、完整判分分别报告；缺 Anthropic 不使前面所有模式统一失败。正式判分若缺凭据则在付费执行前明确报告，不以自检补官方 reward。
12. 无评分入口须在固定版本上单独验证。已读的 CLI、ExperimentConfig 和 `_build_harbor_command` 未见直接关闭 judge 的选项；优先验证官方服务与 runner 的独立开发路径，不捏造开关，不修改正式评分器。无有效入口时如实交付离线/工具部分，保留运行缺口。
13. 无评分执行保留实际角色工具、任务输入与自主运行要求；不读隐藏评分文件。开发记录与官方结果分开，写入判分未运行的原因及 null reward，不制造官方 scorecard。
14. 判分认证不能只判断 `ANTHROPIC_API_KEY`：固定源码也支持 Claude Code 登录/OAuth，Docker/Modal 转发相应 token。只记录存在性和实际认证验证结论，不输出秘密。用户目前仅有免费 Claude 账号，尚无可用判分路径实测；原配置的 key-only 前提需要恢复实现时审查。另可考察 `collect_all_verifier_checks` 的 `include_semantic_judge=False` 阶段校验分支，作为独立的部分确定性诊断，不能报完整官方通过；参见 `docs/judge-access-options-2026-10-21.md`。
15. 用户已选首轮模型工具接入验证与一次本地开发执行合计按 5 元人民币规划，写代码费用单独记录；本次 D0 恢复不包含付费运行。目标模型/模式及限额候选见 `docs/development-preparation-2026-10-21.md`，未实测前不视为冻结。每请求前核算已用预算和下一请求的输入/最大输出余量，余量不足就停止并记录；未知用量不能按零处理，预算停止不等于任务完成。这是本地开发策略，正式私有评测的边界见下方“本地开发预算与正式私有评测”。
16. 就绪验收拆成官方工具、模型工具往返、干净初始状态下的一次自主任务执行。模型普通聊天成功不能替代所选 runner 中的多轮工具接入；思考模式须核对所需字段和实际请求设置。合成小工具只验证协议，不能当作官方任务证据。测试工具后的业务世界不得未经重置直接充当正式开发执行的起点。
17. 本轮只允许恢复参考基线所必需的最小模型兼容适配、预算和记录代码；自动摘要、后台压缩及自有业务控制器仍属后续改进候选。若固定上游无法通过其扩展点接入，报告具体差异再调整，不把研究伪代码当现成实现。
18. 实施交接分成 D0 离线修复、A 官方工具、B 模型往返、C 单次任务四份稳定候选。D0 可构建并启动开发/离线测试容器，不启动官方任务世界或参赛模型；A/B/C 按用户恢复范围和阶段验收推进。交付身份同时绑定阶段、实际 HEAD 与未提交实现差异；`ready_for_review` 不是验收通过。详见本变更 `handoff.md`。
19. 开发/调度 Python 的主次版本对齐固定官方任务环境，当前为 3.12。同步开发基础镜像、controller venv 与两份依赖锁，并在实际目标镜像中验证；官方任务镜像及资源保持固定身份。安装与检查仅在 Docker 内完成，源码与环境路径分离，复用已有缓存及资源；旧 3.13 验收保留为历史证据，不表示本次迁移已通过。
20. A 阶段优先验证调度容器复用已有 Docker 引擎创建并列任务容器；只有该阶段提供必要的引擎访问。挂载路径须从引擎可访问的源解析，不能把容器私有目录直接作为宿主机路径；网络、任务隔离、结果读取与清理均需实际证据。当前没有实现该接入。
21. 自有交付镜像的受控构建上下文排除秘密与受限资料，运行时由有权限方提供。固定官方镜像包含手册，不能直接当作无受限内容的分发镜像。最终复现不依赖开发容器临时手装的包，且记录目标架构与实际镜像身份。
22. A 使用独立入口，不绕过 `run_baseline.py` 对 B/C 的预算/判分阻断。只在 A 调度容器提供引擎权限，默认离线 `dev` 保持无 socket。先核对固定官方启动钩子与具体工具 handler，再允许无模型环境启动和脚本查询；不向任何容器提供参赛模型或 judge 凭据。静态源码、实时发现、具体调用和业务任务完成分别取证。
23. A 探针只接受经源码核实的逐工具允许列表及现场兼容 schema；不按命名空间整类放行，不执行提交、发送、模拟对话或评分。未知工具/参数契约停止并记录；原始响应留在忽略目录。每次独立检查创建新的调试世界并只清理自己拥有的容器/网络，已保存证据须在清理后仍可读取。
24. B 离线入口独立于任务入口：轻量 Chat Completions 适配层接受注入的合成传输，生产 CLI 只提供离线 fixture，没有 HTTP/SDK 客户端、凭据加载、官方 MCP 或真实任务通路。离线环境使用 `--network none`，不挂 Docker socket、手册、病例或 verifier；不调整原 `run_baseline.py` 的真实执行门禁。
25. 候选请求显式记录 `deepseek-flash`、`https://api.deepseek.com`、Chat Completions、`thinking={type:enabled}`、`reasoning_effort=high` 和有限 `max_tokens`，只表示已准备的格式。逐条保留 assistant 的 `content`、不透明 `reasoning_content` 与工具调用，再按 `tool_call_id` 追加结果。至少两次连续工具往返及最终响应才证明本轮合成示例闭环；模型字段是 fixture 值，真实模式、返回模型和兼容性仍未知。
26. 每次注入传输前复用 D0 的 `evaluate_budget`；预算、轮数、最大输入/输出、累计用量、价格/换算依据须可核对。示例价格、用量与成本明确标为 synthetic，真实 provider usage/cost 为 null，既有 B/C 预算不被重置或消费。缺失/无效证据停止后续请求；响应格式/未知工具/参数/重复 ID 在工具执行前拒绝，整批调用先校验再派发。传输拒绝/超时不自动重试，已执行效果与后续请求错误分别保留。
27. 合成闭环成功需至少两个独立工具往返轮次，随后取得正常 `stop` 的有效最终文本；`tool_calls` 为空值可表示最终消息，但 `length`/过滤或不一致的结束原因不能算完成。所有返回响应先核算可用用量，再验证业务消息；缺失或无效用量（包括最终响应）使累计总量/总成本为 null，已知前缀另记且标明不完整。配置限额拒绝 bool/非整数，工具调用仅接受 `type=function`。

### B 离线探针的参考 runner 接入缺口

固定上游 `openai_agents_runner.py` 的 `run_agent()` 通过 SDK `Runner.run()` 管理循环；`_build_model_settings()` 配置推理强度和 SDK 重试，`_agent_model_context()` 的专用 reasoning 回放只用于 Tinker 路由。原 harness 没有合成工具替换或逐请求预算回调开关，本地工具还包含真实 shell/文件操作。因此此前 B 离线阶段采用独立合成协议探针，**其证据不包含官方 runner 接入**。本轮由下一节接入层补充固定 SDK/runner 的离线验证，关闭重试并接通逐请求门禁；真实 B/C 的验证仍不能由旧探针或本轮离线结果代替。

探针的 request 记录包含 `endpoint`/`api` 路由元数据，是离线配置封套，不能直接当作 SDK 关键字或 HTTP JSON body 提交。真实适配还需分离路由与 wire payload，验证 SDK 序列化、返回字段、真实 tokenizer/预算计量及服务商行为；本轮 UTF-8 字节界限只约束本地合成输入。

字段依据于 2026-10-26 核对的 DeepSeek 官方 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) 与 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：带 tools 的后续请求需保留此前 `reasoning_content`。这里只据此准备请求与离线契约，不据文档推断账号、SDK 或服务商的实际响应。

### 模型与官方 runner 接入层：本轮设计

固定上游 `4444a07` 的 harness 明确安装 `openai-agents==0.13.6` 与 `openai==2.36.0`。本轮使用这些真实包及其依赖，在已有 Python 3.12 Docker 内准备独立、可复现的可选依赖层；不升级原 dev/controller 锁，不在宿主安装。SDK 内部行为按固定已安装源码和实际离线请求验证，不能用最新文档替代固定版本。

路由配置与 HTTP JSON 分开：DeepSeek 候选的 endpoint/API/key-env 只用于客户端配置；body 保留 model/messages/tools、有限输出、thinking 和 effort。接入层通过上游 `run_agent()` 的模型 context/settings 接点提供显式 Chat Completions model 与客户端，保留官方循环；不修改 vendor，不复制官方 runner。离线验收替换 MCP 与本地 shell/文件工具为允许列表合成工具，并在 HTTP transport 注入响应，不创建任务世界。禁止追踪上传；环境与临时替换退出后恢复。

预算检查位于实际序列化请求发送边界，覆盖 SDK 每次模型请求；响应可用用量先核算，再校验结束原因和整批工具，失败则不执行该批工具。HTTP 客户端重试、Agents retry、MCP 工具重试与外层重跑分别核对，均不得自动重演。缺用量/来源时 aggregate 为 null、已知前缀单列，停止后续请求；已执行效果不因下一请求错误消失。输入字节数只能作为离线界限，未验证 tokenizer/服务端 framing/真实价格时不得据此开放付费入口或承诺账单硬封顶。

带工具历史逐条保留原 assistant content、opaque reasoning_content、工具 ID/参数及对应 tool 结果；thinking 经 SDK extra_body 序列化后应落在 body 顶层。回放须绑定精确模型与 endpoint，避免跨模型泄漏或静默降级。通过真实 SDK 捕获的第二/三次 HTTP body 验证，不能仅比较预先构造的 dict。

无评分入口选择直接执行固定官方 runner 的 `run_agent()`，不进入 `cb experiment run`/Harbor verifier；这仅建立开发接入路径，不增加虚构 skip-judge 参数，也不修改官方 judge。生产 CLI 提供纯计划及合成离线集成，真实模式在任何 credentials/网络/MCP/claim 边界前拒绝。本轮不把它接入 C 的真实 attempt，不消耗/重置真实 B/C 预算。

### 真实 B 运行准备：本轮设计

沿用上一接入层已验证的固定 SDK/官方循环及 scoped 恢复机制，不复制 runner 或再造一套业务 Agent。将 fixture 内部的传输与核算职责分离到可注入的通用请求边界；离线演练使用 mock 下层，真实 HTTP 构造/调用和凭据读取仍在 live 暂停门禁之后。旧 B/C/baseline 的门禁及既有合成探针行为保留；必要的接入层抽取须有原回归。

provider profile 显式固定 model、endpoint、API、thinking/high、key-env 名称、有限轮数/输出、响应模型约束，以及价格/输入预留的版本、来源和核对日期。不读 .env，不调用 /models 或 /user/balance。预检只核对显式本地资料，分别报告代码/SDK、配置、预算证据、认证未验证和执行暂停；plan/preflight 不写文件或占用运行机会，不能把 technical configured 写成可执行授权。

2026-10-26 从官方 [人民币价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/) 核对 DeepSeek Flash 高峰未命中输入 2 元/百万、输出 8 元/百万；直接 CNY 核算，避免引入未经核对的汇率。使用高峰/未命中价格作为保守上界，不将该估计称为账单实测。来源过期/缺失、金额类型错误或非有限值均阻断。

输入预留默认可采用官方 [模型元数据文档](https://api-docs.deepseek.com/zh-cn/api/list-models/) 示例的 context_window=1048576，明确标为 documented context ceiling，作为对被服务端接受请求的保守推断；不再把旧探针的 UTF-8 字节数称为 provider token 上界，也不下载 tokenizer 来掩盖服务端 framing 未验证。该策略假设服务端遵守文档容量，并非精确 tokenizer/费用硬封顶证明；实际 usage 超界时如实核算并停止。较小输入预留只有获得相应明确依据后才能采用，不能由任意配置字符串宣称已验证。

累计预算包含此前 B/C 花费。未提供真实账目时真实预算就绪保持 unknown，不能默认为零或由 synthetic 文件放行。准备层只在合成 namespace 演练持久请求账目：先持久预留后到达下层传输，响应先核算后验证工具；超时、未知用量或中断中的请求保留未决状态，换 run-id/重启不能把未决费用清零或自动释放。持久化/清理错误和主错分别记录。实际账本初始化与真实请求机会留待明确恢复，C 控制器本轮不改。

验收重点是同一通用传输边界在真实 SDK/官方循环中的禁网演练，而非只对字典做单元测试。使用显式 profile 和先前账目覆盖逐请求预留、陈旧来源、输出/轮数、缺失/不一致 usage、整批工具与历史、取消/超时/HTTP 错误、未决预留恢复和多进程排他。真实 provider usage/cost/reward 仍为 null，模拟 usage 与基于文档价格的演练估算分开标注。串行 B 验证无需扩到官方世界、C 资源调度、业务策略或后台进程。

### 本地开发预算与正式私有评测

2026-10-26 用户指出本地预算与官方评测要求的适用范围不同，并要求记录以防接续遗漏。主代理当日通过浏览器复核 [Kaggle Rules](https://www.kaggle.com/competitions/chi-bench/rules)：第 11 条规定开发 API 费用由参赛方承担，私有评测 API 费用由主办方承担；第 7、11 条要求私有任务使用同一冻结系统配置，第 12 条将推理成本列入同分比较。当前规则没有要求沿用本地首轮 5 元上限；主办方承担费用也不能解释为允许无限调用，正式入口仍须遵守届时公布的资源限制。

成本记录与金额硬停止应分别配置。本地开发策略继续以首轮 B/C 共享 5 元为上限，包含已有花费与每请求预留，未知用量不清零。正式评测须使用单独标识并冻结的运行策略：不继承本地余额、共享 B/C 账本、synthetic 记录或缺少开发 prior 文件的阻断条件。若正式规则或冻结配置明确规定金额上限，则按其范围执行；未规定金额上限时可仅记录用量与成本，不自行套用开发期 5 元。正式成本比较按主办方冻结价表，开发期价格快照不能被当成官方计费依据。

正式任务和独立尝试的身份、证据及未决状态应分别隔离。一道题的花费或 pending 不得自动阻断其他合法 trial，也不能通过换 run-id 擦除同一尝试的未决记录或自动重演。用量未知时保留 null 总量和已知前缀，该 trial 的停止/失败行为按统一冻结策略处理；保持请求/历史/工具校验、效果记录与重试控制，不能用“主办方付费”放开这些执行约束。所有私有任务使用同一策略，不按题手工改配置。

F 开发前，`b_provider_profile.py` 严格固定了 5 元 profile，`b_live_preflight.py` 与 `SyntheticJournal` 也按本地准备策略核对；不能只改 JSON/金额就声称已完成正式适配。正式提交前必须完成 [F 任务](tasks.md#f-separate-development-budgets-from-official-evaluation) 的代码分离、Docker 离线连续任务/独立尝试验收和冻结入口说明。以下 F.2–F.4 的实现与验收不改变已有本地验收的历史范围，不恢复真实 API、真实 C 或官方判分。

F.2–F.4 的实现边界：使用独立且可验证身份的策略表达 local_development、evaluation record_only 和显式每 trial capped。record_only 无金额硬停止，仍记录合成 usage/估算、保留协议/工具/轮数/输出/重试约束；未知用量停止受影响 trial，其他合法 trial 可继续。evaluation preflight 不读取开发 prior 文件，不能据此填造真实花费为零。

评测演练以 evaluation_id/task_id/attempt_id 确定固定状态归属，run_id 仅管理输出。同一 evaluation 持久绑定策略与 provider profile 身份，不能靠更换 policy、cap 或 run_id 绕过已有 attempt。claim 在 runner/client/tool 前独占并持久化；所有记录只在与本地账本分离的合成演练 namespace 中创建，旧账本不静默迁移或清零。完整提交冻结和主办方正式启动路径仍由 F.5 与后续真实阶段单独验收。

### G：评测专用入口与干净目录包

F 的策略组件只证明显式选择 record_only 后不会继承本地金额上限；直接沿用开发默认启动命令仍会选择本地策略。G 将交付入口固定为 evaluation record_only/null cap，不暴露 local scope、金额上限或开发 prior 参数；默认只读计划，rehearse 明确提供 trial 身份和外部输出根，live 在读取配置/manifest/身份/凭据前拒绝。此处只冻结可核对的离线候选入口，不提前完成 F.5 的最终模型/资源/完整正式启动验证。

目录包采用明确的公开文件 allowlist，包含必要 participant 代码、provider/entry 配置、模型锁/安装脚本和主代理维护的 [运行说明](../../../docs/evaluation-entry-runbook.md)，不复制整个仓库。local-development-policy.json、开发账本、凭据、vendor、数据、手册、测试和审核原始材料不进入包；已有 SDK/vendor 在验收时作为独立只读资源挂载。manifest 使用严格固定路径与内容 digest 表示身份，不能成为任意文件读取列表或实际调用授权，也不宣称具有真实性签名。

entry 必须从自身包路径解析资源，不能依赖 cwd 或开发文件回退；输出与只读包隔离。包/config digest 实际进入同一 evaluation 的持久登记，不能只写日志而不约束后续任务。复用既有 registry/claim/guard/SDK 官方循环，通过明确参数注入 output root/执行身份，避免临时修改全局路径来选择模式。原本地入口与 F 的身份/金额/锁/路径防护保留回归。

目录导出先持久写入未完成标记，所有允许文件及 manifest 写入并 fsync 成功后，删除该标记作为完成提交点。提交点前失败即使 manifest 清理也失败，验证仍拒绝；失败目标继续占用。源文件、manifest、entry/provider 配置均检查实际类型/大小并有界读取。输出根与包的祖先/后代路径均不得重叠，拒绝 symlink/父目录跳转。

验收在无原仓库挂载的干净包上实际启动 CLI，以同一默认策略完成多条估算超过 5 元的合成链路；覆盖 unknown 后独立任务、重复 attempt、换包/config、文件/manifest 篡改、禁止参数、源/目标 symlink 或父目录跳转、构建部分失败以及只读/暂停边界。包是 identified/offline preparation，实际官方任务和正式配送继续单独核对，不上传本地导出包或受限产物。

### H：官方启动接点与独立安装复现

核对固定上游 `4444a07` 的 `openai_agents_harness.run()`、runner 的 `parse_args/main/run_agent/write_result` 和 `docker/entrypoint.sh`。harness 将 instruction 写至 `/tmp/instruction.md`，选择 task 配置中首个有 URL 的 MCP server；runner 接受 `--instruction-file`、`--mcp-url`、`--logs-dir`（默认 `/logs/agent` 或 `OPENAI_AGENTS_LOGS_DIR`），写 `run_result.json`、可用的 `run_output.txt` 与 `trace.jsonl`，harness 另将 stdout/stderr 保存为 `run_log.txt`。所选 provider task.toml 指向 `http://localhost:8020/mcp`；该 localhost 属于官方任务容器。entrypoint 分别等待 provider 8020、payer 8100、CM 8200 的 `/mcp`，8023 health 不等于 MCP endpoint。调用方跨容器时必须显式提供从其网络位置可达的地址；本轮 URL 只传给合成 MCP factory，并不证明网络可达。

H 沿 G 的包/策略/claim 链路添加外部启动输入，最小扩展已有 `_rehearse`/`_run_offline` 参数，不复制官方 runner 或改上游 harness。instruction 只从明确的有界 UTF-8 普通文件读取；拒绝路径跳转/symlink、评分 fixtures 路径与非法 URL，不依赖内容关键词猜测是否是隐藏答案。合法 HTTP(S) `/mcp` 地址不得含凭据/query/fragment；地址不决定 transport，所有离线调用仍固定 MockTransport 与 synthetic MCP/本地工具。元数据保存输入 hash/URL/日志归属与合成来源，原始任务/轨迹只留本地。

日志目录必须新建独占，禁止覆盖包、输入或持久账目；与 output root 的账目/claim 子树隔离。读取输入/验证配置和依赖之后才预留尝试，runner 前持久 claim；预留后的失败保留证据与日志，重复 task/attempt 不因换 run-id 或日志目录重跑。保留 runner 原生产物和 stdout/stderr，不能用自写成功文件替代 runner 输出，也不能把 runner 的合成成本称为官方账单。live 在读文件/配置/client/claim 前继续拒绝。

独立安装使用本轮新建空 Docker 卷，以干净包内 `requirements-model.lock` 和安装脚本执行哈希校验安装，检查实际 Python、SDK、完整锁定版本与依赖一致性；不使用既有 SDK 安装目录，不改变锁、不在宿主安装。复用基础镜像意味着基础层没有重新构建，包仍需要独立授权的固定 vendor，不称自包含镜像或新机器/其他架构通过。安装后禁网运行只读干净包，分别挂载外部输入/输出/vendor/新依赖，换 cwd，验证正常、失败、重复和暂停边界。F.5 涉及的当前主办方限制、最终模型/资源/正式启动与实际运行授权继续另行验收。

### K：多次 C 开发尝试与真实账目接续

本轮开发模型为 `gpt-6.1-terra` / `high`，参赛运行时保持既有 DeepSeek Flash。用户明确允许多次 C 开发尝试并取消旧 5 元金额停止条件；新本地授权使用独立 `record_only` / null cap 策略，仍保留请求预留记录、实际 usage、已知费用前缀、未知总量和逐请求协议检查。旧 local-development-policy 的 5 元行为及 G 正式评测策略不改，避免将历史授权重新解释为当前授权。

旧 `runs/real-b-c/` 的生产 accounting、B 回执、失败 claim 与原始产物保持原字节；新开发根通过显式接续命令验证旧 schema、已知用量、产物/账目哈希与无 pending，再导入有来源的累计金额，不以零重新开始。缺失、篡改、并发或未知账目停止，不能靠换目录/编号绕过。新账目单列历史 prior 与本阶段新增用量，金额为按 provider 回报及文档价估算，不当作账单。

每次 C 使用新 run/attempt 身份、独占产物和持久 claim，新官方世界完整初始化后运行自主模型任务，结束后精确清理本次资源；同一 attempt 不重演。多个尝试是主代理在前次终态后发起的独立开发运行，HTTP/SDK/MCP 请求不自动重试；不在试跑中指导业务动作。独占调度锁应覆盖前置校验、claim、世界、runner 及清理，避免两个控制器同时发起付费任务。未知资源或 cleanup 失败先查明归属，不开始下一世界。

代码修复后以显式 source transition 接续，保存前后身份、原因、账目/前次结果关联，不修改已有 run 的身份或总额；新源必须有对应 B 工具联调成功证据，才能运行 C。旧 B 仍是历史证据，不能只改哈希把它当成新源运行。接续命令不发送 API、创建世界或读取 Key；实际执行仍由主代理在独立审核后进行。

复用现有 Python 3.12 镜像、SDK 卷、固定 vendor、任务和授权手册；C 使用 J 已修复的 artifacts 父目录 bind，文件工具仍限既定资源/工作区范围。先离线验收接续、超 5 元 record_only、两次不同 attempt、同 attempt 拒绝、并发锁、源码变更/B 失效、unknown 与失败清理，然后真实 B 与 C。按终态日志定位环境、工具和模型行为；官方 reward=null，不调用 verifier/judge，不自动声称任务正确、F.5 冻结或正式评分通过。

实际 C 反馈要求允许路径内支持 PDF：新增独立单包哈希锁和只读卷，固定 pypdf 6.20.1，与官方固定源码锁一致，不改变原 SDK/基础镜像/vendor。读取器在原路径校验之后提取 PDF 文本，限制输入、页数、解压工作量、提取和返回长度，禁外部 JBIG2 程序，不提供 OCR；保留 UTF-8 与 offset/limit，格式错误作为工具错误返回。读取器源码对所有调用者绑定，锁/包实际版本与源码哈希仅 K 必需；J 的文本路径不因此依赖 PDF 包。

### J：首次真实 B/C 的受控接入（历史授权）

用户明确恢复真实模型联调与满足条件后的唯一一次无评分 C，首轮 B/C 共享 5 元；官方判分仍暂停。新增独立本地真实开发入口，不改 G 正式包的固定 record_only/null cap、允许文件或旧 live 暂停。先完成必要代码与合成外部边界测试，固定候选后由主代理独立审核，实际 metadata/API 和 C 由主代理执行；实现代理不读真实密钥、不调用模型。B/C 失败或未知不自动重演。

当前固定 profile 为 DeepSeek Flash thinking/high、Chat Completions、有限 30 轮/每轮 8192 输出上限。2026-10-27 主代理重新核对官方 [价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[模型元数据](https://api-docs.deepseek.com/zh-cn/api/list-models/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode) 与 [请求契约](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)：与既有 profile 的模型、1M context、high 档和峰值 CNY 输入 2/百万、输出 8/百万一致。仍用高峰/未命中上界，不以时段折扣增加预算；响应用量是 provider 回报，费用是按价目估算而非账单。thinking 不支持 required/指定单个 tool_choice，使用 auto 和有依赖的 smoke 目标，不靠强制工具掩盖真实模型行为。实际 model metadata、认证与响应模型另行核对；未知/不符先停止，不静默更换模型、模式或放宽身份。

真实账目使用固定 first-B/C campaign，与 synthetic/evaluation 完全分离；日志根可变化，预算/claim 根不随之新建。主代理核对本项目此前只有离线/无模型记录后，显式初始化有来源的 prior=0；缺账目保持 unknown，不由 b-smoke/c-once 自动补零。复用现有 guard 的请求结构、历史/ID、保守预留与 Decimal 核算，真实 journal 采用独立 schema/状态身份和原子持久锁，不能把合成标签换成实测。每请求先落盘 reserve，再传输，响应 usage 先结算再校验整批工具参数；HTTP/SDK/MCP/外层重试为零。超时/中断/未知用量保留 pending，完整总量为 null，已知前缀单列；后续 C 不得放行。5 元约束建立在已核对容量/价格和实际返回用量的假设上，不夸称已实测账单硬封顶。

B 使用真实 SDK/模型、固定 transport、少量确定性本地测试工具，由模型自己调用；第二个工具依赖首个返回值，至少两次工具往返后有非空最终结果才标记成功。B 不创建官方世界或消耗 C claim。每次实际请求/工具结果具有来源，保留 reasoning_content、assistant content 和 tool call IDs，不能用 fixture 回答代替缺失的真实回执。B 可采用低于 profile ceiling 的小轮数限制，实际限制必须进入证据。

C 仅针对已选 provider task，复用固定官方 world 镜像、entrypoint 与 A 的所有权/清理逻辑，不重建受限镜像或把旧调试世界当初始世界。先核对真实 B 的 source/SDK/profile/budget 身份与已知余额，再持久 claim，之后才创建 world。controller 仅调度 Docker；模型 runner 使用独立容器，不挂 socket、整个原项目、.env 或 task fixtures。代码/vendor/SDK 分别只读挂载，但本地工具不可读这些目录；只投影公开 instruction/tool_reference 与已授权 handbook，scratch/logs 独立可写。world/runner 共享本次专属 artifacts 父目录，挂载到 `/logs/artifacts`；固定官方启动会删除重建其 `workspaces` 子目录，不能把该子目录本身作为挂载根。模型文件工具仍限 workspace 内 case/provider/shared，不因父目录挂载扩大读取范围。world 仅内部任务网络且无 provider/judge 凭据；runner 可连接任务 MCP 与固定 provider。最终清理本轮拥有的 runner/world/network，保留所有证据，主错与清理错分别报告。

固定官方 local-tool factory 提供不受限 shell/Python/文件读写；直接放进有 socket 的 controller 会暴露权限，单纯换 MCP 地址无法解决。因此 participant adapter 在独立 runner 中只提供范围受限的读/list（确需时提供 scratch 写/edit）及 claim_done/sleep，不暴露 shell/Python、环境变量和评分目录；这是自有受控配置，与原版全部本地工具能力不同。MCP 业务工具来自官方运行时 schema，正常病例动作仍由模型自主决定；整批参数在任何动作前检查。运行途中不让人工补业务动作或修结果，官方 reward 为 null，不运行 verifier/judge。

验收包括真实路径的 mock transport/MCP/Docker 边界、跨 B/C 累计账目与 pending、并发/重复 claim、整批 schema 校验、目录/凭据泄露、异常清理与 G/H 回归。只有真实 B 成功且预算足够才执行 C；凭据、网络、认证或模型行为的真实失败如实保留，不能据代码通过代勾真实成功。最终冻结 F.5 在有真实试跑反馈后处理，本轮不扩业务策略或其他任务。

### C 的离线执行控制

新增集中式 `c_run_control.py`，职责是单题尝试的生命周期与证据控制，不新增第二套模型工具循环。`plan` 纯验证/预览，不写目录或 claim；`rehearse` 只调用注入的纯 Python 合成 backend；`live` 在 claim/外部边界前明确拒绝。既有 `build_experiment_config()` 和 `evaluate_budget()` 分别提供单题形状及保守入场核算，`run_baseline.py` 与 D0 gate 不改。agent/model 显式保存为候选，不能从历史命令示例推断已冻结 DeepAgents 或真实 runner。

运行目录按 run-id 独占，尝试按 synthetic namespace 下的 campaign/task/upstream 身份独占，防止换 run-id 重试。claim 用独占文件创建并在外部动作前持久化；进程不确定退出也保留 claim，不加自动过期/重置。演练消耗的只是 synthetic claim，真实 C 机会不被占用。完整输出与 claim 留在忽略目录。

backend 仅表示创建新世界、运行一次和清理边界。返回的资源必须核对本次所有权；部分创建失败通过显式 handle 交还清理信息，未知/外来资源不猜测删除。清理放 finally，主失败和清理失败分栏记录，退出零也仅称演练结束。用量缺失不按零计，合成费用、已知前缀与真实 null 结果分开；B 已花费参与同一 5 元规划，不给 C 另加预算。此处是入场控制，不能声称已接上官方 runner 内的逐请求拦截或实现对任意阻塞函数的硬取消。

真实 C 前置仍包括真实 B profile/harness 往返、逐请求预算/重试接点、实际价格/用量来源以及已核实的无评分入口。当前 `cb experiment run` 未有已验证的跳过 judge 路径；本轮不伪造参数、修改 judge 或把合成 C 演练当作自主任务。后续正式接入须单独核对这些边界。

## Suggested Evidence

`runs/<run_id>/manifest.json` 至少记录：

- run_id、实际开始/结束时间、执行状态与退出码。
- 项目代码身份、上游 git SHA、数据版本、实际镜像 ID。
- 公开 task_id、harness、精确模型标识和不含凭据的接口身份。
- 实际运行参数及限制、官方结果/scorecard 的相对路径和摘要。
- 官方 reward；没有有效判分时为 null，不用执行器自行推断。
- elapsed_seconds、token usage 和 cost；仅记录有可信来源的数字，缺失为 null，并注明来源。

原始轨迹、scorecard、任务内容和可能受限的衍生输出只在本地保存。可分享报告先核对实际授权范围，再仅导出允许公开的内容。

## Verification

离线验证覆盖：缺依赖、未设配置、子进程失败、超时、缺判分文件，以及来源有效的模拟成功记录。验证包装逻辑与报告诚实性，不重复测试上游整个系统。

真实单任务验收检查：固定配置可重放、官方输出真实存在、manifest 与文件相符。reward 为 0 也可以完成“基线运行”验收，但必须报告失败和原始分母；不能改成成功。

## DeepSeek 开发评审（L）

原版 WorkspaceJudge 接受带 run_session 的 runner，PA adapter 与提示可复用，但仅改 CHI_BENCH_JUDGE_MODEL 不会切换 provider。L 通过独立 DeepSeek runner 实现同一 rubric 的开发评审，不修改 vendor、不调用 Claude、不输出冒充官方的 reward/scorecard；结果包含 origin、模型/提示/输入/源码身份、确定性部分检查、每项本地 verdict 与不可判定项，official_reward=null。模型替换的结果不与论文或主办方分数混报。

上次 C 保留了 workspace 与 trace，未在移除 world 前导出完整业务状态。不能从最终聊天或零散工具结果拼成权威 export。L 在模型完成、runner 停止后通过所属 world 的 localhost:8023/export 只读捕获，写到 controller 独有的 evidence 目录；runner 和其工具不挂载此目录。导出成功/失败均记录，不影响本轮资源精确清理，失败不给可评审身份。只支持当前 PA provider contract，其他契约显式拒绝，不宣称全任务覆盖。

评审独立于 participant。首版把官方 adapter 生成的完整 workspace 按相对路径内联为 JSON 数据，通过一次结构化模型请求评审；不提供 tools、shell、MCP、socket、整仓库或环境读取能力。提示增加明确的内联传输/返回 JSON 说明并记录版本；保留原 rubric 与判定规则，不称完全未改的官方协议。超出单次输入界限则拒绝，不静默截断材料。隐藏 expectations/评审材料不回流给 participant，原始 world 只供 adapter 构建目标患者证据。严格校验全部 rubric ID、pass 的 bool 类型、引用/结构；缺项/格式错/超时不转成 NA 或通过。请求在发送前持久记录，HTTP 零重试；有可信 usage 先结算再解析 verdict，未知状态保留并阻挡后续调用。有限时长/输入/输出，金额 record_only/null cap。评审账目单列新增费用，保留原 B/C 累计不重置；实际账单与保守估算分开。

先合成外部边界、固定候选并独立验收，再由主代理使用已有 DeepSeek 认证实际运行。本轮补接导出改变运行源码身份，旧 B 不冒充当前 B；如旧 C 无完整 export，按现有 rebind/new B/new C 协议新建尝试并留存旧账目，不重演旧 claim。正式 G/H 交付默认与原版 Claude 判分暂停保持既定边界，F.5 留待正式配送与冻结。

## Risks and Open Questions

- 手册访问、全量清单哈希和 Kaggle 接受规则已验证；Writeup 未创建，运行模型/API 与实际接入仍待验证。本地 judge 继续暂缓，首轮 5 元预算已确认。
- Docker daemon 已做只读验证；开发/任务镜像、跨容器调度路径、容器内依赖和目标架构仍未实测。宿主机 Python/uv 缺失不作为要求在 Mac 安装项目依赖的理由。
- 上游文档与实现可能有版本差异，实施时固定提交并记录差异。
- 基线耗时、成本和失败阶段将决定下一轮业务范围；目前不预设成功率提升。
