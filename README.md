# CHI Workflow Agent

面向 CHI-Bench 的医疗行政工作流 Agent，支持医疗机构授权申请（Provider）、保险方审查（Payer）和照护管理（CM）。Agent 通过官方 MCP 工具处理任务，程序负责上下文预算、工具调用校验、完成核验和可追溯的运行记录。[CHI-Bench](https://github.com/actava-ai/chi-bench)

## 阶段成果

在 75 个公开任务中，已核对至少 **20 个不同任务**有真实模型开发运行记录，覆盖 Provider 10 个、Payer 6 个和 CM 4 个。最近一组 `16384` 基线覆盖 Payer t022、t023、t024 和 CM anorexia、CKD、asthma。六题均提交完成声明并通过历史检查。各结果对应当时的冻结版本，`official_reward=null`。[成果证据](openspec/REVIEW_STATE.md#开发成果)

## Docker 快速开始

在仓库根目录构建 Python 3.12 开发镜像，导出 Go 程序包到尚不存在的目录。

```sh
docker compose build dev
docker compose run --rm --no-deps dev python -m chi_agent.bundle build --target /workspace/dist
```

`dist/` 包含启动入口、依赖锁和 `bundle-manifest.json`。两种程序包各有一份手册，涵盖外部依赖、预检和运行。[Go](docs/go-chi-entry-runbook.md) · [兼容评测](docs/evaluation-entry-runbook.md)

## 项目结构

| 路径 | 用途 |
| --- | --- |
| [src/chi_agent](src/chi_agent/) | Agent 运行、MCP、上下文、账本和导出包 |
| [scripts/development](scripts/development/) | 开发调度、资源检查和患者模拟 |
| [scripts/experiments](scripts/experiments/) | 早期探针、基线和实验 |
| [scripts/tools](scripts/tools/) | 构建、检查和运行汇总 |
| [tests](tests/) · [openspec](openspec/) | 回归测试和行为规格 |

### 离线合成轨迹回放

在项目 Python 3.12 开发镜像内，按 `scripts/tools/verify_offline.sh` 的依赖和只读源码挂载方式并禁用网络，提供可写的 `/out`，按以下命令运行。

```sh
python -m scripts.tools.replay_trace run --suite tests/fixtures/trace_replay_suite.json --output-dir /out/replay-baseline
python -m scripts.tools.replay_trace run --suite tests/fixtures/trace_replay_suite.json --output-dir /out/replay-candidate
python -m scripts.tools.replay_trace compare --baseline /out/replay-baseline/report.json --candidate /out/replay-candidate/report.json
```

每次 `run` 必须使用尚不存在的输出目录。报告汇总合成用例分母和实际观测的派发、状态及完成声明，附源码与环境身份。
