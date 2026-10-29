# 有界行为与实验条件

## 起点和职责

PR #22 已实际核对合并，merge `575b6d1ae5d1f7944166e92a22ce33d3f9e46fc9`；fetch 后主线一致，从该点建立 `codex/go-chi-batch-recovery`。R 的实现、失败、账目及包身份保留在 [R 报告](../../../reviews/chi-go-evaluation-entry-review.md)，不得改写其一次 C 结果。

用户在知悉 Go 用途未获官方确认后决定继续，并强调额度充足、必要实验可充分使用；不按旧 CNY 余额收紧 Go，也不放宽无限调用。运行模型仍为 `deepseek-v4.1-flash`、base URL `https://opencode.ai/inference/go/openai/v1`，thinking/high；主输出 8192，确认 32768/至多两次；SDK turns 和主/确认共享实际请求上限 50。B 保持独立 6 请求/1024。record_only/null cap、USD 三列、未知用量阻断、零 HTTP 自动重试/回退、Extra Usage 关闭不变，不加 `[1m]`。

一个 `gpt-6.1-terra / high` 独占自有代码/测试和运行 runbook；主代理维护本规格、README、学习账本、唯一 REVIEW_STATE 和一份 S 阶段报告，固定候选后独立审查、执行真实运行与 GitHub。不得向实现者/参赛 Agent 提供隐藏评分材料；实现者不读真实新题正文/轨迹或 Key，不创建子代理。宿主只编辑/Git/Docker。

## 有效确认混批的可恢复拒绝

只改变新 Go CHI 的这一条失败策略：结构、模型、reasoning、tool schema、参数和调用 ID 均通过完整批校验，但包含 `local-confirm-patient` 且批次长度大于 1 时，不再将它提升为致命协议错误。

在任何工具 callback、文件访问、MCP 调用、绑定检查副作用、确认计数/子请求、claim 发生前，将整批每个调用 ID 标记为拒绝。所有本地工具（包括读取/写入/claim/确认）和 MCP 统一先检查该标记，以各自原 call ID 返回清楚一致的 `REFUSED` 观察，记录 refusal 证据及可信工具结果；该批实际工具执行数为零。不要代拆、代排、执行其中的安全子集、伪造业务返回或自动再次发送原请求。

模型在下一正常 SDK turn 观察全部拒绝，再自主决定重新发起单独确认或其他动作。它是新的已计费模型决策，计入共享 50 次，不是 HTTP 自动重试；没有额外免费/隐藏调用。重复混批也消耗普通请求额度，不给无限恢复机会。拒绝不绑定/poison 患者、不增确认尝试、不记完成、不改变业务状态。无效 schema/重复 ID/伪造历史、未知用量、账源异常、传输或持久化故障仍保守停止；旧 native/Q 和旧 live 拒绝不改。

验收要覆盖混批顺序、重复同名同参、读写/MCP/claim/确认混合、完整结果回传及下一轮预算刷新；一个有效单独确认仍走原公开证据、两次确认和患者实体门禁。其他角色不获得 provider 专用工具。

## 显式 CHI 来源迁移

不能直接更改旧 identity、搬走旧账根、另建目录清零或重用 R 的 B 收据。提供不调用模型的显式 audit/rebind 接点，要求预期旧 identity、旧账 hash、受审新包运行身份，在本地模式审计并锁定既有 Q 后锁 CHI。

迁移前完整核验全部旧账/请求/工具/诊断/claims/seals/B receipts，pending/halt/inflight/未结束 attempt 或账目损坏时拒绝。将旧 `chi-accounting.json` 原字节以 hash 归档，持久化明确的 old→new 迁移链和中断标记；新状态保留所有旧 attempt 的原内容、费用、身份归属、失败和独占性。旧 wire/tool evidence、seal、receipt 文件原路径和原字节不变。旧 run 仍按其历史身份验证，新 run 只使用当前身份；多次迁移可追溯且完整审计。

归档/迁移链/账目缺失、篡改、链接、孤儿文件或中断均阻断后续调用；不静默补写或删除中断标记。旧 attempt/run 的独占限制跨身份保持，旧 B 对新身份无效，新候选必须取得自己的 B。当前包/源码与历史 identity 不能随 CLI 任意冒用。允许具体存储格式由实现者选择，但要有故障注入和旧 R schema 接续验证。

## 操作者调度、终态和确定性检查

将 R 已有操作者流程收敛为自有、可测试的单次开发调度入口，放在参赛包之外；复用既有 SDK/镜像、a_environment 和适用捕获帮助函数，避免复制 native 业务循环或引入后台调度。一次命令只执行一个明确配置的 B 或 C；配置受审并绑定任务资源、bundle/runtime、初始 world 和镜像身份，主代理按下述固定清单串行安排，不自动批量/重试。

启动任何 world/runner 或读取模型凭据前，验证 controller 完整捕获依赖、固定 SDK/PDF/官方资源及输出独占路径；真实 controller 需既有 `/opt/a-venv` 与只读 SDK/PDF 卷。runner 只收 Go Key、只读独立包/SDK/vendor、公开 instruction/ref、授权手册和 workspace；不能看到 `.env`、socket、完整 world、fixtures、expectations、评审材料或其他提供方 Key。仅选 provider MCP，world 使用内部网络，不启动 judge。

