# D0 开工与审核 Prompt

日期：2026-10-24。供用户复制到新对话，不表示本文件建立时已经恢复编码或启动执行器。

## 交接顺序与并行边界

1. 在同一本地工作区新开 Codex 对话，发送下方 Codex Prompt，先核对并保存规划基线。
2. 取得基线提交和分支后，将 Gemini Prompt 交给 Antigravity 中的 Gemini。
3. Gemini 完成 D0、自测、提交并停止修改；用户把候选 SHA 或交付报告路径发给新 Codex 对话。
4. Codex 审核并给出结论，用户转交返工意见或接续已授权任务。

当前同一工作区采用串行交接：Gemini 实现 → 停止修改 → Codex 审核 → Gemini 返工或后续开发。仅切换分支不能隔离同一工作区的并发修改。若以后需要审核旧候选时并行开发，须使用独立 worktree/checkout、固定候选提交及隔离的容器/结果目录，并在合并后验证；当前不自动建立该流程。D0 后的 A/B/C 也不因并行意愿而自动恢复。

## 给新 Codex 对话

```text
请在 /Users/asaki/Documents/ChatGPT/Kaggle 接续 CHI-Bench 项目。现在只恢复 bootstrap-baseline/D0 的开发协作：我自行指挥 Antigravity 中的 Gemini 写代码，你负责规格、独立审核、教学和 GitHub 存储。不要操作、调试、监控 Antigravity，也不要向它派发任务。A/B/C 和参赛模型付费运行仍暂停。

先读 AGENTS.md 指定的当前协作、学习和项目状态摘要，以及 chi-agent/reviews/REVIEW_STATE.md；再读 chi-agent/openspec/changes/bootstrap-baseline/handoff.md 的 D0 摘要、具体任务和对应规格。历史长记录、源码和日志按需读取。

开始时：
1. 核对 Git 根目录、分支、实际 HEAD 和未提交文件。Git 根目录为 Kaggle，项目在 chi-agent/，不要另建嵌套仓库。
2. 当前有上一轮 Docker/OpenSpec/协作规划改动尚未提交。检查这些文档的实际差异，用明确文件清单将本项目已核对的规划单独做本地 commit，向我报告基线 SHA 和分支。保留其他既有改动，不使用 git add .、reset 或强制清理；不夹带实现改动、凭据、手册、数据和真实日志。当前不必为准备工作先 push。
3. 确认 Gemini 的 D0 范围和报告位置已明确。没有新的稳定候选时，只完成交接准备并回复我；不自行实现 D0、不审核旧候选冒充新交付，也不持续轮询等待。

我通知“Gemini 已完成 D0”并给出候选 SHA 或交付报告路径后，请直接开始独立审核：
- 先固定实际基线/候选及工作区身份，比较差异，再读相关入口、调用者、配置和必要测试。首次 D0 还需核对旧实现与未解决问题，不能把原候选视为已通过。
- 依赖安装、测试和调试全部在 Docker 内完成。候选与当前文件不一致时，先取得隔离且可复现的候选环境，不覆盖他人改动，也不把另一份代码的测试结果记给该提交。
- 检查实际生产入口与相关正常/失败路径，区别执行器自测和你独立重跑的结果；不调用参赛模型、judge 或真实任务，不自动启动 A/B/C。
- 不直接修改候选实现。发现问题时，给出具体位置、触发条件、影响和可转交 Gemini 的修复要求；审核期间 Gemini 停止写入同一工作区。
- 将结论写入 chi-agent/reviews/bootstrap-baseline-d0-review.md，更新 REVIEW_STATE.md，分别记录“已审”和“已通过”身份、未运行项与遗留问题。按阶段处理 GitHub 备份，推送前检查上传范围；备份不等于验收通过。
- 我希望边参赛边学习：围绕本轮真实代码讲一两个关键概念，给一个简短理解问题，并更新 learning-agreement.md；没有回答或实践证据，不记为已掌握。教学不作为继续工作的门槛。

当前没有真实 trial 或官方 reward，旧离线候选及返工尚未通过新验收。不要把文档、commit、自测或未评分执行写成竞赛任务已通过。
```

