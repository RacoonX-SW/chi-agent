# CHI Agent 协作入口

从根 [README](README.md) 查运行方法，从 [审核接续状态](openspec/REVIEW_STATE.md) 查当前候选、授权和未决事项。规格及活动变更由 [OpenSpec](openspec/) 管理。

## 开发与交付

- 新功能、行为变更和较大迁移先查现有规格及活动 Change。OpenSpec 提案经用户明确批准后再实施。批准依据写入提案，进度由对应 `tasks.md` 记录。
- 默认由一名 `gpt-6.1-terra` / `high` 子代理实现并做 Docker 自测，主代理固定候选、独立复验并负责 GitHub 交付。同一工作区同时只有一名实现写入者，额外并行任务按用户与项目约定安排。普通文档和 Git 操作由主代理处理。专项分工以对应变更的批准记录及当前审核状态为准。
- 从最新 `origin/main` 建实现分支。主代理审阅差异、显式暂存、提交和推送，创建以 `main` 为目标的 PR。用户负责最终验收和合并。验证结果记入 PR，变更按审批范围同步规格并归档。
- 正式 trial 由参赛 Agent 自主执行，人工复盘与改进在评测结束后开展。

## Docker 与资源

- 安装、下载、调试、测试和运行在 Docker 内完成，开发和调度使用 Python 3.12。容器按所选角色和调用方资源配置绑定挂载。
- 凭据、受限手册、任务数据、vendor checkout、原始账本、轨迹与运行目录留在本地。测试使用隔离临时输出，只读挂载明确需要的资源。评测期望和 verifier 材料仅由评审侧使用。
- 参赛运行模型、费用、真实调用和官方评分以当前授权为准。账目保留历史身份、失败和未结算状态。

## DeepSeek API 调用时段

DeepSeek 官方 API 直连的 B/C、患者确认及开发评审在北京时间工作日 09:00–12:00、14:00–18:00 避开新请求。经 OpenCode 调用 DeepSeek 按已批准范围安排。具体窗口及执行边界见[原时段约定](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/COLLABORATION.md#deepseek-api-调用时段2026-10-28)。

## 外部资料

网络研究优先使用内置搜索、浏览和 finance 工具，引用官方一手来源。按用户明确要求或在内置工具无法取得必要复杂页面时使用 Firecrawl。
