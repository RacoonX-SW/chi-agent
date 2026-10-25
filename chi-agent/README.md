# CHI Workflow Agent

长期协作要求：**边参赛，边学习 Agent 开发。** 新对话先读 [学习约定与进度](docs/learning-agreement.md)；每轮结合设计、实际代码/轨迹和小问题推进理解，不只交付代码。

当前协作：**Codex 主代理协调两个 `gpt-6-luna` / `high` 子代理**，负责规格、写入接力、独立审核、教学与 GitHub 存储，见 [双 Luna 工作流](docs/luna-subagent-workflow.md)。本轮恢复 A 的官方环境与不触发模型的只读 MCP 接入；固定候选 `a173409` 已通过 Python 3.13/3.12 aarch64 离线独立检查，实际环境/工具结论见 [A 审核](reviews/bootstrap-baseline-a-review.md) 与 [审核状态](reviews/REVIEW_STATE.md)。B/C、参赛模型 API 和官方判分继续暂停，真实 Agent 入口仍有核算/无评分机制缺口。不操作 Antigravity，不设置后台轮询。

## 当前准备状态汇总（2026-10-25）

后续交付采用 **`codex/<任务名>` 工作分支 → Codex 推送并创建 PR → 用户审核/决定合并 main**，代码、规格、学习和审核文档都遵守。主代理不直接开发或 push main，不自行 merge 或开启 auto-merge；详见 [分支与 GitHub 工作流](docs/github-workflow.md)。

恢复前资料见 [准备审计](docs/preparation-audit-2026-10-24.md)；D0 的 b7f8941 曾独立通过 80 项测试和 21 项补充检查。当前 A 代码身份为 `a173409416cf111ec2f2cc45247aa592b5ddd77e`：两个 Python 版本各 115 项测试、19 subtests、6 项补充方法通过，并完成官方任务世界的真实 MCP 独立复验。OpenSpec CLI、其他架构、模型往返和 Agent 任务仍未验证，用户完整验收/合并未单独记录。

环境约定：**依赖安装、下载、测试和运行全部在 Docker 内完成。** 宿主机保留 Docker Desktop、编辑器/Git 与源码；开发环境实测 Python 3.13.17/aarch64，官方任务环境实测 Python 3.12.15/arm64。已有授权手册只供本地官方环境使用，含手册的任务镜像不发布；详见 [Docker 工作流](docs/docker-workflow.md) 与 A 审核。

2026-10-25 执行器更新：用户认为手工接力方式不合适，明确更换为 **两个 Luna High 子代理实现、主代理协调与独立验收**；此前 Antigravity + Gemini、DeepSeek 方案保留为历史。此变化只涉及开发协作，不更改参赛运行时模型候选和 5 元预算，也不承诺更少总 token 或固定节约比例。

**D0 离线工程与 A 官方环境/无模型只读工具接入已通过独立验收；模型与自主任务仍待后续阶段。** 下表及 A 审核优先于后续历史记录，用户完整验收及合并另行决定。

