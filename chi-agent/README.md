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

## B：离线合成模型工具往返

复用已构建的 `chi-agent-dev:latest`，从本项目目录执行。只挂载脚本和输出目录，显式使用镜像内的 venv；不需要 `.env`、官方资料或 Docker socket。

```sh
mkdir -p runs/b-model
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/runs/b-model:/workspace/runs/b-model:rw" \
  -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python scripts/b_model_probe.py \
  --run-id b-offline-example-001 --scenario success
```

每次使用新的 run-id；同名输出会拒绝覆盖。可将 `--scenario` 改为 `post-tool-rejection`、`post-tool-timeout`、`missing-usage` 或 `invalid-call` 观察失败记录；`--mode live` 会明确拒绝。成功退出 0，受控停止/失败退出 1，非法或重复 run-id 退出 2。输出位于 `runs/b-model/<run-id>/evidence.json`。

成功示例经过两轮合成工具往返和最终响应。请求中的工具选择与返回都来自手写 fixture；候选模型/模式字段、用量及价格只作离线协议和合成核算检查，真实 provider usage/cost 与 official reward 为 null。真实模型传输、官方 runner 集成与任务执行须另行恢复并验证，实际验收范围见 [审核状态](reviews/REVIEW_STATE.md)。

## C：离线单次执行控制

`scripts/c_run_control.py` 的 `plan` 只预览候选单题配置，不写文件或取得 attempt claim；`rehearse` 在纯 Python 合成 backend 上演练创建、运行一次和清理；`live` 明确拒绝。复用现有镜像，从本项目目录执行：

```sh
# 只读计划；没有真实 B 花费等证据时，预算就绪状态仍为 unknown
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD/scripts:/workspace/scripts:ro" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/c_run_control.py plan --run-id c-plan-001 \
  --agent openai-agents --model deepseek-flash

# 独立的合成演练账本，只挂脚本和输出
mkdir -p runs/c-demo-001
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/runs/c-demo-001:/workspace/runs/c-control:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/c_run_control.py rehearse --run-id c-demo-001 \
  --agent openai-agents --model deepseek-flash --scenario success
```

同一输出根目录对应一个持久合成账本，按固定 campaign/task/upstream 限制一次尝试；换 run-id 仍会 `claim_conflict`，相同 run-id 则拒绝覆盖原证据。失败、超时和清理错误也保留 claim。需要独立测试场景时使用另外的隔离合成目录；这些目录不接入真实执行机会或账单。

其他 `--scenario`：`runner-rejection`、`timeout`、`partial-create`、`cleanup-failure`、`unknown-budget`、`missing-usage`。manifest 位于映射输出中的 `runs/<run-id>/manifest.json`，claim 位于 `claims/synthetic/`。有效 plan/完整演练退出 0，阻断、claim 冲突或受控失败退出 1，非法输入/已有 run-id/live 拒绝退出 2。

配置中的 harness、模型轮数和时限均为 `configured_unverified`；此处没有运行官方世界或 Agent，也未实现官方 runner 的逐请求预算 hook、硬取消或跨目录/跨主机全局幂等。真实 usage/cost/reward 为 null，任务结果 unknown；实际验收及真实接入缺口只查 [审核状态](reviews/REVIEW_STATE.md)。

## 模型与官方 runner 接入层：离线集成

`scripts/model_runner_adapter.py` 使用固定官方 `run_agent()` 与真实 SDK 循环，HTTP 响应和工具均为合成替身。`plan` 只预览，`offline` 捕获实际 SDK 序列化，`live` 固定拒绝；原 baseline/B/C 门禁仍保留。使用前核对 [当前授权与验收](reviews/REVIEW_STATE.md)。

从本项目 `chi-agent/` 目录执行。可选 SDK 单独安装到 Docker 卷，复用现有 Python 3.12 镜像，不改基础镜像或 `requirements.lock`。安装需要包下载网络，不需要模型凭据：

```sh
docker run --rm \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/requirements-model.lock:/workspace/requirements-model.lock:ro" \
  -v chi-model-deps:/model-deps -w /workspace chi-agent-dev:latest \
  sh scripts/install_model_dependencies.sh /model-deps
```

离线命令不挂 `.env`、data、手册或 Docker socket；vendor 只提供固定源码。先按 A 的源码获取说明准备 checkout，已存在时复用。每次换一个新的 run-id：

```sh
mkdir -p runs/model-runner
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$PWD/runs/model-runner:/workspace/runs/model-runner:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/model_runner_adapter.py offline --run-id sdk-offline-001 --scenario success
```

