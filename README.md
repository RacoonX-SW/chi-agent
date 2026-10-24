# CHI Agent

面向 Kaggle CHI-Bench 竞赛的 Agent 开发仓库。当前保存规划、OpenSpec、学习记录和待验收的 bootstrap 代码；尚无真实任务运行、官方分数或已通过验收的 Agent。

- [项目状态与参赛路线](chi-agent/README.md)
- [第一阶段任务与验收交接](chi-agent/openspec/changes/bootstrap-baseline/handoff.md)
- [边参赛边学习的约定](chi-agent/docs/learning-agreement.md)
- [GitHub 存储与协作约定](chi-agent/docs/github-workflow.md)

保留现有目录结构：本仓库根目录对应本机 `Kaggle/`，项目代码位于 `chi-agent/`。接续开发先读取 [AGENTS.md](AGENTS.md) 和 [COLLABORATION.md](COLLABORATION.md)。

后续代码和文档先在 `codex/<任务名>` 工作分支开发，由 Codex 推送并创建目标为 `main` 的 PR，用户审核后决定是否合并。Codex 不直接开发/推送 main，也不自行合并；具体见 [GitHub 协作约定](chi-agent/docs/github-workflow.md)。

D0 已通过当前开发目标下的离线代码验收；A/B/C、参赛模型 API 和官方判分仍暂停。分支 push、PR 创建、独立检查与用户合并分别记录，不等于已向 Kaggle 提交参赛材料。

手册、数据集、凭据、本地环境和真实运行产物只保存在本地，不纳入仓库。已有验收记录中的模拟观察不是真实 trial 结果。