| 准备项 | 状态 | 依据与边界 |
| --- | --- | --- |
| 竞赛方向与路线 | 已整理/已明确 | 竞赛优先，医院侧任务起步；后续仍需覆盖赛事其他领域 |
| 手册访问和下载 | 已验证 | 2026-10-24 重新核对固定版本全量 1,292 文件字节数和 SHA-256，全部一致；公开规划子集 9 文件也全部一致 |
| 一个官方任务与实时工具 | 静态拆解及 A 接入已验证 | 发现 30 个角色 MCP 工具；固定 cases.list_cases({}) 返回有效空列表，不代表业务任务成功 |
| 第一阶段 OpenSpec | 已成文 | proposal/design/spec/tasks/handoff 齐备，已补充 Docker 内开发和镜像交付场景；引用与结构做静态检查，尚未运行 OpenSpec CLI |
| 分工、学习与交接 | 双 Luna 首轮闭环完成；D0 离线代码验收通过 | 子代理实现和 Docker 自测，主代理控制写入交接、固定候选并独立复验；学习记录只按用户实际回答更新 |
| 首轮参赛运行预算 | 已确认规划 | 模型工具接入验证＋一次任务试跑合计 5 元；写代码另行记账，当前未恢复付费运行 |
| 模型与 runner | 候选待实测 | `deepseek-flash`＋官方参考 runner，Chat Completions/思考 high 为候选；协议、字段与实际限额待验证 |
| 数据与官方环境 | 选定任务环境已验证；全量未下载 | 官方 checkout 4444a07、数据 5ce8810 的 7 文件子集及批准手册；真实官方 Python 3.12.15/arm64，独立新世界读取及正常清理通过，见 A 审核 |
| Docker 开发与兼容性 | 离线独立检查通过 | Python 3.13.17 与 3.12.15 / aarch64 各 115 项项目测试、19 subtests、6 项补充方法通过；A controller 20 项锁定依赖检查通过；真实官方镜像与其他架构分别取证 |
| 无评分执行入口 | 明确阻断未验证真实执行；干运行保留 | 依据 R1 明确阻断无 skip-judge 机制的 ungraded 真实执行，记录 unsupported 理由；保留干运行与离线模式 |
| 现有实现与基线 | D0 b7f8941 已通过；A 当前候选 a173409 | A 通过范围以分层审核为准；没有 Agent trial、官方 reward 或实测模型成本，不把工具探针记成任务成功 |
| 官方判分 | 已决定本地暂缓 | 最终私有评分交主办方；确定性检查优先、Gemini 按需辅助的集成仍待实现 |
| GitHub 存储与合并 | 私有仓库，工作分支/PR 交付用户 | [xsw932187210-cell/chi-agent](https://github.com/xsw932187210-cell/chi-agent)，后续 Codex 推送 codex 分支、创建 PR，由用户审核合并 main；内部代码验收不等于合并授权 |
| Kaggle 入场与材料 | 已接受规则；Writeup 待创建 | 已登录 Rules 页面显示接受规则和 Team 页签；Writeup、私有程序包和技术报告均未提交。最终截止为北京时间 2026-11-16 07:59 |

当前 D0 无代码返工待办；本轮只推进 A，B 模型工具往返及 C 一次自主执行继续暂停，见 [交接包](openspec/changes/bootstrap-baseline/handoff.md)。后续业务策略与自动压缩根据真实基线再细化。

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
4. 双 Luna 的 D0 离线工程及 A 只读工具接入已独立验收，见当前报告；B/C 仍暂停。先由用户处理本轮 PR，再决定下一阶段，不能从工具成功推断完整 Agent 能力。

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

本项目开发、测试与检查均在 Docker 容器内完成。下列为开发操作命令；Compose socket 挂载已移除，当前 D0 离线代码验收通过。固定候选的独立构建与无 socket 检查命令见 [验收报告](reviews/bootstrap-baseline-d0-review.md)。

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

## A：不调用模型的官方工具接入

本轮只恢复 A。入口是 `scripts/a_environment.py` 与独立 `compose.a.yaml`，只执行固定任务环境和脚本指定的只读查询；`run_baseline.py` 的 B/C 预算及无评分入口门禁保持原状。实际独立结果见 [A 审核](reviews/bootstrap-baseline-a-review.md)。

以下命令从 `chi-agent/` 目录执行，依赖安装、源码/数据下载和运行均在 Docker 内。先提供已有授权的 `data/skills/` 及 `data/source-downloads.json` 完整校验清单；首次缺官方 checkout 时，在开发容器中 clone 并 checkout `project.yaml` 的固定提交。默认离线 `dev` 不挂 socket。

```sh
docker compose build dev
# 首次获取官方源码；若已有固定 checkout，直接运行下方 check
docker compose run --rm dev sh -ec 'git clone --filter=blob:none https://github.com/actava-ai/chi-bench vendor/chi-bench
git -C vendor/chi-bench checkout 4444a07fa68a4f1623f841a292a54e284fc8e7f7'
docker compose -f compose.a.yaml build a-control
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py check
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py download-data
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py build-image \
  --run-id a-new-unique-id
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py run-probe \
  --run-id a-new-unique-id --probe-script /workspace/scripts/a_tools_probe.py
```

一次镜像准备与探针使用同一个新 run-id；已有运行目录或任务资源的 ID 会被拒绝并保留，下一次验证换新 ID。首次 `build-image` 单独允许 1800 秒，日志静默等待最多 300 秒，总时限在事件之间检查；`run-probe` 仍为 900 秒，普通 Docker API 仍为 30 秒。`run-probe` 沿用固定官方 entrypoint，等待 MCP 启动完成后只调用 `cases.list_cases({})`，最后清理本次任务容器与网络。它不启动 Agent、模型或 verifier；查询会产生读取审计，不能据此声称自主任务成功。原始 schema、响应、阶段状态和清理记录保存在忽略的 `runs/a-environment/<run-id>/`。

A controller 通过 `HOST_PROJECT_ROOT=${PWD}` 解析引擎看到的挂载源；必须从实际项目目录运行。其他 Docker 主机通过 `DOCKER_HOST_SOCKET` 指定已有 socket，不在 Mac 安装项目包。任务容器使用内部网络、不发布端口，只挂结果目录和只读探针，不接收模型/判分凭据。

用户已明确允许官方启动必需的 `fixtures/expectations.json` 仅供无 Agent 的隔离服务初始化。探针不读取评分文件。下载只含固定 7 文件子集，完整数据集仍未补齐；本地官方任务镜像含授权手册，不上传 GitHub 或镜像仓库。默认开发/调度镜像通过 `.dockerignore` 排除受限资料。

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