将最后一行的参数换为 `plan` 可查看无评分直接 runner 路径；这条路径不调用 `cb experiment run` 或 verifier，也不添加上游 skip-judge 参数。候选模型、工具选择、用量与价目都是合成验证输入，真实 provider usage/cost/reward 仍为 null，任务结果 unknown。真实 tokenizer、服务端计量和价格尚不能由离线字节界限证明；后续真实运行须另行恢复并验收。

证据为 `runs/model-runner/<run-id>.json`；身份在 runner 执行前独占，重复身份不会重跑或覆盖。正常合成完成退出 0，受控失败退出 1，非法/重复身份或 live 拒绝退出 2。可用 `--scenario post-tool-429`、`missing-usage`、`invalid-final-usage`、`batch-valid-then-invalid`、`empty-history` 观察错误、用量未知和空历史字段；其他场景见 `--help`。独立验收与限制集中在状态页链接的接入层报告。

## 真实 B 运行准备：只读预检与合成账目

`scripts/b_live_preflight.py` 提供 `plan`、`preflight`、`rehearse` 和固定拒绝的 `live`。profile 在 `profiles/deepseek-flash-prepared.json`，来源/核对日期、CNY 峰值上界、完整上下文预留及有限生成参数均明确保存；不把文档推断写成 tokenizer 或账单实测。使用前核对 [当前授权](reviews/REVIEW_STATE.md)。