不论 runner 正常、失败或超时，先确认 runner 静止，再在 world 清理前捕获该次权威 export、原始 shared world、expectations 及身份/hash；无终态就明确记录 unavailable。捕获异常作为独立字段保留，不能覆盖主运行的诊断/退出码。最后清理只属于本次的 runner/world/network，保存全过程状态、工具和耗时；捕获失败不伪造、补作或悄悄重跑。

在结束后的操作者侧核对捕获完整性，运行固定上游 `collect_all_verifier_checks(..., include_semantic_judge=False)` 的适用确定性部分，并比较目标/非目标患者的业务变化及目标终态。检查不能调用 Claude/其他模型，不把结果反馈参赛 Agent，不把确定性通过写成完整临床裁决或 official_reward（仍为 null）。缺材料/不适用/检查错误分别记录，不能默认 pass。

固定上游 `WorldService.export_state()` 的提交包、文档等部分字段只覆盖 effective target case，单靠 export 计数不能证明全局无副作用。因此操作者还需在 world ready/runner 启动前和 runner 静止/清理前，通过服务容器内只读 SQLite 接点保存 provider/payer `resources` 表的全量有界逻辑快照（按 resource_type/resource_id/payload，不改变库），用于逐资源新增/修改/删除与患者/案件关联比较。快照只放操作者捕获目录，不挂参赛 runner。前/后快照失败分别记录，不能将无证据当作无变化；不新增业务 API、Agent 工具或评分调用。

## 冻结与有界真实验证

1. 开发前只按固定 tasks.jsonl 的兼容元数据选两题：沿用 R 的 provider/family/task_kind/verifier_contract/expected_target_status 匹配规则，排除原八题及已使用 t012，取剩余条目字典序前二。冻结索引 hash、ID、选择规则和排除清单；不读 title/instruction excerpt/隐藏答案调参。不因结果换题。
2. 只下载所选两题各五个必要文件到新的资源目录，下载时固定 hash；t012 复用 R 原五文件，原版共享 world 和镜像不变。详细新题输入与评分材料不用于实现调参，隐藏材料只供服务初始化和运行后的操作者检查。两道具体 ID/hash 在选择后追加本节，未冻结不调用。
3. Terra Docker 禁网自测停止写入，主代理固定候选并独立审查。通过后导出独立只读包，固定源码、包/运行身份、所有提示/schema/门禁、任务资源、依赖、世界和操作者配置。离线用已保存响应回放/合成混批证明整批零执行和自主下一轮；不重复 G/H 安装。
4. 在完整审计和显式迁移后，最多 **1 次新 B**（≤6 实际请求），同一候选再做 **2 次 t012 开发回归**（各≤50），随后 **2 个冻结新任务各 1 次**（各≤50）。每次新世界和独占 attempt，最多 206 次实际 provider 请求。四次 C 的成功/失败都保留；失败不换题、不追加直到成功。t012 两次用于同候选重复观察，不据此声称稳定性或单变量因果收益。
5. 迁移验收前若开发回归已暴露缺陷，本轮先离线分析；改代码会使旧 B/包身份失效。不得悄悄把后续配额变成新候选重跑，修复/额外 B/C 须另行明确界限并重新固定/独立审核。工程失败不自动触发 paid retry；未知用量阻断所有后续调用。
6. 本轮所有真实运行模型/参数/公开提示/工具策略保持同一候选，无人工中途业务指导。OpenCode 调用可全天安排；原官方 API 避峰、十一月隐私人工复核按文档执行，不加程序时钟门禁。非编码用途仍是用户知悉的未确认项，不伪装请求。t013/t019、Go 付费临床评审、Claude、完整 Harbor/F.5 保持暂停。

## 验收证据

2026-10-29 开发前已在 Docker 执行选择：固定索引 SHA-256 `8751f9ae3132a861f389d85d66ba0cca5a52fddb17fe3e2ab4dc92f2804ccc91`，四个剩余兼容条目中按规则选定 `pa_t014_t014_o001_p01_new_referral_provider` 和 `pa_t017_t017_o001_p01_new_referral_provider`，均为 provider/new_referral/contract_v5、无输入 PDF。排除清单、选择器和输出保存在本轮忽略的 operator-audit/evidence；未读取标题、instruction excerpt 或 fixture 内容。即使失败也不替换这两题。

独立审核必须覆盖：有效混批所有入口零执行/逐 ID 拒绝/自主改正、非法批次仍致命、单独确认及跨患者写入门禁、50/51 与确认共享、零重试/取消/未知阻断；旧 v1 真实账目副本及多次迁移、篡改/缺件/中断/并发/B 收据隔离；controller 缺依赖在创建资源和读取 Key 前拒绝、runner 失败也捕获/主错误不覆盖、清理与缺捕获真实限界；独立包原工作区不可见启动与最终归档身份。

主代理开始时保存全部旧 data/runs 文件 hash；本轮只允许按受审迁移修改 CHI 主账，原字节归档并逐旧条目/证据验证，其余旧文件不变。报告全部实现/操作者失败、真实请求/工具/确认数、用量、逐请求和整体耗时、USD 三列与历史 CNY 分账、捕获/确定性检查范围和未验证项。文档职责不重复，最后显式提交/推送、base=main PR 交用户审核，不 merge/auto-merge。