## 给 Gemini / Antigravity

```text
请在 /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent 实现 CHI-Bench 的 bootstrap-baseline/D0。现在明确恢复 D0 编码与容器内构建/离线测试；A/B/C、参赛模型 API 和官方判分不在本次范围内。你负责实现和自测，Codex 随后独立审核。

Git 根目录是 /Users/asaki/Documents/ChatGPT/Kaggle。先读取根目录 AGENTS.md 的当前约定、COLLABORATION.md 的当前协作方式，以及 chi-agent/openspec/changes/bootstrap-baseline/handoff.md 的“D0 开工摘要”和“第一份 D0 的具体任务”；按需读取对应 proposal/design/spec/tasks、Docker 工作流和旧返工意见，不全量载入历史聊天或第三方源码。

先核对新 Codex 对话已保存的规划基线提交、当前分支/HEAD 与未提交改动，记录实际起始身份。沿用交接分支，保留既有差异；不要 reset、全量暂存或把无关改动混入交付。

按现有 OpenSpec 完成：
1. 最小 Docker 开发环境、声明并锁定依赖、受控构建上下文、源码/结果持久化。项目依赖、下载、测试和调试均在 Docker 内进行，不在 Mac 安装项目 Python/uv/Node/OpenSpec。自有开发容器首选 Python 3.13，保留固定官方任务环境的 Python 3.12 契约；未验证部分如实报告。
2. 修正单题配置与命令生成，拒绝多题/多尝试误配置；按模式检查就绪，不将 Anthropic 凭据作为所有离线操作的统一前提。
3. 正确区分未评分、reward 为 0、缺判分和进程失败；参数错误、干运行、异常/超时、未知用量及预算停止有明确记录。D0 只验证限额/预算的离线逻辑，不宣称真实 runner 中已生效。
4. 用合成 fixture 和必要外部边界替身检查实际生产入口、配置、argv、manifest 与退出状态；覆盖相关正常/失败路径，完成容器内可复现自测。

构建可以下载声明的开发依赖；D0 测试不依赖真实病例、完整任务世界、实时 MCP 或模型服务。受限资料、密钥和真实轨迹不进入提交或自有交付镜像。不要捏造跳过 judge 的官方参数，不重写官方模拟器或评分器，不扩展网页、多 Agent 或上下文压缩。需要改变外部行为/验收标准时，先报告具体差异，不自行改写规格后宣称通过。

交付要求：
- 只显式暂存本次 D0 相关文件，做稳定的本地 commit，不 push、不代勾 Codex/用户验收。记录实际执行器、基线 SHA、候选 SHA 和仍存在的未提交差异。
- 维护一份 chi-agent/reviews/bootstrap-baseline-d0-handover.md：主要变更及关键入口、实际 Docker 命令/退出结果与日志位置、未验证项/失败项、必要设计取舍。不要重复粘贴整段日志或另写多份长总结。
- 候选 SHA 应包含交付代码与报告。报告可在提交前写明基线及文件范围，提交后在最终回复中提供候选 SHA，不为把提交自身的 SHA 写回报告反复提交。
- 最终回复“ready_for_review”，附基线 SHA、候选 SHA、分支、报告路径和测试结果摘要；之后停止修改，等待用户转交 Codex 审核意见。不自动进入 A/B/C。

遇到无法解决的环境/权限或上游契约问题，保存实际证据并报告完成范围和具体阻塞，不伪造测试、官方 reward 或完成结论。
```

## Gemini 完成后通知 Codex

```text
Gemini 已完成 bootstrap-baseline/D0，已停止修改。
候选：<Gemini 给出的 commit SHA>
报告：/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/reviews/bootstrap-baseline-d0-handover.md
请按既定规格独立审核，并结合实际代码讲解。
```
