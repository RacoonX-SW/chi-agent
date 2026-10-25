# CHI Workflow Agent

面向 Kaggle CHI-Bench 的 Agent 开发项目，随参赛学习设计、工具调用、调试和评测。

## 阅读入口

| 需要了解 | 文档 |
| --- | --- |
| 当前阶段、授权、验收身份、PR 与下一步 | [审核接续状态](reviews/REVIEW_STATE.md) |
| 代理分工与文档职责 | [共同协作约定](../COLLABORATION.md) |
| 环境、Python 版本目标与容器边界 | [Docker 工作流](docs/docker-workflow.md) |
| 分支、PR 与上传范围 | [GitHub 工作流](docs/github-workflow.md) |
| 教学方式、理解进度与下一学习点 | [学习约定](docs/learning-agreement.md) |
| 参赛路线与当前变更范围 | [参赛路线](openspec/competition-route.md)、[bootstrap-baseline](openspec/changes/bootstrap-baseline/proposal.md) |
| 验收契约与实现任务 | [验收场景](openspec/changes/bootstrap-baseline/specs/benchmark-readiness/spec.md)、[任务](openspec/changes/bootstrap-baseline/tasks.md) |

本页只维护运行方法与入口；阶段结果和详细证据集中到状态页及其链接的阶段报告。命令示例中的模型名称不表示已经可用或获准调用。

## Docker 开发与离线自测运行

以下命令均从 `chi-agent/` 目录执行，依赖与检查在 Docker 内完成。默认 `dev` 不挂 Docker socket；版本选择与缓存规则见 [Docker 工作流](docs/docker-workflow.md)。构建命令按需执行，可复用未变的镜像。

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

入口为 `scripts/a_environment.py` 与独立 `compose.a.yaml`，执行固定任务环境和脚本指定的只读查询。使用前核对 [当前授权](reviews/REVIEW_STATE.md)；这里列出操作方法，历史验收证据由该状态页链接。

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

## 资料来源

核对日期：2026-10-19。

- [官方仓库与安装说明](https://github.com/actava-ai/chi-bench)
- [官方单任务 Quickstart](https://www.actava.ai/benchmarks/docs/quickstart)
- [自定义 Agent 接入](https://github.com/actava-ai/chi-bench/blob/main/docs/extending.md)
- [OpenSpec 结构与场景格式](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)

依赖版本、任务 ID 和命令以实施时固定的上游提交及对应文档为准；不把示例模型名当作已经可用的配置。
