# Python 3.12 环境对齐独立审核

2026-10-25；基线 `925d34b2b78c920b590f3bd8a43596f6ae327bdc`，固定候选 `726e80e5dc7ca5025179131b5e90802e74efc7ed`。结论：授权范围内通过；不恢复 B/C、参赛模型 API、Agent trial 或官方判分。

改动仅四个环境文件：开发基础镜像切换到缓存的 Python 3.12 固定 digest，controller venv 选择 3.12；两锁在 Docker 的 Python 3.12.15/uv 0.6.14 中以原版本作约束重新解析，包版本均保留。一个 `gpt-6-luna` / `high` 子代理实现/自测后停止写入，主代理另取 `git archive` 快照独立构建和复验。

| 独立验证的实际镜像 | ID |
| --- | --- |
| 开发（同时更新 latest） | `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3` |
| 调度（同时更新 latest） | `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3` |
| 复用的原官方任务镜像 | `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50` |

主代理实际检查均退出 0：

- 从候选 tar 分别执行 `docker build ... - < candidate.tar`，复用构建缓存；没有重建官方镜像、下载手册/任务资源/浏览器或清理全局缓存。旧 dev/controller 保留标签 `pre-python312-20261025-01`。
- `docker run --rm --network none ...` 内执行独立 `runtime_check.py`：两镜像的实际解释器、基础解释器及开发 venv 均为 3.12；当前平台 aarch64/arm64。开发 11 个锁定包加本项目、controller 20 个锁定包与安装 metadata 精确一致，无多余包；所需库可导入，无 socket/模型凭据。
- 两个 venv 的 `uv pip check`、固定快照 `python -m pytest -q`（115 passed、19 subtests）、offline readiness、单题 `run_baseline.py --dry-run`、两份 Compose 配置检查通过。干运行未执行任务或创建 manifest；其余模式仍报告缺口。
- 从独立调度镜像执行 `run-probe --run-id py312-review-20261025-01`，预先核对并复用上表官方镜像。Python 3.12.15、内部网络、无端口、预期挂载，Agent/runner/judge 均未启动；发现 30 个工具，仅 `cases.list_cases({})`，合法返回 `items_count=0`，model_calls=0、tool_retries=0。
- 独立 `probe_check.py` 只读取身份/摘要元数据，经 Docker API 确认本轮容器/网络均不存在，证据文件仍保留；未打开原始 MCP 响应、手册或评分文件。schema/响应哈希与先前 A 空列表证据一致。

原始证据留在忽略目录：主代理 `runs/python312-alignment/review/`（candidate.tar、构建/检查日志、两个独立检查脚本与元数据）；实现者 `runs/python312-alignment/selftest/`。真实任务记录分别位于 `runs/a-environment/py312-review-20261025-01/` 与 `py312-selftest-20261025-01/`，不上传 GitHub。

范围限制：其他架构、OpenSpec CLI、异常 daemon 中断的真实清理分支、模型往返及用量/账单、无评分 Agent 执行和官方 reward 仍未验证。正常 A 回归不替代这些证据；合并由用户决定。
