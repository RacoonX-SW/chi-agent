# 执行器交接：bootstrap-baseline

当前摘要、授权和验收身份见 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。本轮开发 G 的评测专用默认入口与干净目录包，并做 Docker 离线验收；按 [现行实现工作流](../../../docs/luna-subagent-workflow.md) 使用一个 Luna High 子代理，主代理负责规格、独立审核、教学与 GitHub。真实 API、真实 C 尝试与官方判分继续暂停，F.5 完整最终系统冻结留待后续。下方 F/接入层/C/B/A/D0 交接保留其阶段范围。

后续代码及文档交付统一使用 `codex/<任务名>` 工作分支：主代理先建分支、协调实现并独立检查，再推送和创建目标为 main 的 PR；用户审核并决定是否合并。主代理不直接开发/推送 main、不自行合并。下方历史 main 身份只记录已发生的交付，不能当作后续继续在 main 工作的授权，详见 [GitHub 工作流](../../../docs/github-workflow.md)。

## 当前 G 专用入口与干净目录包交接（2026-10-26）

按 [专用交付入口契约](specs/benchmark-readiness/spec.md#requirement-dedicated-evaluation-delivery-entry-without-development-fallback)、[G 设计](design.md#g评测专用入口与干净目录包) 和 G 任务。实现代理负责 entry、bundle/config/manifest、相应测试以及必要的公共 helper 参数接点；root独占 Markdown/Git，包括作为包输入的 [运行说明](../../../docs/evaluation-entry-runbook.md)。默认固定 evaluation record_only，无 local/cap/prior 参数回退；live 最先拒绝。

目录包仅包含固定公开 allowlist、内容 manifest 和运行说明，不包含 local policy、原始 runs、凭据、vendor、数据、手册或测试。干净包只读挂载，SDK/vendor 独立只读挂载，输出另行可写，从无原仓库挂载/不同 cwd 实际验证多 trial 超过 5 元仍完成、unknown 隔离、重复 attempt、换包/config 拒绝及故障/路径边界；包身份必须实际绑定进 registry。所有运行使用既有 Python 3.12 Docker，固定依赖/官方源码，不安装/下载/重建，不自行提交最终材料或恢复 API/C/判分。

## F 预算策略分离交接（2026-10-26）

按 [预算策略契约](specs/benchmark-readiness/spec.md#requirement-separate-local-development-budgets-from-official-private-evaluation)、[设计](design.md#本地开发预算与正式私有评测) 和 F.2–F.4。实现代理独占 scripts、相应测试及必要 public JSON 配置，主代理独占 Markdown/Git。策略从 provider 配置独立出来，默认保留本地共享 5 元及 pending 保护；评测演练显式选择 record_only 或每 trial capped 策略，使用 evaluation/task/attempt 身份、独立持久 claim 与同一 evaluation 的策略/profile 登记，不继承开发 prior 或账目。plan/preflight 只读，live 在配置/凭据/client/claim 前拒绝；真实 SDK/官方循环仍用 MockTransport 与合成工具。

复用既有 Python 3.12 镜像、只读模型依赖卷与固定 vendor，不改 C、baseline、锁文件或官方源码，不安装/下载/重建。先自测停写，再由主代理固定候选独立复验本地限额回归、合法估算超过 5 元的 record_only、显式 cap、跨 trial unknown 隔离、相同 attempt 零重演和策略一致性；最终提交与真实运行不由此自动通过。

## 真实 B 运行准备交接（2026-10-26）

行为按 [准备契约](specs/benchmark-readiness/spec.md#requirement-prepare-a-real-stage-b-run-without-enabling-api-calls)、[本轮设计](design.md#真实-b-运行准备本轮设计) 和 P 任务。实现代理负责 provider/profile、预检及受控传输/账目代码和相应测试，必要最小抽取既有接入层并回归；主代理负责所有文档和 Git。复用镜像/模型依赖卷，不装新 SDK/不下载 tokenizer，不读凭据/生产账本、不调用 API，不修改 vendor、C 或原真实 gate；真调用许可不由 profile/文件/CLI 参数自行生成。

## 模型/runner 接入层交接（2026-10-26）

行为与交付以 [集成契约](specs/benchmark-readiness/spec.md#requirement-offline-validation-of-the-model-and-official-runner-integration-layer)、[设计](design.md#模型与官方-runner-接入层本轮设计) 和 [I 任务](tasks.md#modelofficial-runner-integration-code-offline-only) 为准。唯一实现子代理负责接入层代码、相应测试和独立可选 SDK 锁/安装入口；主代理负责其余文档、固定候选后的独立检查及 GitHub。复用 Python 3.12 Docker，使用固定真实 SDK/官方循环和合成 HTTP/工具边界，不改 vendor、基础依赖锁、原门禁或评分器。运行方法只维护在 README。

## C 离线交接（2026-10-26）

验收按 [C 控制契约](specs/benchmark-readiness/spec.md#requirement-offline-stage-c-single-attempt-execution-control)、[C 任务](tasks.md#c-offline-single-attempt-lifecycle-control) 和 [C 设计](design.md#c-的离线执行控制)。唯一实现子代理负责 `scripts/c_run_control.py` 与 `tests/test_c_run_control.py`，主代理负责其余文档与独立审核。不改 B 代码、既有真实 gate 或官方源码，不安装 SDK，不把合成控制演练写成实际任务执行。

先从用户已合并的最新主线开始；`plan` 不写文件或占用机会，`rehearse` 只创建独立 synthetic claim、调用纯 Python 环境/runner 边界并核对清理，`live` 明确拒绝。不同 run-id 在同一 campaign/task/upstream 下仍只能开始一次；失败/超时/未知终态不自动重演，真实 C namespace 不被演练消耗。共享预算、部分资源创建失败、所有权、主错/清理错及未知用量都要留可检查的证据。

复用现有 Python 3.12 dev 镜像，所有测试/调试在无网络 Docker 中，只挂源码和本轮输出，不提供凭据、官方资源或 socket。子代理自测后停止，主代理固定候选独立复验，再创建 base=main PR 交用户审核。真实 B、无评分 runner 和正式 C 依赖仍单独待验证。

## B 离线交接（2026-10-26）

目标和行为以 [spec 的 Offline-only preparation for stage B](specs/benchmark-readiness/spec.md#requirement-offline-only-preparation-for-stage-b)、[B 任务](tasks.md#b-offline-preparation-of-modeltool-exchanges) 和 [设计取舍/参考 runner 缺口](design.md#b-离线探针的参考-runner-接入缺口) 为准。候选是独立合成协议探针，不是已接通的官方 Agent runner。

唯一实现子代理负责 `scripts/b_model_adapter.py`（若必要）、`scripts/b_model_probe.py` 与相应测试；主代理独占规格、README、学习、审核和 Git。复用现有 Python 3.12 dev 镜像，不装 SDK、不新增真实模型传输、不启动官方世界。Docker 离线运行不挂 socket、不转发凭据，输入仅为代码和合成 fixture，结果保存在忽略的 `runs/b-model/`。

交付至少两次连续合成工具往返及最终响应的证据，并覆盖未知/无效调用、重复 ID、历史字段保留、后续请求拒绝、预算/轮数/用量缺口和重复输出身份拒绝。实际 provider usage/cost 与 official reward 仍为 null。子代理自测后停止写入，由主代理固定候选独立复验，再推送工作分支并创建 base=main PR；不自行合并或恢复真实 B/C。

## 历史 A 授权与交接（2026-10-25）

用户本轮明确恢复 **A 官方环境与不触发模型的只读 MCP 接入**，覆盖上文历史“仅 D0”范围；B/C、参赛模型 API 与官方判分继续暂停。起点为最新 `origin/main` `d1c9f991eda9548974838f72578078f9f9b05757`，工作分支 `codex/bootstrap-baseline-a`，接手时仅有学习文档未提交差异，须保留。

两个子代理显式 `gpt-6-luna` / `high`：一号负责固定源码/数据、官方 Python 3.12 环境及调度/清理；二号先只读核查启动与工具 handler，交接后实现实时 schema/只读探针及自测。共享实现写入串行，主代理独占规格、教学、审核和 Git。默认 D0 dev 不挂引擎 socket，仅 A 调度容器获得所需访问。

验收依据为 spec 的 “Bounded model-free stage A tool integration” 与 tasks 的 A.1–A.6。必须先核查启动钩子和所选具体工具不会调用模型，再运行服务；不转发模型/judge 凭据，不启动 runner、模拟对话或 verifier。MCP 调用由脚本明确指定，未知工具/schema 不猜测。原始 schema/响应与镜像中的受限资源留在忽略目录，GitHub 只保存代码及允许的版本/检查摘要。运行与错误均保留可读取证据，只清理本轮拥有的资源。

A 的调试世界不能当作 C 的起点，工具查询成功不能证明模型选择工具、自主完成任务或官方评分。交付后由主代理固定候选、独立复验并创建 PR，用户审核决定合并；不自行合并或恢复下一阶段。

## 历史准备决定（2026-10-24）

以下是恢复前的执行器/环境核对，不再规定当前实现者。最新角色与执行授权以上文及根 AGENTS.md 为准。

2026-10-24 执行器方案更新：用户澄清此前耗尽的是 Antigravity 中的 Claude 额度，并报告已有 Google AI Pro；当前优先由 **Antigravity + Gemini 3.8 Flash-High** 实现，DeepSeek 备用。此调整只涉及开发执行器，不更改参赛运行时模型候选或 5 元预算，也不恢复编码和付费运行。

同日最新协作要求：**用户自行操作 Antigravity/Gemini 并转交任务和返工意见，Codex 负责规格、独立验收和教学，不再操作、调试或向 Antigravity 派发任务。** 执行器接入由用户与实现方自行处理；Codex 核对实际交付身份和代码证据。用户在候选稳定后通知审核，没有自动派发或后台验收安排。详见 [本地与 GitHub 协作](../../../docs/github-workflow.md) 和 [审核接续状态](../../../reviews/REVIEW_STATE.md)。

2026-10-24 只读准备核对已确认 Antigravity 2.26.0 的 chi-agent/Local/Gemini 3.8 Flash High 与可用额度、Docker 服务、Python 3.13 及资料清单哈希。项目依赖环境、源码/完整数据、新模型文件与终端工具仍待恢复后验证，见 [准备审计](../../../docs/preparation-audit-2026-10-24.md)。默认 Python 为 3.9.6；可用新解释器不代表项目环境已经建立。

同日最新环境要求：用户要求依赖安装、下载、测试和运行都在 Docker 中完成，覆盖之前在 Mac 建立项目 `.venv` 的建议。自有开发容器首选 Python 3.13；通过 GitHub 连接器已实际核对固定上游 `requires-python = ">=3.12"`，官方 Dockerfile 为 `python:3.12-slim` 且含解释器专属路径。官方任务镜像保持其版本，自有代码在实际目标容器内验证；不只改镜像标签就宣称完成迁移。宿主机只需要已有 Docker Desktop、编辑器/Git 与源码，见 [Docker 工作流](../../../docs/docker-workflow.md)。当前不构建镜像、不安装依赖，也未恢复编码。

## D0 开工摘要（2026-10-25 接续）

**本轮 D0 离线交付已完成。** 主代理修订协作约定，两个子代理按预算/判分与门禁分工，完成写入接力和自测后提交候选 b7f8941；主代理独立 80 项测试及 21 项补充检查通过。当前无 D0 代码返工；A/B/C 与付费运行仍暂停。无需先写完后续 Agent 改进的完整开发手册；实时工具契约、模型兼容性和实际成本分别在获授权的 A/B/C 取得证据后更新。

| 项目 | 本轮约定 |
| --- | --- |
| 目标 | 在 Docker 内建立可复现的离线开发环境，修复旧包装代码，使其配置、就绪检查和运行记录符合当前规格 |
| 输入 | 当前 OpenSpec、实际 Git HEAD/工作区、旧候选及返工意见；保留既有改动，分别记录起始状态与本轮差异 |
| 主要工作 | 最小开发镜像/依赖锁/持久存储；单题选择；分模式就绪；无评分和异常记录；有限调用与预算检查的离线验证；生产入口回归 |
| 离线边界 | 构建阶段允许下载声明的开发依赖；测试使用合成 fixture/外部边界替身，不依赖完整任务世界、实时 MCP 或参赛模型 API；D0 不向容器提供任务调度引擎权限 |
| 费用边界 | 不调用参赛模型或 judge；B/C 的 5 元预算继续留在后续阶段。D0 只验证预算/限额的离线逻辑，不宣称真实 runner 的逐请求预算拦截已经生效 |
| 通过标准 | 实际生产入口生成正确的单题配置，拒绝多题/多尝试误配置；离线模式不统一要求 Anthropic；0/null 与失败状态正确区分；干运行不启动任务或模型；容器内检查可复现，源码/结果持久化可核对 |
| 交付 | 一个稳定本地候选提交，加一份 `reviews/bootstrap-baseline-d0-handover.md`；写明基线/候选身份、变更目的、实际 Docker 命令/结果和未验证项 |
| 停止条件 | 子代理自测后停止修改，由主代理固定候选并独立复验，必要返工交回对应子代理；不自动进入 A/B/C，不编造无评分 CLI 开关或官方 reward；任务结束不后台轮询 |

`proposal.md` 说明目标，`design.md` 记录取舍，`specs/benchmark-readiness/spec.md` 是行为与验收契约，`tasks.md` 跟踪进度。本摘要只收拢 D0 的交接入口，不另建一套平行需求。具体命令和依赖锁在实现并实测后写进 README；OpenSpec CLI 校验尚未运行，开发容器可用后在容器内完成并记录结果。

下方“第一份 D0 的具体任务”给出缺陷和允许范围；涉及相关行为时再读对应设计与场景。历史长记录按需查阅，不要求执行器反复读取全仓库。

## 先读什么，如何处理历史冲突

1. [项目指令](../../../../AGENTS.md)、[协作约定](../../../../COLLABORATION.md) 的当前方式、[学习约定](../../../docs/learning-agreement.md) 的教学方式/当前进度、[README](../../../README.md) 的当前状态和 [审核状态](../../../reviews/REVIEW_STATE.md)。历史记录按需查阅。
2. 本变更的 [proposal](proposal.md)、[design](design.md)、[spec](specs/benchmark-readiness/spec.md)、[tasks](tasks.md)，以及 [首轮准备与候选配置](../../../docs/development-preparation-2026-10-21.md)。
3. [官方任务拆解](../../../docs/task-walkthrough-pa-t018.md)、[参赛路线](../../competition-route.md)、[判分认证与替代检查](../../../docs/judge-access-options-2026-10-21.md)。
4. [旧验收报告](../../../reviews/bootstrap-baseline-2026-10-20.md)、[历史返工意见](review-feedback.md) 和 [执行器切换记录](../../../docs/executor-transition-2026-10-20.md)，再看实际代码与差异。

最新用户指令与当前需求优先。历史返工记录保留技术缺陷的证据价值，但其中“交给 Antigravity”“手册尚未批准”“必须先本地官方判分”等早期状态不再支配当前任务。手册批准和下载已有证据，不要求用户重新申请；完整任务数据与环境仍需补全。不要改写历史验收报告来制造通过。

## 接手时的实际基线

- 项目目录：`/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent`；Git 根目录是上一级 `Kaggle`。
- 本轮开工起点为 `35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9` / main；当时已审 c4b410a 未通过。当前 D0 离线通过身份为 `b7f894130df93ded69496576b83e6dcdcab7e56b`。规划基线 `c660e2699b8b972c9aa1d114a3e4d63510b8985e` 保留作累计目标核对；后续重新记录实际 HEAD/差异，不能用早期身份冒充新开工点。
- 已知旧提交：`9a347195fc786c69db5ecddd4c1b2d50615eb682`。它未通过独立验收，之后的返工差异也未复验；开始时重新记录实际 HEAD 和未提交文件，不能只凭这个 SHA 代表当前代码。
- 2026-10-21 新增 GitHub 私有备份，见 [GitHub 协作约定](../../../docs/github-workflow.md)。存储提交包含旧候选和规划，不代表 D0 交付或验收通过；下面未提交状态是备份前快照，恢复时以实际 Git 状态为准。
- 历史接手时曾有用户资料、规划、旧实现和测试的未提交改动。本次准备核对的 HEAD 为 `d8ebe6f7035f5f86ece087aeb133e5ab8a100835`、分支为 `main`，非忽略的待提交文件仅为规划文档；已核对规划单独保存为本地基线，完整 SHA 由提交后的 Codex 回复给出。Gemini 开始时仍须复核实际状态，保留既有差异与 `.DS_Store` 等无关文件，不重置、不全量暂存。
- 上游代码固定目标为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`；`.coordination/upstream-reference/` 只是只读材料，不是 vendor checkout 或真实运行证据。
- 选定任务是 `pa_t018_t018_o001_p01_new_referral_provider`。只能从公开 Agent 输入、角色工具和授权手册取得上下文；`tasks.jsonl` 中的评测预期不能送入 Agent。
- 当前没有真实 trial、官方 reward 或可信实测成本。旧“30 项测试通过”不能证明返工版本或业务任务通过。

## 恢复后分四份交付

本表保留完整 D0/A/B/C 阶段及证据；当前增量授权以上方 C 离线交接及 REVIEW_STATE 为准。每份交付由子代理停止写入，主代理固定候选并独立验收、统一回复用户。真实接入及任务执行只有用户恢复对应范围才启动，不需用户转发子代理整段对话。

| 阶段 | 实现/验证范围 | 独立验收要看什么 | 参赛模型费用 |
| --- | --- | --- | --- |
| D0：离线修复 | 建立最小开发容器；修正配置与单题边界、分模式就绪检查、无评分记录、限额与生产入口测试 | 容器内命令、锁定依赖、持久化及构建上下文；代码差异、针对旧缺陷的回归；不启动官方任务世界 | 不调用参赛模型 |
| A：官方工具接入 | 补齐固定源码/任务依赖，启动环境，取得实时 schema，验证已核实不触发模型的合法读工具 | 环境与数据身份、实际调用、返回和依赖缺口 | 计划不调用模型；未知路径先核查 |
| B：模型工具接入 | 在选定 runner 中验证连续工具往返及目标思考模式字段，使用合成小任务 | 实际请求设置、call/result 关联、后续响应与用量 | 与 C 合计不超过已规划的 5 元；初始建议预留至多 0.5 元 |
| C：一次自主任务执行 | 从干净世界运行选定任务一次，并发 1；保存效果、产物与停止原因 | 任务与配置身份、真实 trace、可用业务回读、资源来源和未完成项 | 使用同一 5 元预算的剩余部分，初始建议至多 4.5 元 |

B 的合成数据不是官方病例；A 的调试世界不能直接作为 C 的起点。独立验收默认检查产物、离线重放和实际设置，不因此自动再执行一次 C。费用属于同一预算账本，不给每个阶段重新加 5 元。当前开发使用 Codex 中两个 Luna High 子代理，其可见用量与返工单独记录，不占用或扩大参赛 API 运行预算，也不自动调用备用 API。

## 第一份 D0 的具体任务

以下是初始 D0 需求，早期“当前仍有”的缺陷描述保留作来源；本轮 R2/R3/R5 已关闭，当前无代码返工，以 [最新审核](../../../reviews/REVIEW_STATE.md) 为准。不要因历史任务文字重复实现已修内容；未来仅对新变更影响的行为回归，后续阶段须按授权推进。

1. **记录接手身份。** 保存实际 HEAD、起始未提交文件清单和实现文件摘要，区分接手已有差异与本轮新增差异；原候选仅作为待修代码。
2. **修正单题选择。** 当前 `scripts/run_baseline.py` 仍把 `include_task_name` / `n_tasks` 放进 submission 配置，相关测试也断言这一错误形状。以固定上游实际 schema/CLI 为准修正，测试必须走生产入口、检查真正生成的配置与命令，并拒绝多题/多尝试的误配置。
3. **按模式报告就绪。** 当前 `project.yaml` 与 `check_readiness.py` 仍把 `ANTHROPIC_API_KEY` 作为统一前提。拆清离线、工具、无评分执行和官方判分的依赖；不以缺 judge 阻塞所有模式，也不把环境变量存在当成连通性。手册检查使用已有下载与版本证据，不能仅凭手工授权标志伪造准备完成。
4. **区分无评分和已判分。** 无评分执行没有 reward 文件是预期情况，报告 `official_reward=null` 与未评分状态；显式评分模式缺少有效结果才是未得到 verdict。评分解析保留 0，拒绝非法二元值和身份歧义，不把进程退出 0 当成任务通过。
5. **落实调用边界。** 参数校验、干运行、子进程失败/异常/超时均有明确终态；干运行不启动任务或模型。设计首轮累计预算、有限生成与尝试次数的检查，未知用量不按零处理；请求拒绝不触发已执行写操作的重放。
6. **提供容器内的最小运行依赖与检查入口。** 编写开发镜像、必要 Compose 配置与 `.dockerignore`，在容器内锁定解释器、uv/测试依赖，OpenSpec CLI 如需安装也放容器内。宿主机只运行 Docker/编辑器/Git；依赖环境不要写回源码绑定目录。镜像构建可下载依赖；构建完成后的离线测试不依赖模型 API、完整任务资料或容器内的任务调度权限。验证源码/结果持久化、干净环境重建及构建上下文排除凭据/手册；D0 不启动官方任务服务。依赖缺失如实报告，参赛模型和正式判分不因环境准备而自动调用。
7. **证明测试覆盖生产行为。** 针对旧入口缺陷测试实际 argv、配置、manifest 和退出状态；只替换外部边界。不要另造一份与生产入口无关的字典来证明实现正确，也不写只验证错误假设的测试。

无评分入口还没有实测。D0 可以验证包装与错误报告，不能伪造 `--skip-judge` 等开关；A 才核对实际环境和命令。若固定上游无法提供所需入口，保留已交付的离线/工具部分，报告具体差异与最小替代接入建议，不调用官方判分来掩盖入口缺口。

允许围绕本变更修改 `scripts/`、对应 `tests/`、`project.yaml`、最小依赖清单/无密钥配置样例、项目 Dockerfile/Compose/`.dockerignore`，以及 README 的实际运行说明。可按需新增少量共用模块，保持用途集中。OpenSpec 外部行为变更先写明差异供 Codex 调整；例行修复与目录组织可自主完成。不修改 RepoPilot，不重写官方模拟器/评分器，不增加网页、自动压缩或多 Agent 框架。

## B/C 的配置与停止条件

候选为 `deepseek-flash`、DeepSeek 官方接口、官方参考 runner、Chat Completions 和显式思考 `high`。候选限制为任务基础 900 秒、最多 30 轮、每次生成最多 8,192 token。**这些不是已实测配置。** B 必须检查真实请求及连续往返，记录精确模型标识/模式/接口和生效限制，再用于 C；失败不得静默换模式后仍标原配置通过。

每次请求前使用累计用量、可核对的价格与下一请求输入/最大输出预留检查预算。余量不足、用量无法核实、缺少必要依赖或无法有限恢复时，保存证据后结束。实际账单、用量推算与外层超时分别描述，不承诺未验证的账户扣费硬限额。

工具执行成功但后续模型请求报 400 时，分别记录工具效果与模型 API 错误；只有日志能确认出错环节。业务写操作超时保留结果未知，不自动重试整个任务。C 已尝试一次、包括超时或预算停止后，不自动再次启动 C。

本地完整官方判分当前暂缓。源码的 Claude Code/OAuth 认证是可选实现路径，用户当前没有已验证可用的完整判分授权；部分确定性校验需在独立验证侧核对适用性。当前不新增 Gemini/DeepSeek 判分替换器，任何辅助检查都不能产生官方 reward。

## 每份交付必须提供的证据

| 内容 | 必须说明 |
| --- | --- |
| 候选身份 | stage、实际 executor、基线 HEAD、未提交差异；交付 commit 或可复核 patch 与实现文件摘要 |
| 变更映射 | 哪项需求改了哪个生产入口/关键符号，旧缺陷怎样被回归检查覆盖 |
| 实际检查 | 命令、工作目录、解释器/依赖身份、退出码、日志位置；未运行项与原因 |
| 状态分层 | 离线实现/离线验收、工具、模型往返、真实任务执行、官方判分分别记录；不能相互代替 |
| 运行证据 | 若发生 B/C，保留任务、模型、harness、版本、输入限制、停止原因、已核实效果、用量与费用来源 |
| 教学材料 | 真实入口与关键调用链、一条可解释的交互或失败记录、设计取舍与未解问题；D0 的模拟例子明确标注 |

报告可放 `reviews/bootstrap-baseline-d0-handover.md`、`reviews/bootstrap-baseline-a-handover.md` 等对应阶段文件。原始运行与可能受限内容留在忽略目录；报告不得夹带秘密或未经允许公开的原文。

采用本地 commit 加一份简短阶段报告交接，避免重复长总结；报告覆盖上述本阶段实际涉及的证据即可。`.coordination/delivery.json` 改为可选，不是通知或唤醒机制。如保留该文件，沿用 `schema_version=1`，`task_id` 使用本轮阶段 ID（例如 `bootstrap-baseline-d0`），附 `stage` 和实际候选身份，不能沿用旧交付标记。只有确实发生任务执行时才将 `real_baseline_run` 记为 true。

`ready_for_review` 表示材料稳定、等待主代理审查，不代表验收或任务通过；无法继续则报告具体依赖。子代理交付后停止修改，由主代理固定候选、审核并协调必要返工。实现者只勾选亲自完成的任务，不能代勾独立审核/用户验收；沿用已有 D0 交付报告，不重复创建同阶段材料。

## Codex 如何验收

先确认阶段、基线/候选身份和工作区，再读差异、相关入口/调用者/配置与必要测试；项目依赖、测试和调试在 Docker 内完成。首次 D0 建立可信认识，不把旧候选视为已验收；后续按提交差异与遗留问题增量审核，必要时扩大读取范围。检查生产入口与边界、模拟/真实来源、预算与运行身份。A/B/C 还检查实际记录是否支持对应结论；官方 reward 未运行就保留 null。审查期间实现方不继续写同一份候选。

审核结果写入报告和审核接续状态；主代理将具体问题直接交回对应 Luna 子代理，不依赖用户转交 Gemini。扩大任务、付费范围、改变业务/评分口径或公开发布时仍按原边界处理，不操作外部执行器。当前未启用后台唤醒。

## 新对话衔接文字

从根 AGENTS.md 指定的最小摘要和 [当前 C 离线交接](#当前-c-离线交接2026-10-26) 接续；历史 [D0 Prompt](../../../docs/d0-handoff-prompts.md) 不覆盖当前单实现代理、Python 3.12 和阶段授权。文档本身不触发真实模型请求、任务执行或后台唤醒。稳定候选交付后先停止写入，再由主代理独立审核；需要返工时交回同一实现代理。

## 文档验证状态

OpenSpec CLI 的实际验证状态与本轮 Docker 检查由 REVIEW_STATE 链接的一份阶段报告记录。不能将文档完成或派发成功写成离线实现通过、实际接通或全部配置已冻结。
