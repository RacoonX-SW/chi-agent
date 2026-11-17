# Proposal

## Why

`src/chi_agent/` 目前将 42 个 Python 文件放在同一层，Agent 运行、工具、上下文、模型接入与交付代码的职责需要逐个打开文件才能辨认。按职责组织子包，可以让读者从目录定位实现，并继续通过现有命令构建和启动程序。

## What Changes

- 将 35 个模块归入 `agent/`、`context/`、`tools/`、`models/`、`accounting/`、`roles/`、`evaluation/` 七个子包，保留文件名，在包根保留 7 个初始化、入口和交付文件。完整迁移表见 `design.md`。
- **BREAKING** 内部模块导入路径调整为对应子包路径，仓库中的调用方、动态导入、测试补丁目标与资源定位同步迁移。
- 保留 `python -m chi_agent.cli`、`python -m chi_agent.bundle`、`python -m chi_agent.evaluation_bundle`、`python -m chi_agent.evaluation_cli` 及 Harbor 的既有入口与参数。
- 两种新导出包采用 v3 成员布局，按显式清单包含子包初始化文件。v1、v2 包继续使用各自冻结的成员清单验证。
- 复用现有离线验证入口和 Trace/Replay，对照固定主线与迁移候选的合成行为，再验证两种包的独立启动和历史包校验。

## Capabilities

### New Capabilities

本轮复用现有 `repository-distribution` 能力。

### Modified Capabilities

- `repository-distribution` — 补充正式源码按职责组织的要求，以及源码子包迁移后 v1、v2、v3 包身份与既有入口的兼容场景。

## Impact

- 基线为 GitHub `main` 的 `e2404fb495172b03d814ae4e8919e83f2ddd1058`，规划分支为 `codex/source-package-layout`。
- 影响 `src/chi_agent/`、引用这些模块的 `scripts/` 与 `tests/`、两类 bundle 的显式清单和身份读取，以及 README 与两份运行手册中的结构说明。
- 迁移验收以现有工具参数、业务判定、预算、费用和未知状态处理规则的行为一致性为依据。新包身份独立记录，历史 trial 继续绑定原冻结版本。
- 实施和验证限定于 Docker Python 3.12 的离线范围。凭据、数据、vendor、账本和真实轨迹使用原有本地位置。

## Review

2026-11-18 用户审核本版提案后明确回复“我觉得可以，按照这个方案实施吧”，批准按本提案、42 文件迁移表和对应增量规格实施。批准范围包含七个职责子包、现有根入口、两种 v3 导出包、v1/v2 验证兼容及 Docker Python 3.12 离线复验。实现与自测按根 AGENTS 交由一名 `gpt-6.1-terra` / `high` 子代理，主代理独立复验并交付 PR，用户最终验收和合并。
