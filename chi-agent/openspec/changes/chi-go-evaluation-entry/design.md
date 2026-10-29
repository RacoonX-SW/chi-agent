# 有界设计与验收

## 官方契约和已确认范围

固定上游为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`。已读 `experiment/agents/openai_agents_harness.py`、`openai_agents_runner.py`：harness 从任务配置取 MCP URL，将公开 instruction 写为文件；runner 接受 `--instruction-file`、`--mcp-url`、`--logs-dir`，用 `Agent` / `Runner.run` 接入 Streamable HTTP MCP，并写 `run_result.json`、成功输出及 trace。上游默认重试不能继承，本程序所有模型请求零自动重试。上游原 harness 不会自动选择我们的 Go guard；交付说明必须写出自有入口怎样替代 runner 调用以及仍需主办方集成的边界。

角色为 provider、payer/UM、CM；固定世界对应 MCP 端口 8020、8100、8200，8023 为 health。端口是已知默认，实际 URL 从调用方传入并按实际角色核对；不能因 host 为 localhost 就认定跨容器可达。只连接明确选择的角色，不汇集三个角色工具。官方动态工具 schema 是可调用动作的来源，工具名消歧、完整批次参数验证、调用 ID 唯一和完整结果回传均须验证。

外部任务与包分离：只允许公开 instruction/工具参考、授权手册及该角色 workspace；禁止 verifier/fixtures、期望答案、开发轨迹/账本和配置秘密进入参赛 Agent。主办方源码与授权资源在外部提供，不把 vendor、数据或手册打进包。资源路径白名单须按角色处理，不能把 provider 写路径放开给 payer/CM；PA provider 的既有患者确认和实体写入约束保留，其他角色不能误套 provider 专用语义。三角色协议离线通过不等于三赛道业务能力通过。

## 运行与协议

- 固定 Go SDK base URL `https://opencode.ai/inference/go/openai/v1`、模型 `deepseek-v4.1-flash`、`OPENCODE_API_KEY`、自有 UA 和每对话稳定 session；不加 `[1m]`，不声称 1M 实测。
- 复用锁定 SDK、同路由 reasoning/空历史兼容、现有工具循环和 PDF 读取；优先抽出小型可复用接点，避免复制整套控制器或将本地世界调度器带进包。
- 新 CHI 运行契约由代码和包身份固定，不能把 Q 探针的 6 请求/1024 输出设置用于任务。自主任务 SDK turns=50；主请求与患者确认共用 50 次实际发送上限。主输出上限 8192，确认上限 32768、至多两次。主请求用现有 `request_budget.feedback()` 语义，确认后刷新，Guard 独立核对计数/原 system prompt；不把可信反馈追加到持久历史。
- 从公开 instruction 和实际 MCP schema/本地白名单工具构造请求契约，固定首轮指令和系统提示、工具描述/schema；历史只能回放已返回的 assistant/tool 内容，禁止缺结果、伪造结果、重复调用、任意追加系统消息、改路由/工具/生成参数和静默 fallback。终态 reasoning 可选，工具阶段 required reasoning 与同路由回放保留。
- 最终动作由运行模型决定；claim_done 是过程事件，不是成功或官方得分。环境/工程故障与业务决策结果分别记录。请求耗尽、未知用量、HTTP/取消/持久化失败不自动重发。

## 账目、身份和启动边界

默认 evaluation `record_only`、金额 cap=null；不继承本机旧人民币开发限额、默认题或账本路径。每 evaluation/task/attempt 和 run 身份独占，失败也保留 claim；换 run-id/日志/输入不能重演同一 attempt。包/配置/源码身份进入记录，变化不自动覆盖旧身份或收据。新源码的真实 B 证据不能用 Q 的旧 B 代替。

复用 Go 的三项 USD 语义、预留/结算/未知阻断和来源检查。允许为正式 evaluation 隔离持久状态，但须明确它不表示账户/项目历史清零；本地开发接续不得以新目录绕过旧 pending/halt。Q/native 旧账不改写，适用的源码变更用显式有证据的接续。所有可信 usage 先结算，再判协议/业务结果；异常 billing source、非零余额扣费或未知字段停止下一请求。三项 USD 不相加，不与 CNY 混合，订阅固定费另列；Extra Usage 已由用户确认关闭，程序不修改它。

保留旧 synthetic/旧入口的 live 拒绝；新 CHI live 接点必须先核对包、外部输入、身份、来源及预算状态，才创建客户端。用户已明确知悉 Go 的非编码用途支持尚未确认，要求按真实开发用途继续使用；不得因这一未确认事项新增程序阻断，不虚构官方许可或伪装 coding。十一月隐私复核只放文档，不加程序时钟门禁、后台轮询/等待或自动唤醒。

## 固定实验条件和顺序

