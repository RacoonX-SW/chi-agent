# CHI Workflow Agent

长期协作要求：**边参赛，边学习 Agent 开发。** 新对话先读 [学习约定与进度](docs/learning-agreement.md)；每轮结合设计、实际代码/轨迹和小问题推进理解，不只交付代码。

当前协作：**用户已仅恢复 `bootstrap-baseline/D0`，自行指挥 Gemini 写代码，Codex 负责规格、按提交差异独立审核、教学与 GitHub 存储。** Codex 不操作或调试 Antigravity；本次先核对并保存规划基线，交付稳定后由用户通知审核，不持续轮询。新对话先接上 [审核状态](reviews/REVIEW_STATE.md)，按需读相关规格与代码，历史记录不默认全量重读。流程见 [本地与 GitHub 协作](docs/github-workflow.md)。A/B/C、参赛模型 API 和官方判分仍暂停。

## 当前准备状态汇总（2026-10-24）

恢复前逐项核对及实施顺序见 [开发前准备核对](docs/preparation-audit-2026-10-24.md)。本次 Codex 只核对规划差异与 Git 身份并保存本地规划提交；D0 实现和容器内自测由用户交给 Gemini，尚无新候选可审核。

最新环境决定（2026-10-24）：**依赖安装、下载、测试和运行全部在 Docker 内完成。** 宿主机只保留已有 Docker Desktop、编辑器/Git 与源码，不再计划在 Mac 建立项目 `.venv` 或安装项目依赖。自有开发容器首选 Python 3.13；固定上游 `pyproject.toml` 已核实要求 3.12+，官方任务 Dockerfile 使用 Python 3.12，分别验证实际兼容性。此前报告的宿主机默认 3.9.6 不参与项目运行。详见 [Docker 工作流与交付边界](docs/docker-workflow.md)；目前尚未构建或运行这些项目镜像。

2026-10-24 执行器更新：用户确认前次受限的是 Antigravity 中的 Claude，并报告已有 Google AI Pro。当前优先方案改为 **Antigravity + Gemini 3.8 Flash-High 写代码，DeepSeek 备用**；Codex 继续规格、独立验收、教学与 GitHub 存储。优先使用套餐内额度，具体账号限制与实际接入待核实。下文早期“DeepSeek 实现”的描述是历史安排；参赛运行时模型候选和 5 元预算不变，D0 以本次恢复指令为准，后续阶段仍暂停。

**规划材料和首份 D0 交接已具备，用户已恢复 D0 开发协作；环境、接口与真实运行准备尚未完成。** 下表优先于后续按时间积累的旧状态，不能把“文档完成”写成“系统已可运行”。

