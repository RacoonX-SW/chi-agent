# 项目协作入口

以下约定适用于本工作区的 CHI-Bench 参赛工作。用户后续的明确指令优先于这里的历史状态。

## 开始或接续对话时

先读取以下入口的当前摘要；历史记录、完整源码和长日志按本轮需要再读，不默认全量重读：

1. [协作约定](COLLABORATION.md) 的“当前协作方式”。
2. [学习约定](chi-agent/docs/learning-agreement.md) 的教学方式、当前进度和下一次入口；追加历史按需查阅。
3. [CHI 项目状态](chi-agent/README.md) 的当前准备状态，以及 [审查接续状态](chi-agent/reviews/REVIEW_STATE.md)。
4. 只读本轮涉及的 OpenSpec、代码差异及相关调用代码；参赛路线见 [competition-route.md](chi-agent/openspec/competition-route.md)。完整协作流程见 [GitHub 与本地审核约定](chi-agent/docs/github-workflow.md)。

## 必须延续的用户偏好

- 首要方向是按照 Kaggle CHI-Bench 官方要求参赛；同时教用户理解 Agent 开发，包括设计过程、模型与程序的分工、tool 调用、运行状态、调试和评测。
- 在重要设计、实现和验收节点主动讲解，不只交付代码或让用户确认结果。每次围绕当前任务讲少量概念，结合实际材料、代码或轨迹，再给一个简短理解问题。
- 区分“已经讲过”“用户能解释”“用户实际应用”；没有用户回答或操作证据，不得把某知识点标为已掌握。
- 把学习进度、用户疑问和下一步更新到学习约定文档，方便新对话继续。没有实现或没有核对的源码，不能编造函数调用链。
- 学习嵌入竞赛推进，不把完成整套课程或通过测验设为继续开发的前提。

## 当前边界（2026-10-24 更新）

- 用户自行操作 Antigravity，将任务和返工意见交给 Gemini；Codex 负责规格、独立审核、教学与 GitHub 存储，不再控制、调试或向 Antigravity 派发任务，也不轮询其界面。此要求撤销早先的自动派发与自动返工授权。交付后由用户发一条通知，附候选提交或报告路径；没有后台自动验收安排。
- 审核优先比较稳定的基线/候选提交，读取差异、相关入口/调用者/配置与必要测试；不默认重读整个项目或执行器对话。首次接手、范围扩大或接口/依赖变化时按实际影响补读。记录“上次已审核”和“上次已通过”的提交，不能因摘要或 commit/push 就认定实现正确；见 `chi-agent/reviews/REVIEW_STATE.md`。
- 用户最新要求 Docker 内开发、调试与交付：项目依赖安装、下载、测试、运行均在容器中进行，宿主机保留 Docker Desktop、编辑器/Git 与源码。不要把宿主机缺 uv/OpenSpec/PyYAML 当成必须在 Mac 安装的缺口。自有开发容器首选 Python 3.13；固定官方任务镜像实际为 Python 3.12，保持其兼容性并分别验证。详见 `chi-agent/docs/docker-workflow.md`；D0 的开发容器构建和离线自测由用户指挥 Gemini 完成，Codex 不自行实现。

- 2026-10-24 用户在本次接续中明确仅恢复 `bootstrap-baseline/D0` 开发协作：先由 Codex 核对并单独本地提交规划基线，用户再自行指挥 Gemini 实现；稳定交付后提供候选 SHA 或报告路径，Codex 再审核，不持续轮询。A/B/C、参赛模型 API 和官方判分仍暂停。此前耗尽的是 Antigravity 中的 Claude 额度，用户报告已有 Google AI Pro，当前优先 Antigravity + Gemini 3.8 Flash-High，DeepSeek 备用。旧准备审计确认的客户端/额度不等于本次交付能力已验证，也不改变参赛 Agent 的运行时模型候选和 5 元预算。
- 最新准备审计见 `chi-agent/docs/preparation-audit-2026-10-24.md`：规划可支持恢复 D0；Docker 服务已核实可用，开发镜像/容器内依赖、完整数据/官方源码 checkout 与真实接入仍缺。Kaggle 已接受规则，Writeup 尚未创建；最终材料截止为北京时间 2026-11-16 07:59。
- 已完成一个官方任务的静态拆解；尚未运行真实 trial，实时 MCP schema、官方 reward、耗时和成本仍未测。
- 用户当前不为本地判分开通 Anthropic，最终私有评分交主办方。先规划离线、工具接入与无评分的真实开发执行；官方 reward 保持未知，部分 Claude 模拟对话的本地验证也需单独记录缺口。见 chi-agent/docs/development-preparation-2026-10-21.md。
- 判分认证更正：固定上游还支持 Claude Code 登录/OAuth，不可再断言原生 API Key 是唯一方式。用户目前仅有免费 Claude 账号，没有订阅；确定性检查可考察函数级非语义分支，完整评分仍未具备。见 chi-agent/docs/judge-access-options-2026-10-21.md。
- 网页工作台等独立产品形态已经搁置。医院侧是起步调试方向，不代表整个竞赛最终范围。
- 既有离线候选未通过独立验收，不能当作已验证的 Agent 实现或学习范例。
- 正式 trial 由参赛系统自主执行；教学、人工分析和改进在开发阶段及 trial 结束后进行，不在评测中替 Agent 选动作或修结果。

## 外部资料

网络研究优先使用内置搜索和浏览工具。仅在用户当前明确要求，或内置工具无法获取必要动态内容时使用 Firecrawl；作为后备时先说明原因。优先官方一手来源。
