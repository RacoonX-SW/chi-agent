# 从 Antigravity 切换到 DeepSeek：交接状态

日期：2026-10-20（Asia/Shanghai）。最新用户要求：**暂停编码，先完成项目规划；之后在新对话由 DeepSeek 接手。**

2026-10-21 补充：下文是 10 月 20 日的切换快照，不代表当前手册、数据或预算仍未确认。手册访问/下载已验证，首轮参赛运行预算已选 5 元；编码及付费运行仍暂停。当前接手依据为 [分段交接包](../openspec/changes/bootstrap-baseline/handoff.md)：先 D0 离线修复，再按授权与验收推进 A/B/C；历史 Antigravity 身份和旧交付标记不复用。本轮仅整理文档，没有派发 DeepSeek 或修改实现。

## 当前文件与 Git 状态

2026-10-21 GitHub 更新：已按用户要求建立私有的 [xsw932187210-cell/chi-agent](https://github.com/xsw932187210-cell/chi-agent)，由 Codex 配置远端和备份当前草稿。下面的“没有 remote/未提交”是 10 月 20 日快照，接手时以实际 `git status`、`git log` 和 `git remote -v` 为准；备份不改变旧候选未验收状态。目录与后续分工见 [GitHub 协作约定](github-workflow.md)。

- 项目目录：`/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent`。
- 当前 Git 根目录：`/Users/asaki/Documents/ChatGPT/Kaggle`。
- 最近提交：`9a347195fc786c69db5ecddd4c1b2d50615eb682`，首轮离线实现。
- 当前没有配置 remote，没有 push 到 GitHub。
- Antigravity 返工改动保留在 `scripts/run_baseline.py` 和 `tests/test_readiness_and_baseline.py`，尚未形成新提交，也没有 ready_for_review 交付标记。
- 验收报告与规划文档也有未提交改动；接手时不要覆盖、清理或把它们误当成执行器自己的修改。

## 验证状态

- 原提交 30 项离线测试由 Codex 独立运行通过，但存在未覆盖生产入口的测试，以及 CLI/单任务选择/判分缺陷，原提交未通过验收。
- 实施中的第一次返工也出现了配置层级和判分验证问题；Codex 已在 review-feedback 中澄清。返工版本未完成复验，不能沿用原 30 项测试数字证明它正确。
- Antigravity 原会话显示额度耗尽错误，当前没有正在执行的任务。
- vendor、数据、真实运行输出未就绪；未进行真实模型基线评测。API、手册批准和报名状态没有在本聊天确认。
- 后台聊天定时检查的创建请求被拒绝，未启用自动唤醒。

## 读取顺序

1. 本文与 `docs/project-planning-v0.md`：理解暂停原因、未确认范围和当前候选状态。
2. 上一级 `COLLABORATION.md`：分工及用户最新约束；其中暂停安排优先于早先的任务派发授权。
3. `reviews/bootstrap-baseline-2026-10-20.md`、配套 observations JSON。
4. `openspec/changes/bootstrap-baseline/review-feedback.md` 及原变更文件。
5. 当前代码和实际 Git 差异；只在用户确认重新开发后，建立新的基线并运行对应检查。

## 切换原则

项目由普通 Python 文件、Markdown 规格和 Git 差异组成，不依赖 Antigravity 私有会话格式。DeepSeek 可读取同一目录继续工作，无需重写业务技术栈。

交接材料必须在仓库内，不只保存在 Antigravity brain/聊天记录。API 端点、模型完整名称、环境变量和实际执行器配置在恢复开发时核实，凭据保存在本地配置中。

先完成项目规划并标注已确认/待确认项，再决定哪些 bootstrap 代码保留、修复或替换。不要把接手等同于接受当前实现。

本次本地保全记录位于忽略目录 `.coordination/transition-2026-10-20/`，包含代码/测试差异和源文件摘要；它不等同于新提交或验收通过。
