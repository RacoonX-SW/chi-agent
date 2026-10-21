# GitHub 存储与协作

日期：2026-10-21。用户要求沿用 `xsw932187210-cell`，新建仓库存储 CHI 项目代码。

## 仓库与目录

- 私有仓库：[xsw932187210-cell/chi-agent](https://github.com/xsw932187210-cell/chi-agent)。
- 本机 Git 根目录：`/Users/asaki/Documents/ChatGPT/Kaggle`，项目目录仍为其下的 `chi-agent/`；不另建嵌套 Git 仓库。
- `origin` 使用已有 SSH 认证：`git@github.com:xsw932187210-cell/chi-agent.git`。不创建或提交新的密钥。
- 沿用现有 `main` 分支；后续新建开发分支使用 `codex/` 前缀。

首次备份保留旧提交与当前草稿，包括 OpenSpec、说明文档、自有脚本、测试和离线验收材料。旧 bootstrap 实现与未复验的返工仍是待修候选，不能因已经推送而称为已验收或可运行。

## 上传边界

不上传 `.env`、令牌、私钥、下载手册、数据集、vendor checkout、本地环境、`.coordination/`、真实运行轨迹或含受限内容的产物。根目录和项目的忽略规则共同覆盖本地目录；提交前仍须检查实际暂存清单，忽略规则不会自动移除已经跟踪的文件。

`reviews/` 目前只有旧离线验收说明和合成 fixture 观察；没有真实任务产物。后续报告只保存允许披露的汇总及版本身份。私有仓库同样是向 GitHub 上传，不能用“私有”代替资料授权。

## 后续分工

1. DeepSeek 按已授权的有界任务实现、自测并交付稳定候选，可先本地 commit。
2. Codex 检查差异与上传范围，按阶段独立验收并记录结果；由 Codex 处理 GitHub push。用户参与方向、学习和最终验收。
3. 日常备份可保存明确标注的待验收候选；阶段交付是否通过，以验收记录为准。公开发布、Kaggle 提交和付费运行按各自授权处理。

本次只配置 GitHub 与保存现状，没有恢复功能编码、派发 DeepSeek、启动后台唤醒或调用付费模型。

## commit 和 push 的区别

`commit` 在本机 Git 历史中保存一个版本；`push` 将选定分支的提交发送到 GitHub。执行器只做本地 commit，其他电脑或新执行器仍需访问同一本机目录，或者等 push 后再从 GitHub 获取。两者都不能证明代码正确。

接手时检查 `git status`、`git log`、`git remote -v` 与分支的上游状态；不要重置或覆盖他人未提交的工作。GitHub 不是本次竞赛的自动提交入口。