1. Terra Docker 禁网自测后停止写入，主代理固定候选，读 diff/调用代码并独立复验；复用 Python 3.12 dev、现有 SDK/PDF 卷和锁，无重复安装/下载/G/H 验证。
2. 必要新 B 至多一个真实固定自造 coding 工具闭环、最多 6 请求，以当前受审 transport/SDK 身份核验协议，不发送 CHI/手册/评分。B 用代码固定的独立合约（6 请求、1024 输出、无患者确认和任务预算反馈），C 才启用 50 请求/8192 输出和剩余次数反馈；不得给 B 显示 50 可用却在 6 截断，也不允许 CLI 任意覆盖合约上限。共用同一 ChiGuard/SDK 接点，C 的反馈与超过 6 次运行通过合成证据另验。若新 CHI transport 与 coding B 不是同一条接点，必须如实说明 B 不能证明新接点，不为增加数字重复旧探针。
3. 真实 C 在离线审核及适用 B 通过后安排一个新兼容 provider 任务，最多 50 总请求、独立新世界/attempt。开始前另在本规格固定任务 ID、资源 hash、模型/提示/依赖/门禁、初始世界及检查方法；在这之前不读其详细业务 instruction、期望答案或原始轨迹来调参。未冻结就不启动。t013/t019 不作为本轮真实验收题。
4. 只做一次 C，保留成功、失败、工具事件、终态、耗时及费用；不因业务失败重跑。明确工程缺陷才允许离线修复、重新固定/独立审核，再单独限定所需的新 B/attempt。用途未确认作为报告限制保留，不给参赛 Agent 隐藏判分材料，不调用 Claude，不以本地检查写 official_reward。

## 离线验收场景

- 独立导出包在原工作区不可见、工作目录=/tmp、包只读、外部 SDK/vendor/input/授权资源/输出分离挂载下运行；无需重装空 SDK 卷。校验允许文件、内容身份、依赖闭包、缺资源/不兼容 SDK/篡改包和任意工作目录。
- 三角色分别传入不同 instruction/MCP URL，实际 SDK 多工具交换、正常终止、日志/结果/trace、角色资源边界；provider 真实患者门禁通过合成公开观察验证。只宣称合成协议验证。
- 请求计数超过 6 仍可继续任务；50/51 边界、确认共享计数、反馈刷新/伪造/陈旧、完整工具批次无部分副作用、history/schema/name 篡改、未知/已知用量而内容失败、零重试/redirect/取消、并发/重复 attempt、未知账目、读写/链接路径与中断留证。
- 所有失败保留；退出码、诊断、claim、日志与费用口径相互一致；秘密不出现在正文、异常或导出包。真实与合成账目不混用。

官方资料（2026-10-28 核对）：[Go 用途/模型/隐私](https://opencode.ai/v2/docs/console/go/)、[USD usage](https://opencode.ai/v2/docs/console/api/inference/)、[服务条款](https://opencode.ai/legal/terms-of-service)。文档未提供非编码 CHI 支持或十一月 ZDR 续期证据；不将未证实等同于明确禁止，也不自行声称已支持。

## 本轮一次 C 的预先冻结（2026-10-29）

任务固定为 `pa_t012_t012_o001_p01_new_referral_provider`，数据版本 `5ce88104df2a91e057619eb70fb51f56fc5949eb`。选择器只比较固定 `tasks.jsonl` 的角色、family、task_kind、verifier_contract 及与既有 submit 路径相同的终态兼容字段；排除已使用/已读的八个任务，再取剩余五个兼容条目中字典序第一项。索引 SHA-256 为 `8751f9ae3132a861f389d85d66ba0cca5a52fddb17fe3e2ab4dc92f2804ccc91`，没有查看其 instruction excerpt、title 或 fixtures 内容来选题/调参。完整只读选择元数据位于忽略目录 `runs/chi-go-entry-root/evidence/task-selection.json`。

这是“未用于调参的兼容 provider 任务”，不是随机总体抽样或三赛道泛化样本。公开索引已知、任务整体未完全盲化；不会因结果更换任务。只下载该题必要的 instruction、tool_reference、task.toml、manifest、expectations 五个文件供世界初始化及运行后的操作者检查；后两项不挂给参赛 Agent，不发送给运行模型。资源 hash 在读取其详细输入之前由 Docker 下载步骤固定到本地 manifest。

实验条件：当前通用 Agent 实现的独立审核候选、不可写的独立导出包、Go `deepseek-v4.1-flash`/thinking high、主输出 8192、确认 32768/最多两次、总请求/SDK turns 50、现有反馈/PA provider 患者门禁与字段提示、同一 Python 3.12/SDK/PDF 锁、固定原版 world 镜像和全新世界。候选的包/源码/配置身份在 B/C 前固定；选题后的返工只能针对合成工程故障，不能按该题内容改策略。

验收检查：正常/异常停止原因，工具发起/返回/拒绝、全部主请求与确认、未知用量/账源，目标业务终态及完整 world 中非目标患者写入，适用原版确定性部分检查。诊断与隐藏材料只在结束后的操作者侧，完整原版 Claude 评分不运行，official_reward=null；不增加付费临床评审来替代官方得分。本轮一个真实 B、一个 C 上限，所有失败/费用保留。