本通用入口的默认策略在 `profiles/local-development-policy.json`，用于本地开发；5 元是首轮 B/C 的共享开发限额。下方评测策略参数用于只读预检与合成演练，使用独立身份和状态，不继承本地余额/账本/限额。交付包的固定默认入口见下节“评测专用入口与干净目录包”；完整最终冻结和真实启动仍需完成 [F.5 及后续真实验收](openspec/changes/bootstrap-baseline/tasks.md#f-separate-development-budgets-from-official-evaluation)，`live` 在所有策略下继续拒绝。

从本项目目录执行。基础镜像即可读取 plan/preflight；没有可选 SDK 或真实预算证据时会受控报告缺口。以下命令不挂凭据、模型依赖、官方资源或结果目录：

```sh
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/profiles:/workspace/profiles:ro" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/b_live_preflight.py preflight
```

改为 `plan` 可查看配置与最坏请求预留。真实预算缺失时 `preflight` 通常退出 1；即使显式提供已核对的 `--budget-evidence <路径>` 并取得技术核对结果，也仍为 authentication unverified / execution paused。该只读文件的格式由 `validate_budget_evidence()` 定义；不应拿 synthetic journal 充当真实花费依据。`live` 退出 2，不因配置或文件而解除暂停。

下面在同一官方循环/真实 SDK 中演练新的通用 guard，复用上一节 `chi-model-deps` 卷。这个挂载目录只保存 synthetic 账目，默认演练 cap 对齐 5 元目标，真实 B/C 账目仍未初始化；首次使用一个新的合成目录：

```sh
mkdir -p runs/b-provider-preflight/rehearsal-example-001
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/profiles:/workspace/profiles:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$PWD/runs/b-provider-preflight/rehearsal-example-001:/workspace/runs/b-provider-preflight/synthetic:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/b_live_preflight.py rehearse --run-id prepared-example-001 --scenario success
```

完整演练退出 0，其他结果以非零退出及 `safe_error_code` 标记。run-id 独占记录、`synthetic-accounting.json` 和持久 flock 文件在目录内保留。timeout、unknown usage 或中断产生的 pending 不自动清除，换 run-id 仍会阻断；settled 花费和已持久化 cap 也不随重启重置。需要独立错误场景时用另一个明确合成目录，例如 `--scenario post-tool-503`、`missing-usage`、`duplicate-call-id`。旧 schema/损坏账目拒绝，不删除历史证据或自动迁移。

这只验证受控传输、预算账目和预检代码。认证、真实 prior spend、服务端计量/响应模型与账单仍未验证；实际结果与限制集中在状态页链接的阶段审核。

### 评测预算策略的离线演练

`--execution-scope evaluation` 显式选择评测策略：`--evaluation-policy record_only` 记录用量/估算而不施加金额硬停止，`--evaluation-policy capped --evaluation-cap-cny 7` 则使用明确的每 trial 上限。两者都保留请求/历史/工具/usage 校验和零重试。评测 preflight 不需要开发期 `--budget-evidence`；不要同时提供该参数，也不要将合成估算当成主办方账单或已授权真实执行。

以下命令使用固定合成场景，在同一真实 SDK/官方循环中产生三次合法请求，累计估算超过 5 元，证明 record_only 没有继承本地限额。挂载目录仅保存本轮合成记录：

```sh
mkdir -p runs/evaluation-budget-policy/example-001
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/profiles:/workspace/profiles:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$PWD/runs/evaluation-budget-policy/example-001:/workspace/runs/evaluation-policy-rehearsal:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/b_live_preflight.py rehearse --execution-scope evaluation \
  --evaluation-policy record_only --evaluation-id eval-example-001 \
  --task-id task-a --attempt-id attempt-1 --run-id eval-task-a-001 \
  --scenario evaluation-over-five
```

同一 evaluation 固定 policy/profile 身份，不能在后续任务换模式或 cap；演练另一策略时用新的 evaluation-id。每个 task/attempt 的状态独立，换 run-id 不能重跑已占用尝试，失败/pending 的证据也保留；另一个合法 task/attempt 可继续。`plan`/`preflight` 支持相同策略参数且只读；evaluation preflight 的退出 0 只表示策略检查结束，SDK 身份可能仍 unavailable，完整运行就绪须分别核对。`live` 始终退出 2，正式提交配置与主办方真实运行结果仍未冻结/验证。

## 评测专用入口与干净目录包

`scripts/evaluation_entry.py` 是包内固定入口，默认使用 evaluation `record_only`、金额上限 `null`，不提供开发预算、scope 或 cap 参数。默认模式为只读 `plan`；`rehearse` 仍使用真实 SDK/官方循环和合成 HTTP/工具。包和 entry 配置经严格核对后，内容身份会绑定到 evaluation 的 registry/claim。`live` 固定拒绝；本节提供离线交付准备方法，完整正式冻结与实际接入范围见 [审核状态](reviews/REVIEW_STATE.md)。

从项目 `chi-agent/` 目录导出。复用现有基础镜像，无需 SDK、凭据或官方资源；目标目录必须尚不存在：

```sh
mkdir -p runs/evaluation-entry-bundle/exports
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/scripts:/workspace/scripts:ro" \
  -v "$PWD/profiles:/workspace/profiles:ro" \
  -v "$PWD/docs/evaluation-entry-runbook.md:/workspace/docs/evaluation-entry-runbook.md:ro" \
  -v "$PWD/requirements-model.lock:/workspace/requirements-model.lock:ro" \
  -v "$PWD/runs/evaluation-entry-bundle/exports:/exports:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  scripts/evaluation_bundle.py build --target /exports/evaluation-entry-001
```

导出只读取固定允许文件，不遍历整个仓库；开发 policy/账本、凭据、vendor、数据、手册、测试及原始轨迹不进入包。目标已存在时拒绝且保留原文件；构建中断的目标保持占用，未完成标记会阻止验证。manifest 中的 hash 标识内容，不提供签名或执行许可。

进入导出的包目录后，可用基础镜像验证与查看只读计划：

```sh
cd runs/evaluation-entry-bundle/exports/evaluation-entry-001
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/package:ro" \
  -w /tmp chi-agent-dev:latest /opt/venv/bin/python \
  /package/scripts/evaluation_bundle.py verify --root /package
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD:/package:ro" \
  -w /tmp chi-agent-dev:latest /opt/venv/bin/python \
  /package/scripts/evaluation_entry.py plan
```

独立 SDK/vendor 只读挂载和多任务合成运行命令见包内 `RUN_EVALUATION.md`，源文件为 [运行说明](docs/evaluation-entry-runbook.md)。输出根须与包路径双向无重叠；同 evaluation 可继续另一合法 task/attempt，换 run-id 不能重演占用的 attempt。默认合成场景每 trial 估算超过 5 元，不会触发开发限额。包验证/完整演练退出 0，受控演练失败退出 1，输入或身份拒绝/live 退出 2；缺 SDK/vendor 时 `plan` 报告缺口仍退出 0，`preflight` 退出 1，完整依赖核对后 preflight 才退出 0。认证和执行许可始终分别报告。

## 资料来源

核对日期：2026-10-19。

- [官方仓库与安装说明](https://github.com/actava-ai/chi-bench)
- [官方单任务 Quickstart](https://www.actava.ai/benchmarks/docs/quickstart)
- [自定义 Agent 接入](https://github.com/actava-ai/chi-bench/blob/main/docs/extending.md)
- [OpenSpec 结构与场景格式](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)

依赖版本、任务 ID 和命令以实施时固定的上游提交及对应文档为准；不把示例模型名当作已经可用的配置。