| 准备项 | 状态 | 依据与边界 |
| --- | --- | --- |
| 竞赛方向与路线 | 已整理/已明确 | 竞赛优先，医院侧任务起步；后续仍需覆盖赛事其他领域 |
| 手册访问和下载 | 已验证 | 2026-10-24 重新核对固定版本全量 1,292 文件字节数和 SHA-256，全部一致；公开规划子集 9 文件也全部一致 |
| 一个官方任务的拆解 | 已完成静态分析 | 输入、公开工具、流程与评分边界已整理；实时 schema 未取得 |
| 第一阶段 OpenSpec | 已成文 | proposal/design/spec/tasks/handoff 齐备，已补充 Docker 内开发和镜像交付场景；引用与结构做静态检查，尚未运行 OpenSpec CLI |
| 分工、学习与交接 | D0 协作已恢复；待新候选 | 用户自行操作 Antigravity/Gemini；Codex 本次先保存规划基线，后续按稳定提交与报告独立审核。D0 实现与容器内自测尚未收到交付 |
| 首轮参赛运行预算 | 已确认规划 | 模型工具接入验证＋一次任务试跑合计 5 元；写代码另行记账，当前未恢复付费运行 |
| 模型与 runner | 候选待实测 | `deepseek-flash`＋官方参考 runner，Chat Completions/思考 high 为候选；协议、字段与实际限额待验证 |
| 完整数据与环境 | 未就绪 | 本轮确认 `vendor/chi-bench` 和 `data/.chi-bench-version` 均不存在；仅有规划用任务子集。Docker 服务已核实可用，CHI 镜像与任务环境尚未建立 |
| Docker 开发环境 | 已建立并验证 | 自有开发镜像 `chi-agent-dev:latest` 基于 Python 3.13-slim，锁定依赖于容器内 `/opt/venv`，已通过容器内 42 项离线自测；源码持久化挂载，构建上下文排除凭据与大资料 |
| 无评分执行入口 | 待验证 | 有设计方向，尚无实际可运行证据；不提供虚构的跳过 judge 开关 |
| 现有实现与基线 | 未验收/未实测 | 旧候选及返工未通过新验收，D0 未交付；没有已验证的真实 trial、官方 reward 或实测成本 |
| 官方判分 | 已决定本地暂缓 | 最终私有评分交主办方；确定性检查优先、Gemini 按需辅助的集成仍待实现 |
| GitHub 存储 | 私有仓库 | [xsw932187210-cell/chi-agent](https://github.com/xsw932187210-cell/chi-agent)，保留现有目录结构；代码仍是待验收快照，见 [存储与协作约定](docs/github-workflow.md) |
| Kaggle 入场与材料 | 已接受规则；Writeup 待创建 | 已登录 Rules 页面显示接受规则和 Team 页签；Writeup、私有程序包和技术报告均未提交。最终截止为北京时间 2026-11-16 07:59 |

下一步是 [交接包中的 D0](openspec/changes/bootstrap-baseline/handoff.md)：先修单题配置、按模式就绪检查、结果/预算记录和生产入口测试；稳定交付后再验收，之后按授权推进 A 官方工具、B 模型工具往返、C 一次自主执行。后续业务策略与自动压缩根据真实基线再细化，不属于已完成的实现。

## 过程记录与资料索引

2026-10-21 GitHub 配置：用户要求沿用现有 GitHub 账号建立独立的 CHI 私有仓库，由 Codex 处理远端和 push。保存代码、OpenSpec、文档与离线验收记录；手册、数据、凭据和真实运行产物不上传。Git 根目录仍是本机 `Kaggle/`，没有移动项目或另建嵌套仓库。功能编码与付费运行继续暂停。

最新方向（2026-10-20）：**先以 Kaggle 竞赛为主，先明确任务、评分和最终提交。** 网页工作台与独立产品方案搁置；此前医院侧范围作为起步调试方向，整个竞赛还评价保险方利用管理与照护管理。先读 [竞赛要求核对](docs/competition-brief-2026-10-20.md)。

2026-10-21 进展：已完成 [一个官方任务的只读拆解](docs/task-walkthrough-pa-t018.md)，并更新 [OpenSpec 参赛路线](openspec/competition-route.md)。选定头痛病例新转诊任务，核对了公开工具说明和启动配置；实时 MCP schema 和真实评分仍未验证。编码及付费评测继续暂停。

同日开发讨论：已核对官方 harness、runner 与本地工具源码，说明 [开发顺序和一轮工具调用](docs/development-discussion-2026-10-21.md)。先建立可信官方基线，再按失败证据提出自己的改进；尚未选择模型、harness、judge 配置或预算。

同日 API 补充：用户报告 DeepSeek 约 25 元人民币余额、Gemini 免费及约 10 美元额度；没有 Anthropic 原生 API，Claude 仅有免费账号。尚未发请求验证。优先考察 DeepSeek 接入，Gemini 保留为候选；官方完整本地判分尚未配置可用认证。可用余额不代表已经授权的运行预算，具体型号、接口及费用上限仍待确定。

判分认证更正：源码还支持 Claude Code 登录/OAuth，并由 Docker/Modal 转发 token，不能断言只支持原生 API Key；用户当前没有所需订阅。另可考察部分确定性检查的函数级入口，完整官方分数仍未知。证据和替代方案见 [判分访问方式](docs/judge-access-options-2026-10-21.md)。

用户已确认验证路线：确定性检查优先、按需增加 Gemini 辅助评审、完整官方评分交主办方。实现、API 预算及运行均尚未恢复。

同日最新安排：用户暂缓本地官方评分，最终私有评分交主办方。先按 [开发准备与无评分验证路线](docs/development-preparation-2026-10-21.md) 明确环境、模型接入、真实工具交互和运行记录；官方分数仍未知，部分 Claude 模拟对话也存在依赖缺口。此安排覆盖此前先取得官方评分的顺序，编码与付费运行继续暂停。

同日执行设计讨论：建议首版采用单 Agent 的模型/工具循环，程序负责接口与限额检查、状态记录和有限结束检查，业务阶段允许回退和分支。用户随后提出上下文压缩，已补充本地档案、进度表与实际模型输入的分工，以及保留不确定性和接口字段的建议。详见 [执行循环草案](docs/agent-loop-discussion-2026-10-21.md)；拟议能力尚未实现，也未冻结接入点或压缩阈值。

同日补充：[Codex 压缩机制的公开源码学习](docs/codex-context-compaction-study-2026-10-21.md) 已按用户要求整理，包含普通摘要与服务端 V2 的区别、流程图、检查点/版本校验和 CHI 教学伪代码。当前仅借鉴设计，尚未选择或实现压缩方案。

返回项目后的最新准备：用户已选择首轮“模型工具接入验证＋选定任务一次试跑”按 **5 元人民币**上限规划，写代码费用单独记录。已在 [开发准备](docs/development-preparation-2026-10-21.md) 和既有 `bootstrap-baseline` 中细化官方工具、模型多轮工具往返、单任务自主执行三个检查点。`deepseek-flash`＋官方参考 runner 是当前接入候选，接口/模式/限制仍待实测后冻结；没有恢复编码或付费运行，也未实现自动压缩。

最新交接准备：[DeepSeek 分段任务包](openspec/changes/bootstrap-baseline/handoff.md) 已收拢任务顺序、第一份 D0 离线修复、A/B/C 证据、代码身份及停止条件，并附新对话衔接文字。D0 优先修正旧候选的单题配置、模式依赖与生产入口测试。交接文档完成不代表已派发、实现或验收；参赛模型配置仍需接入验证后冻结。

当前阶段：**暂停编码，先确认项目规划**（2026-10-20）。Antigravity 的配额耗尽，返工未完成；现有改动保留，后续计划由 DeepSeek 在新对话接手。先读 [规划草案](docs/project-planning-v0.md) 和 [交接状态](docs/executor-transition-2026-10-20.md)。

目标：开发或改进能在 CHI-Bench 官方环境自主完成任务的 Agent，形成 Kaggle Writeup、私有可运行程序包和技术报告。医院侧申请准备作为第一批调试任务；技术方案和最终角色覆盖策略尚未冻结。

当前状态（2026-10-20）：Hugging Face 本机登录和手册访问已验证；手册全量 1,292 个文件已下载并与远端文件大小核对，已记录固定版本和本地 SHA-256。另已下载公开任务索引及 3 个任务的 Agent 输入说明，尚无完整任务 fixtures 或可运行模拟环境。详见 [资料记录](docs/data-access.md)。Antigravity 的首轮离线候选未通过 Codex 验收；返工暂停。真实模型基线尚未运行，赛事报名状态尚未确认。当前 PATH 未找到 OpenSpec CLI，未执行其校验。

详见 [独立验收报告](reviews/bootstrap-baseline-2026-10-20.md) 和 [返工任务](openspec/changes/bootstrap-baseline/review-feedback.md)。

## 现在先做什么

1. 已完成：本机登录、手册全量下载与核对、首批 3 个公开任务输入说明的阅读，以及头痛新转诊任务的静态工具/执行/评分拆解。
2. 已确认：竞赛优先，医院侧作为起步调试任务；不据此缩小最终比赛的评分范围。
3. 接下来确认：候选模型、harness、开发入口和实际生效限制；首轮预算已选 5 元。恢复后补全环境并取得无评分的单任务执行证据，本地官方评分暂缓。工程改进依据实际错误与轨迹，竞赛通过率保持未测。具体参数和返回值仍需实际 MCP 契约核对，不从静态文档猜测。
4. 本次已仅恢复 D0 离线修复，范围与验收见交接包；规划基线保存后由用户自行交给 Gemini 实现，DeepSeek 备用。稳定交付后通知 Codex 审核，A/B/C 仍暂停。旧 bootstrap 实现仍是待修候选，不能代替整个项目的业务能力。

如需正式参赛，另核对 [Kaggle 赛事页](https://www.kaggle.com/competitions/chi-bench) 当前规则及报名状态。手册及其衍生输出的披露范围按实际授权确认，下载完成不代表可以上传 GitHub 或转发给第三方。

## 协作入口

- [审核接续状态](reviews/REVIEW_STATE.md)
- [本地与 GitHub 协作流程](docs/github-workflow.md)
- [学习约定与当前进度](docs/learning-agreement.md)
- [共同协作约定](../COLLABORATION.md)
- [执行器交接指令](openspec/changes/bootstrap-baseline/handoff.md)
- [首轮目标](openspec/changes/bootstrap-baseline/proposal.md)
- [验收场景](openspec/changes/bootstrap-baseline/specs/benchmark-readiness/spec.md)
- [实现任务](openspec/changes/bootstrap-baseline/tasks.md)

## Docker 开发与离线自测运行

本项目开发、测试与检查均在 Docker 容器内完成：

```bash
# 1. 构建开发镜像
docker compose build dev

# 2. 容器内运行全部离线单元测试
docker compose run --rm dev

# 或使用 pytest 运行
docker compose run --rm dev pytest -v

# 3. 容器内分模式就绪检查（支持 offline / tools / ungraded / scored / all）
docker compose run --rm dev python3 scripts/check_readiness.py --mode offline

# 4. 单题基线配置验证（干运行，检查生产入口、生成配置与命令）
docker compose run --rm dev python3 scripts/run_baseline.py \
    --agent deepagents \
    --model deepseek/deepseek-chat \
    --domain pa_provider \
    --task-name pa_t018_t018_o001_p01_new_referral_provider \
    --dry-run
```

## 后续变更方向

- M0：环境就绪、单任务开发执行及证据记录；本地官方评分暂缓（待恢复实现）。
- M1：根据真实失败选择一个通用 Agent 改进，进行固定变量对照。
- M2：扩展到其他任务和三个领域，检查可靠性与成本。
- M3：冻结可复现程序包、Kaggle Writeup 和技术报告。

后续变更尚未细化或实现。官方模拟器、MCP 工具和评测器属于上游能力，不能作为自己开发的成果。

## 资料来源

核对日期：2026-10-19。

- [官方仓库与安装说明](https://github.com/actava-ai/chi-bench)
- [官方单任务 Quickstart](https://www.actava.ai/benchmarks/docs/quickstart)
- [自定义 Agent 接入](https://github.com/actava-ai/chi-bench/blob/main/docs/extending.md)
- [OpenSpec 结构与场景格式](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)

依赖版本、任务 ID 和命令以实施时固定的上游提交及对应文档为准；不把示例模型名当作已经可用的配置。
