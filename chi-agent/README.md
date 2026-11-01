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
| 参赛路线与当前变更范围 | [参赛路线](openspec/competition-route.md)、[代表角色与开发患者模拟](openspec/changes/representative-role-baseline/proposal.md)、[历史 bootstrap-baseline](openspec/changes/bootstrap-baseline/proposal.md) |
| 验收契约与实现任务 | [Go CHI 接线设计](openspec/changes/chi-go-evaluation-entry/design.md)、[代表角色设计](openspec/changes/representative-role-baseline/design.md)与[任务](openspec/changes/representative-role-baseline/tasks.md)、[历史验收场景](openspec/changes/bootstrap-baseline/specs/benchmark-readiness/spec.md) |
| 近期五步离线开发与外部接手 | [payer证据核对计划](openspec/changes/payer-evidence-prototype/design.md)、[行为契约](openspec/changes/payer-evidence-prototype/specs/evidence-checkpoint/spec.md)、[任务清单](openspec/changes/payer-evidence-prototype/tasks.md) |
| 整个剩余项目的连续收尾 | [Z0–Z8执行设计](openspec/changes/project-completion/design.md)、[F0–F7能力建设](openspec/changes/project-completion/capabilities.md)、[完成契约](openspec/changes/project-completion/specs/project-closeout/spec.md)、[执行任务](openspec/changes/project-completion/tasks.md)；实际权限与状态仍查审核接续状态 |

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

空依赖卷安装、独立 SDK/vendor 挂载和多任务合成命令见包内 `RUN_EVALUATION.md`，源文件为 [运行说明](docs/evaluation-entry-runbook.md)。新增 `launch-rehearse` 接受官方 runner 形态的 `--instruction-file`、`--mcp-url`、`--logs-dir`，实际传入已有受控 runner，保留独立日志；该模式仍固定合成 HTTP/MCP/本地工具，URL 不触发联网。运行可用 `/usr/local/bin/python -S` 和新依赖卷，避免借用基础开发 venv 的包。

输出根须与包路径双向无重叠；日志目标必须新建并与包、输入和账目隔离。同 evaluation 可继续另一合法 task/attempt，换 run-id 不能重演占用的 attempt。默认合成场景每 trial 估算超过 5 元，不会触发开发限额。包验证/完整演练退出 0，受控演练失败退出 1，输入或身份拒绝/live 退出 2；缺 SDK/vendor 时 `plan` 报告缺口仍退出 0，`preflight` 退出 1，完整依赖核对后 preflight 才退出 0。认证和执行许可始终分别报告；实际官方服务/模型/C/判分与 F.5 完整正式冻结仍须后续验收。

## 真实开发入口与协作模型

开发实现默认一个 GPT-6.1 Terra（`gpt-6.1-terra`）/ `high` 子代理，主代理独立审核，见 [实现工作流](docs/subagent-workflow.md)。参赛运行时仍按 DeepSeek profile 配置；开发模型切换不更换参赛模型。

用户已授权多次本地 C 开发尝试并取消旧 5 元金额停止条件；K 策略独立为 real_development / record_only / null cap。运行前先核对 [REVIEW_STATE](reviews/REVIEW_STATE.md) 的验收与实际授权。参赛模型的基础 SDK 继续复用 H 的卷；PDF 读取使用独立的固定依赖，不改原 SDK 卷。

本节直连 DeepSeek 官方 API 的真实请求（含确认子请求和开发评审）须遵守[调用时段约定](../COLLABORATION.md#deepseek-api-调用时段2026-10-28)。启动前核对北京时间并为完整运行留足窗口；预计跨入禁用时段则延后。经 OpenCode 调用 DeepSeek 不受这条避峰限制，可全天安排已授权工作。依用户要求仅放在文档中，不添加程序时钟拦截。

从 `chi-agent/` 目录运行。首次在空 PDF 卷安装；已有通过核对的卷直接复用，安装也在 Docker 中：

```sh
docker volume create chi-k-pdf-deps-20261027-v1
docker run --rm --read-only --tmpfs /tmp \
  -e UV_CACHE_DIR=/tmp/uv-cache -e UV_LINK_MODE=copy \
  -v "$PWD/requirements-pdf.lock:/workspace/requirements-pdf.lock:ro" \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps \
  chi-agent-dev:latest uv pip install --target /pdf-deps --require-hashes \
    -r /workspace/requirements-pdf.lock

chi_live_control() {
  docker run --rm --read-only --tmpfs /tmp \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e A_PROJECT_ROOT=/workspace -e HOST_PROJECT_ROOT="$PWD" \
    -e DOCKER_HOST=unix:///var/run/docker.sock \
    -e PYTHONPATH=/pdf-deps:/model-deps:/workspace/vendor/chi-bench/src \
    -e CHI_MODEL_DEPS_VOLUME=chi-h-root-model-deps-20261027-v1 \
    -v "$PWD:/workspace:ro" -v "$PWD/runs:/workspace/runs:rw" \
    -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
    -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
    -v "${DOCKER_HOST_SOCKET:-/Users/asaki/.docker/run/docker.sock}:/var/run/docker.sock" \
    -w /workspace chi-agent-a-control:latest /opt/a-venv/bin/python \
    scripts/live_development.py "$@"
}
```

controller 需要访问本地 `.env` 和 Docker socket；模型在独立 runner 中，文件工具不可读取凭据/socket/源码/账目。以下命令不是干运行，B/C 会调用真实模型：

```sh
# 仅首次接续：验证旧 known 账目、B 回执与失败 claim，保留原文件
chi_live_control adopt-prior
# 显式记录新源码身份，保留费用；代码变更后也使用此命令
chi_live_control rebind-source --reason 'reviewed implementation for continued C development'
# 每个新源码身份先取得自己的 B 工具闭环证据
chi_live_control k-b-smoke --run-id k-b-example-001
chi_live_control c-run --run-id m-c-example-001 \
  --task-id pa_t013_t013_o002_p01_new_referral_provider
# 上次终态和资源清理符合要求后，可在新世界再次自主尝试
chi_live_control c-run --run-id m-c-example-002 \
  --task-id pa_t019_t019_o001_p01_new_referral_provider
```

K 状态固定在 `runs/real-c-development/`：`adoption.json` 保存旧来源，source-transitions 保存源码变更，accounting 累计旧费用与新增费用；claims 与各 run 产物分别保留。源码改变后先 rebind，再做当前源码 B；同一 attempt 不重演，不删除状态重新初始化。pending/未知用量、资源清理或持久化不明时先处理证据，金额上限取消不等于抹掉未知。旧 `plan`/`preflight` 及下方命令继续表示 J 的 5 元历史入口，不能拿它们当作 K 的预检。

`c-run` 现在必须显式提供本轮冻结清单内的 `--task-id`，不再隐式采用旧题。资源定义见 `scripts/provider_task_resources.py`，运行前校验固定版本、文件哈希与普通文件/无链接路径。B 绑定当前源码，可以作为两题的共同前置；每个 C 仍创建自己的新世界和 claim，账目保持累计。任务清单和实验边界见 [M 规格](openspec/changes/provider-two-task-baseline/design.md)，实际结果只查 [M 报告](reviews/provider-two-task-baseline-review.md)。

已有有效资源直接复用。首次仅获取冻结两题必要文件时，在 `chi-agent/` 运行以下 Docker 命令；固定旧 world 镜像和已授权 handbook 仍是前置，不需要重建镜像：

```sh
docker run --rm -i --read-only --tmpfs /tmp \
  -v "$PWD/scripts:/workspace/scripts:ro" -v "$PWD/data:/workspace/data:rw" \
  -w /workspace chi-agent-a-control:latest /opt/a-venv/bin/python - <<'PY'
import hashlib, json, pathlib, sys
sys.path.insert(0, "/workspace/scripts")
import provider_task_resources as resources
from huggingface_hub import hf_hub_download
root = pathlib.Path("/workspace")
target = root / "data/provider-baseline" / resources.REVISION
manifest = target / "resource-manifest.json"
if manifest.exists():
    for task in resources.TASK_FILES:
        resources.verify(root, task)
    raise SystemExit("Existing resources verified")
files = {}
paths = ["task_index.md"] + [f"prior_auth_provider/tasks/{task}/{name}"
    for task, names in resources.TASK_FILES.items() for name in names]
for relative in paths:
    path = pathlib.Path(hf_hub_download("actava/chi-bench", relative,
        repo_type="dataset", revision=resources.REVISION, local_dir=str(target)))
    raw = path.read_bytes()
    files[relative] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
manifest.write_text(json.dumps({"schema": "chi-provider-baseline-resources-v1",
    "dataset": "actava/chi-bench", "revision": resources.REVISION,
    "tasks": list(resources.TASK_FILES), "files": files}, indent=2) + "\n")
for task in resources.TASK_FILES:
    resources.verify(root, task)
print("Pinned task resources verified")
PY
```

只有选定 task 目录只读挂给 world，participant 仍只接收公开输入、工具说明和既有授权材料。不要在真实运行中人工选择业务动作；观察到结果问题后保留本次尝试，再单独制定通用改进。

已允许路径内的 UTF-8 文本和 PDF 可通过 `local-fs-read` 读取；PDF 是文本提取，不提供 OCR。PDF 上限为 8 MiB、100 页、累计提取 100 万字符、单次返回 10 万字符；可用原有 offset/limit 按行分段。损坏、加密或不支持的二进制返回明确工具错误。解析器版本、锁和包源码纳入 K 身份，缺依赖或不一致会停止；这不扩大 handbook/task/case provider/shared 的路径权限。

### 自主 C 的请求次数与收尾提示

K 的 `c-run` 使用来源受控的执行契约：SDK 主循环最多 50 轮，主模型和患者确认子请求合计最多 **50 次 provider 请求**。`scripts/request_budget.py` 固定该入口的有效限制；原 provider profile 中的 30 保留为其他入口的默认值及旧账身份，不代表 K C 仍只可用 30。K B smoke 仍为原 6 次限制，历史 J 与正式入口保持原行为。

每次业务模型请求前，适配层临时在系统说明中附加最新共享计数：发送前已用、本次序号、包含本次的剩余次数、本次之后剩余次数。信息包含已发生的确认请求，不需要 Agent 额外查询，也不累积旧提示或改变原始病例/工具结果；确认子请求不混入该系统提示。guard 在发送前独立核对状态，伪造、陈旧或额外系统消息会被拒绝。

反馈解释现有收尾成本：尚未声明完成时，从当前响应选择完成工具到最终回复至少两次请求（包含本次）；完成声明已返回后，当前请求可生成最终回复。剩余次数较少时给软提醒，不硬扣业务轮数、不改变完成工具终止语义。50 是上限，符合公开任务要求就应及时结束；未完成时应如实说明，正常退出也不自动证明业务成功。每个主请求的反馈身份/计数及实际 provider round 保存于 run journal，源码变化仍需 rebind 和新 B。

这是增加请求空间与运行时提示的组合改动；实验边界见 [O 规格](openspec/changes/request-budget-awareness/design.md)，实际结果见 [O 报告](reviews/request-budget-awareness-review.md)。

### 自主 C 的申请字段提示

K C 在现有建案与提交工具的原 description 后，追加通用公开字段依据提示：分别核对服务类别和照护地点，机构名称本身不决定地点/级别；提交前把 request、form 和 evidence package 与原始公开材料核对。无需新参数、额外工具或确认模型，仍由 Agent 选择业务动作；这不是程序对字段语义的硬校验。

`scripts/referral_field_guidance.py` 保存版本与文本。run journal 的 `referral_field_guidance` 记录整体指导及各工具原/后 description 的 hash；新模块进入 K 源码身份，沿用原 rebind/新 B 前置。仅 K C 追加，B/J/正式入口及无关工具保持原行为。实验和实际验证边界见 [P 报告](reviews/referral-field-guidance-review.md)；哪些任务安排付费验证只查 [审核状态](reviews/REVIEW_STATE.md)。

### 自主 C 的患者确认与写入门禁

K 的 `c-run` 默认启用患者确认；启动命令不变，操作员无需在运行中手动绑定或代选患者。Agent 先通过公开 MCP 查完整未过滤 roster，再查看待选者及同 sex、DOB 年差不超过 1 的近邻病例；默认一页或按某患者过滤的查询不能证明已覆盖候选。缺少完整可见病例时，工具返回需补查的 ID，保持只读。

`local-read-patient-observation` 只按 patient_id/offset 有界回读已经成功查询的 chart，无法读取任意路径；可用于补齐官方截断返回的内容。`local-confirm-patient` 必须单独调用，带来自公开 instruction 和所选 chart 的真实原文引文。它使用同一 DeepSeek client/GuardedTransport 做一次无工具匹配检查，核对完整候选集合、唯一性和引用，最多两次；不确定、矛盾或缺材料不绑定。

确认请求与主循环共用原来的累计账目及上述 **50 次总 provider 请求**上限和零重试；主业务单次输出仍为 8192，只有源代码构造的 K C 无工具确认请求使用 32768，最多两次。角色和限额不能由 Agent 参数或 HTTP 字段指定；它占用原有请求空间，费用按对应上限预留并结算。协议/材料 hash、provider round、finish_reason、内容是否存在及拒绝/绑定事件保存于该 run journal。已知用量的截断/格式失败明确拒绝且保持未绑定，不在工具内重试；取消仍停止，导致未知用量时保留已有 pending，已结算用量不倒退成未知。源码变更仍须 rebind 和新 B，旧费用/claim 不清零。

确认后，每次 MCP 业务副作用和 workspace 写/edit 都核对患者及已观察的 order/case/form/document 等归属。未绑定、跨患者、猜测 ID、未知工具或身份冲突明确拒绝；不静默切换患者，未证明 line_updates 归属时拒绝。患者源文档与病例文档分别跟踪，共用 form 模板按 case 配对。

语义确认仍来自同 provider，存在模型偏差；来源/身份检查不能证明医学语义正确。完整 world 的非目标患者业务写入、正常结束和目标结果须结合检查，不能只看局部 rubric。设计与实验边界见 [N 规格](openspec/changes/provider-patient-binding/design.md)，实际候选、失败和回归结果见 [N 报告](reviews/provider-patient-binding-review.md)。正式配送入口与 F.5 不在本轮迁移范围。

## OpenCode Go 的 V4.1 Flash 接入

`.env` 本地新增 `OPENCODE_API_KEY`，保留原 `DEEPSEEK_API_KEY`，不要把 Key 放入命令正文或 Git。Go 使用正式 ID `deepseek-v4.1-flash` 和 `/inference/go/openai/v1/chat/completions`；SDK base URL 为 `https://opencode.ai/inference/go/openai/v1`，不能套用 native 的 URL 或 pay-as-you-go 路径。

`scripts/opencode_go_provider.py` 提供独立的 Go 适配与固定 coding 工具探针；下方新 CHI 包复用其提供方接点。该探针 CLI 不接受患者、任务指令、MCP 或任意 prompt，不能替代 `c-run` 或开发评审。Go 的非编码 CHI 用途支持仍待确认。**OpenCode 请求不受 DeepSeek 官方 API 的避峰时段限制，可全天执行已授权工作**；运行前仍核对控制台 Extra Usage 关闭和用量状态，不因等待官方 API 折扣时段而延后。

以下从项目目录运行，复用已有镜像和 SDK 卷，不安装依赖。`plan` / `preflight` 只读，`offline` 用临时账目与模拟 HTTP，均不需要 Key：

```sh
mkdir -p runs/opencode-go-development
go_offline() {
  docker run --rm --network none --read-only --tmpfs /tmp \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONPATH=/workspace/scripts:/model-deps \
    -v "$PWD/scripts:/workspace/scripts:ro" \
    -v "$PWD/profiles:/workspace/profiles:ro" \
    -v "$PWD/requirements-model.lock:/workspace/requirements-model.lock:ro" \
    -v "$PWD/runs/opencode-go-development:/workspace/runs/opencode-go-development:ro" \
    -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
    -w /workspace chi-agent-dev:latest \
    /opt/venv/bin/python scripts/opencode_go_provider.py "$@"
}
go_offline plan
go_offline preflight
go_offline offline
```

真实入口为 `smoke --run-id <新的唯一ID>`。须从已审核源码执行，单独挂载 `runs/opencode-go-development/` 为可写；仅向该容器注入 `OPENCODE_API_KEY`，使用外网但不挂任务资源、`.env`、手册、Docker socket 或旧运行目录。不要在生产账本上运行 `offline` 合成调用。实际受审命令与结果见[Go 审核报告](reviews/opencode-go-provider-review.md)。

需要真实探针时，可在禁网容器从现有 `.env` 生成仅含 Go Key 的临时 0600 文件；下面的外网容器不会接收其他凭据。先核对当前授权，不重复执行已用过的 run-id：

```sh
(
  set -eu
  go_probe_auth_dir="$(mktemp -d)"
  trap 'rm -f "$go_probe_auth_dir/go.env"; rmdir "$go_probe_auth_dir"' EXIT
  docker run --rm --network none --read-only --tmpfs /tmp --env-file .env \
    -v "$go_probe_auth_dir:/auth:rw" chi-agent-dev:latest /opt/venv/bin/python -c '
import os
key = os.environ["OPENCODE_API_KEY"]
assert key.strip() and "\n" not in key and "\r" not in key
fd = os.open("/auth/go.env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as out:
    out.write("OPENCODE_API_KEY=" + key + "\n")
'
  docker run --rm --read-only --tmpfs /tmp --env-file "$go_probe_auth_dir/go.env" \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/scripts:/model-deps \
    -v "$PWD/scripts:/workspace/scripts:ro" -v "$PWD/profiles:/workspace/profiles:ro" \
    -v "$PWD/requirements-model.lock:/workspace/requirements-model.lock:ro" \
    -v "$PWD/runs/opencode-go-development:/workspace/runs/opencode-go-development:rw" \
    -v chi-h-root-model-deps-20261027-v1:/model-deps:ro -w /workspace \
    chi-agent-dev:latest /opt/venv/bin/python scripts/opencode_go_provider.py \
    smoke --run-id go-coding-new-001
)
```

源码变化后先离线审核，再以禁网容器、相同源码/依赖、Go 账本可写挂载，显式执行 `rebind-source --reason '<变更原因>'`。此命令不读 Key、不发 API，要求 profile/SDK 不变、旧用量/费用完整、无 pending/halt 和历史审计通过；归档旧 accounting 原字节，登记转换后继续原累计。`.rebind-pending` 或不完整转换会阻断，不得删除标记、归档或原根目录绕过。

新账本分别累计 Go 返回的余额扣费、模型价目价值和套餐消耗，单位均为 USD；原 CNY 账目不迁移、不相加。订阅月费另计。未知用量保留 pending 并阻止后续请求，重复 ID 不覆盖，账单来源异常先结算已知费用再停止；不能删除账本清零或自动回退到余额/native。

模型标称 1M 上下文由 [OpenCode 模型信息](https://opencode.ai/data/deepseek/deepseek-v4-1-flash)及 [DeepSeek 规格](https://api-docs.deepseek.com/quick_start/pricing/)支持，本探针没有百万 token 实测。`deepseek-flash[1m]` 来自 [Claude Code 专用接入示例](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)，不追加到 Go 的正式模型 ID；单次输出上限与上下文容量分开设置。

## F0–F3 开发能力：状态、角色指导与有界检索

`run_chi()` 默认启用 `capabilities="f0-f3-v1"`，`go_chi_entry.py` 也显式传入。它不改变官方 `SYSTEM_PROMPT`、工具批次校验、预算反馈、零重试或账目 schema，只增加四个本地工具：

| 工具 | 作用 | 主要边界 |
| --- | --- | --- |
| `local-task-state` | 读取本次 run 的目标、事实/计划/缺口、未知写、最新业务状态和下一步候选 | 只读摘要，不含原始工具正文 |
| `local-state-update` | 模型提交带来源的更新 | 事实/状态必须引用已登记 call_id；拒绝旧来源、错 case、改绑患者、把 unknown 改成成功/失败 |
| `local-role-guidance` | 返回 `chi-role-guidance-v1` 阶段/分支/停止条件 | 不含 task ID、期望结局或隐藏答案 |
| `local-fs-search` | 在已授权目录/固定文件中做有界文本检索 | 不建索引、不跟随符号链接；文件/字节/结果/片段均有限制 |

状态写入 `logs/task-state/`（`task-state.json` 与 `versions/`），不写 `chi-accounting.json`。`local-claim_done` 在启用时额外检查：open unknown、写后未回读、同批后续工具；被拒绝时返回具体原因，模型可在剩余预算内查证后重试。claim 之后再尝试写会被拒绝并标记 `claim_violation`，该 run 以 `chi_claim_violation` 结束为 incomplete；journal 的 claim 记录保持单调，不回写历史。`local-fs-search` 在 workspace 内只允许当前 target case；单个文件/PDF 不可读返回 `ERROR: search_unreadable`，不伪装成无匹配。`capabilities=None` 保留旧工具集和旧 claim 行为，仅用于离线基线/对照，不作为真实运行绕过开关。

这只验证合成 SDK/MCP 边界；真实模型是否使用这些工具、真实任务收益、官方评分和正式配送仍未验证。契约见 [F0–F3 设计](openspec/changes/agent-capabilities-f0-f3/design.md)，实际候选/限制见 [阶段报告](reviews/f0-f3-agent-capabilities-review.md)。

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

## F4–F6 上下文预算、完成核验与失败处理

`run_chi()` 默认启用 `context_budget=DEFAULT_BUDGET`（`chi-context-budget-v1`）：3.5M 字符、1M 估计 token、8192 输出预留，来源标 `configured_unverified`。每次通过 contract 的请求在 `journal.reserve()` 前测量 system/instruction/tools/history/tool_result/reasoning，写入 `logs/context.jsonl`（只含计数，不含正文）；超限在发送前返回 `chi_context_budget_exceeded`。`run_log.txt` 另记 `context_requests`、最大字符/估计 token 和已结算输入 token。自动历史压缩**未采用**：当前完整批次校验要求未满足新 contract/真实协议证据，不能靠删消息绕过。

完成核验通过 `local-completion-check` 返回 `chi-completion-v1`，区分 `mechanical_pass/not_applicable/blocked` 与 `observed/not_observed/not_verified/unknown/violation`，并写入 run_log 的 `completion`；它不替代 claim，也不是临床或官方 verdict。

F6 对 MCP mutation 的 dispatch 异常返回 `UNKNOWN_WRITE_EFFECT: <code>`，登记 open unknown；未知期间拒绝所有写，只能用同目标更晚只读观察 resolve；未解决结束为 `chi_unknown_write_effect` incomplete。重复读第 3 次追加 `STAGNATION`、第 5 次拒绝；重复写第 2 次拒绝；不自动重试或换模型。本地文件写异常仍按原逻辑失败。

这些能力仍只在合成 SDK/MCP 边界验证；真实 tokenizer、真实超时副作用、真实模型行为和官方评分未验证。设计与证据见 [F4–F6 契约](openspec/changes/agent-capabilities-f4-f6/design.md) 和 [阶段报告](reviews/f4-f6-context-completion-review.md)。

## F7 实验清单与全分母汇总

`scripts/experiment_manifest.py` 与 `scripts/experiment_summary.py` 独立于被测 Agent，先冻结实验条件，再汇总记录。

```bash
# 校验/冻结 manifest；输出规范 JSON 与 SHA-256
docker run --rm --network none -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/workspace/scripts -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python scripts/experiment_manifest.py validate --manifest campaign.json
docker run --rm --network none -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/workspace/scripts -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python scripts/experiment_manifest.py freeze --manifest campaign.json

# 汇总 records（JSON 数组或 .jsonl）
docker run --rm --network none -v "$PWD:/workspace:ro" \
  -e PYTHONPATH=/workspace/scripts -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python scripts/experiment_summary.py summarize \
  --manifest campaign.json --records records.json
```

manifest 固定 candidate（source/bundle/model/endpoint/simulator/capabilities）、F1–F6 机制的 off/on 或 `na`、任务/角色/attempt、资源 hash、世界镜像、检查项、请求/输出上限和停止条件。off/on 两臂必须同任务集合与 limits；不可独立切换的机制用 `na`+reason。汇总只给全分母计数：completed/failed/skipped/blocked/not_run/missing_evidence、checks pass/fail/na/not_run、business/content、usage known/missing、official present/absent；不输出 success rate、不补 0、不合成官方分数，也不计算某项机制的因果收益。

当前只有合成记录测试（15 个）；真实 Z4/Z5 运行仍需用户批准任务/次数/资源。设计见 [F7 契约](openspec/changes/experiment-harness/design.md)，证据见 [阶段报告](reviews/experiment-harness-review.md)。

## Go CHI 独立包入口

`scripts/go_chi_entry.py` 接收外部 instruction、一个角色 MCP、日志目录和 evaluation/task/attempt/run 身份；它只在经过 manifest 校验的导出包内运行。原 `opencode_go_provider.py` 继续是固定 coding 探针，原 `evaluation_entry.py` 的 live 拒绝保持。实际已验证范围、固定候选和限制只查 [审核状态](reviews/REVIEW_STATE.md)。

从本项目目录导出一个新包，目标必须尚不存在；此步骤禁网且不读 Key：

```sh
mkdir -p runs/go-chi-exports
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD:/source:ro" -v "$PWD/runs/go-chi-exports:/exports:rw" \
  -w /tmp chi-agent-dev:latest /opt/venv/bin/python \
  /source/scripts/go_chi_bundle.py build --target /exports/go-chi-001
```

构建输出的 manifest SHA 通过 `--bundle-sha256` 显式传入新入口；`preflight` 只读核对包、配置、固定上游、SDK 和 PDF 依赖，`coding-b` 取得当前身份的 B 收据，`live` 再运行外部任务。包外提供固定官方 checkout、锁定依赖、授权资源、凭据和可写状态/日志；完整挂载及启动命令见 [Go 包 runbook](docs/go-chi-entry-runbook.md)，导出后为 `RUN_CHI_GO.md`。程序包不含 vendor、任务、手册、凭据或开发轨迹。

新 CHI 任务沿用主请求/患者确认合计 50 次、主输出 8192、确认最多两次/32768 及每次主请求的可信剩余反馈；B 另为 6 次/1024，不把探针配置当正式任务配置。provider 使用患者和实体绑定门禁及通用字段提示；payer/CM 只使用所选角色工具与角色/shared 文件范围，不能把协议演练写成三赛道业务通过。

固定时间策略随包验证：普通/B请求 HTTP read60秒、确认read360秒，单请求I/O总时限分别120/420秒；connect10、write/pool60秒。新请求准入窗口为B180秒、C900秒，窗口内发出的请求可有界完成；调度配置的runner等待必须为B360–3600秒、C1380–3600秒。时间按进程单调时钟计算，与提供方避峰的日历规则无关。

本地继续开发使用 `--history-mode local --local-q-root /prior-go --output-root /prior-go/chi-evaluation`，审计并持锁既有 Go 历史，新的 CHI 状态固定在子目录。外部独立 evaluation 使用显式 `external` 模式；这不代表账户此前消费为零。record_only/null cap、三项 USD 分列和零自动重试保持；旧 CNY 不与 USD 相加。新 CHI attempt 固定 `fee_policy=go-chi-record-incomplete-fees-v1`：可信 tokens 齐全而费用缺项时，保留 null、完整性标记及 warning，继续运行；异常数据、明确非 Go 来源或余额实扣仍停止。旧 Q/native 及旧 attempt 按原契约审计，不改写为新策略。

源码变更后先离线审核、导出新包，再使用包内 `audit-history` / `rebind-history` 明确传入旧身份与旧主账 SHA-256；旧账原字节归档，旧 attempt/失败/费用/证据/收据保留，必须为新候选取得自己的 B。中断标记、证据缺件或新的结果/token 未知仍阻断，不能另建账根绕过。精确命令见 runbook。

遇到未结算历史，使用包内 `inspect-history` 并传同样的历史模式、路径、预期旧identity/主账SHA；它完整核验合法pending/halt并报告缺件，不读Key。可加 `--provider-record /provider-source/request.json --provider-record-sha256 <SHA>` 检查官方Console单请求导出，文件只读挂到操作者容器；精确命令见runbook。exit=0只代表检查完成，输出不会授予运行权限。Console `cost` 单独显示；它不能代替响应中的三项USD、补写旧关联信息或清除占位。新请求的dispatch只存会话hash、时间和原文长度，不保存会话原值。

对用户单独批准留档继续的 legacy 终止超时，操作者可使用 `acknowledge-unsettled`，精确传入原 identity/主账 hash、run/round/request hash、提供方原文件/hash 和处置原因。事务保留原账原字节、旁证和事件 hash；原失败请求仍未结算，只有该事件的全局准入阻断解除。重复处置、篡改、事务中断或新请求未知仍拒绝。此入口不自动确认其他未知请求，不恢复原业务结果；使用前须有明确授权及新的有界试次计划。

开发调度使用包外 `scripts/go_chi_operator.py --config <受审JSON> --config-sha256 <SHA-256>`，在已有 controller 镜像和 SDK/PDF 卷内执行，一次只运行一个指定 B/C。固定配置绑定独立包、运行身份、镜像与任务资源；创建世界和读取 Key 前执行无凭据预检。C 在 runner 前后保留完整业务资源快照，并在 runner 静止、世界清理前捕获权威终态，运行不调用模型的部分确定性检查；主错误、捕获错误和清理错误分别保存。控制器及其捕获材料不放进参赛包，具体调用数和任务清单以当轮 OpenSpec/审核授权为准。

调度产物中，`orchestration.json` 保存退出、捕获/清理及操作者耗时，`runner-logs/result/` 保存参赛日志，`initial-capture/`、`capture/` 和 `resource-snapshots/` 是操作者证据，不挂给参赛 runner。`run_result.json` 的 `usage` 是当前 CHI 账累计；单次用量应按 `chi-accounting.json` 中对应 run 的 `requests` 汇总，旧 Q coding 账另行累计。余额实扣、价目价值、套餐消耗是三种不同 USD 口径，不能相加，也不能根据界面整数百分比推断请求数或精确余量。

用户已知悉 Go 非编码用途尚未获得官方确认并决定继续使用，十一月隐私条件仍需运行前人工复核；不伪装请求，不增加时钟门禁。完整 Harbor 配送与 F.5、原版 Claude 判分分别按审核状态管理。

### 真实 Harbor 组件的合成启动预演

从项目目录执行以下预演。它使用真实Harbor类型/工厂/SingleStepTrial、固定官方Docker环境和真实角色MCP；仅模型HTTP与两条故障注入为测试专用。控制侧最小组件overlay固定于 `requirements-harbor.lock`，复用原SDK/PDF，不是安装完整Harbor可选服务/CLI栈。当前复现范围为Python3.12/Linux arm64；依赖与Docker客户端身份见[规格](openspec/changes/harbor-launch-coverage/design.md#harbor-最小新增与隔离复现)。

先在新的目录安装本轮控制侧overlay，再准备本地测试镜像和自然生成的合成B。下面的shell仅调度Docker；包导出、资源复制、安装、模型/工具循环都在Docker内。目录与ID每次换新，原运行不覆盖。

```sh
harbor_probe_root="$PWD/runs/harbor-launch-coverage-root/replay-001"
harbor_docker_socket="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
harbor_docker_socket="${harbor_docker_socket#unix://}"
mkdir -p "$harbor_probe_root"
docker run --rm --pull=never \
  -v "$PWD/requirements-harbor.lock:/requirements.lock:ro" \
  -v "$harbor_probe_root:/out" chi-agent-py312-review:dev \
  /usr/local/bin/python -m pip install --no-deps --require-hashes \
  --target /out/overlay -r /requirements.lock
sh tests/harbor_rehearsal_prepare.sh "$harbor_probe_root/prepared" replay-001
```

官方Docker环境需要Linux docker客户端。在Docker内取得规格固定的官方归档并核对SHA256，仅解出客户端；可复用已经核对的本轮CLI，不必重复下载。

```sh
docker run --rm --pull=never -v "$harbor_probe_root:/out" \
  chi-agent-py312-review:dev sh -c '
  curl -fsSL https://download.docker.com/linux/static/stable/aarch64/docker-28.5.2.tgz -o /out/docker-cli.tgz &&
  echo "9e4f82996ab790724094475ebed33a736434bfe5d45231b676fef22ffb80044d  /out/docker-cli.tgz" | sha256sum -c - &&
  mkdir /out/cli && tar -xzf /out/docker-cli.tgz -C /out/cli docker/docker'
```

三个场景串行执行：正常只读闭环、非零退出、损坏trace。无需`.env`或真实Key，脚本只用测试专用合成值；verifier禁用，无真实模型或业务任务。含原受限资源的测试镜像仅留本地，不上传。

```sh
for harbor_scenario in success runner-nonzero corrupt-trace; do
  docker run --rm --pull=never --network none \
    -v "$harbor_docker_socket:/var/run/docker.sock" \
    -v "$harbor_probe_root/cli/docker/docker:/usr/local/bin/docker:ro" \
    -v "$harbor_probe_root/prepared/build/bundle:/bundle:ro" \
    -v "$harbor_probe_root/overlay:/overlay:ro" -v "$harbor_probe_root:/out" \
    -v "$PWD/vendor/chi-bench/src:/vendor:ro" \
    -v "$PWD/tests/harbor_trial_rehearsal.py:/trial.py:ro" \
    -v "$PWD/tests/harbor_mcp_probe.py:/mcp_probe.py:ro" \
    -v chi-h-root-model-deps-20261027-v1:/deps:ro \
    -e PYTHONPATH=/bundle/scripts:/vendor:/overlay:/deps \
    -e PYTHONDONTWRITEBYTECODE=1 chi-agent-py312-review:dev python /trial.py \
    --out "/out/trial-$harbor_scenario" --bundle /bundle \
    --image chi-agent-harbor-synthetic:replay-001-seed --scenario "$harbor_scenario"
done
```

`trial-*/trials/`保存原Harbor配置/结果/异常/下载日志，`state/`为删除世界前采集的独立合成账与wire/seal，MCP与公开参考供应证据在各场景目录；测试生成的USD/tokens仅为合成数据，不能并入真实历史。预演使用调用方hooks供应普通公开参考并采证，不更改官方评分器，也不声称stock入口自动选择本适配器。现有三题评分覆盖与实际通过边界见[唯一U报告](reviews/harbor-launch-coverage-review.md)；后续真实调用仍先固定有界规格/身份并满足自己的B门禁。

### 三角色资源与无模型世界预检

包外入口 `scripts/role_world_preflight.py` 接受固定配置和SHA256，先用 `role_resource_preflight.validate()` 核对资源，再启动一个无Key、无外网的新世界；只调用所选角色的一次只读MCP，并在清理前保存初末导出和provider/payer完整resources。初始化状态的纯检查不是任务分数。范围及准备资源的固定版本见[V设计](openspec/changes/representative-role-baseline/design.md)，实际验收见[审核状态](reviews/REVIEW_STATE.md)。

| family | task actor → runtime role | MCP端口 |
| --- | --- | --- |
| prior_auth_provider | provider → provider | 8020 |
| prior_auth_um | payer → payer | 8100 |
| care_management | care_manager → cm | 8200 |

资源manifest采用`chi-role-resources-v1`：绑定revision/task/family/actor/role、相对dataset的task/instruction/tool-reference路径、world来源/path/hash，以及每个文件的path/size/hash/public或world_only可见性。当前有界验证器只接受规格中的必要文件闭包和payer的4份公开PDF；其他题的文件条件需先扩展规格，不能随意增加judge/solution/tests。CM显式使用所声明的共享world/ref，PA绑定双world。原始fixtures只给世界，payer公开PDF由官方初始化复制到自己的incoming_request工作目录。

预检配置为`chi-role-world-preflight-v1`，字段是`schema`、新`run_id`、`dataset_relative`、`manifest_relative`、`manifest_sha256`、`output_relative`、`world_image_id`。路径相对项目根；输出父目录须存在，已有输出或资源身份拒绝。准备好已授权数据与固定镜像后，从本项目目录运行，替换受审配置路径和hash：

```bash
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -v "$PWD:/workspace:ro" -v "$PWD/runs:/workspace/runs:rw" \
  -v "${DOCKER_HOST_SOCKET:-/Users/asaki/.docker/run/docker.sock}:/var/run/docker.sock" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e HOST_PROJECT_ROOT="$PWD" -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src \
  --entrypoint /opt/a-venv/bin/python chi-agent-py312-review:controller \
  /workspace/scripts/role_world_preflight.py \
  --config /workspace/runs/<受审配置>.json --config-sha256 <配置SHA256>
```

产物含`result.json`、`mcp-response.json`、`world-container.log`、`world-artifacts/`、初末capture和`resource-snapshots/`；保留失败编号，不覆盖重跑。CM走独立来源捕获，原始export没有world_id，身份从实际挂载的fixture manifest与world文件核验；不向原导出补字段或改变PA契约。none网络保留localhost供原entrypoint健康检查，不能换成旧式network_disabled参数。

### 本地Go患者模拟与官方默认

本地开发模拟与内容评审是两个入口；启用患者模拟不恢复下节临床评审。官方world仍默认Anthropic，参赛bundle不含`dev_patient_*`、资源预检和操作者；通用`run_chi()`的auxiliary参数默认关闭，正式CLI和存在Go Key都不会自动启用开发模拟器。

开发接点由两端组成：计费所有者构造`PatientBroker`，与已审`ChiJournal`及主guard共享billing锁，启动能力token保护的内部HTTP服务，再显式调用`run_chi(..., auxiliary=broker)`；CHI launch须声明`role=cm`、`aux_contract=patient-simulator-v1`及现行fee_policy，并满足原历史审计/当前B。世界只接收本轮能力文件、run ID和内部broker地址，不接收Go/Anthropic Key，也不接外网。原`go_chi_operator.py`保持provider兼容；统一三角色编排使用下节包外入口，其实际验收/真实运行范围先查[审核状态](reviews/REVIEW_STATE.md)。

在独立开发world中，将可执行的`scripts/dev_patient_cb`只读bind到`/workspace/.venv/bin/cb`，将bootstrap/adapter所在目录只读挂载并加入该world的PYTHONPATH，显式提供以下环境项；镜像及官方默认启动文件不改：

```text
CHI_DEV_PATIENT_SIMULATOR=go-v1
CHI_DEV_CAPABILITY_FILE=/run/chi-dev/capability
CHI_DEV_RUN_ID=<本轮唯一ID>
CHI_DEV_BROKER_URL=http://<内部计费所有者>:<端口>/patient
```

能力文件须为本轮普通只读文件、32–128个字符的字母数字/下划线/连字符token，且不在Agent可读workspace内。原entrypoint激活venv会重新前置venv/bin，所以单纯前置PATH不能保证使用开发cb。wrapper只接受原serve命令形状，在同一进程安装适配类后启动原CLI；没有显式开发挂载时仍是官方Anthropic路径。完整跨容器CM业务按[W规格](openspec/changes/unified-role-cm-lifecycle/design.md)的操作者、生命周期与固定清单执行，不能把自造患者probe当成该业务试次。

独立自造患者探针使用包外`scripts/dev_patient_probe.py --config /input/config.json --config-sha256 <SHA256>`。它会调用真实Go；先查审核状态，不因这里列命令自动授权重跑。运行容器需有只读`/package`及固定vendor/原SDK/PDF、只读开发probe/adapter、原账`/prior-go`和新的可写`/probe-logs`，只安全注入OPENCODE_API_KEY，不挂整个.env或其他Key。配置schema为`chi-synthetic-patient-probe-v1`，字段为`schema`、`bundle`、`bundle_sha256`、`runtime_identity`、`q_root`、`run`、`evaluation`、`attempt`、`output`、`probe_sha256`、`adapter_sha256`；典型路径分别为`/package`、`/prior-go`、`/probe-logs/result`，身份/hash由受审导出和实际源码计算。

probe固定自造预约persona及两句问题，最多2响应，STOP即结束；不加载基准患者或评分材料。`result.json`保存观察到的会话，`completion.json`只在账目封存后出现，失败用`failure.json`，所有wire/usage/seal在原CHI账中追加。患者辅助请求单列purpose/费用，主+确认共享50/确认2不变；预算及超时只见V规格。模型更换会改变患者行为，探针完成、CM业务结束、临床评价与官方reward分别判断。

### 统一角色开发操作者

包外 `scripts/role_operator.py --config <JSON> --config-sha256 <SHA256>` 一次只运行一题。先核对[W规格](openspec/changes/unified-role-cm-lifecycle/design.md)及[审核状态](reviews/REVIEW_STATE.md)的授权、固定候选/当前B/历史与实际日期隐私条件；命令存在不授权重复真实试验。沿用controller、固定world/dev镜像和原SDK/PDF卷，安装/调试/执行都在Docker。

配置schema为 `chi-role-operator-v1`，明确 `run_id/evaluation_id/task_id/attempt_id/role`、`bundle_relative/bundle_sha256/runtime_identity`、`runner_image_id/world_image_id`、`dataset_relative/manifest_relative/manifest_sha256`、`output_relative`、`dev_sha256`、`operator_timeout_seconds`。路径相对controller的 `/workspace`，由 `HOST_PROJECT_ROOT` 映射到Docker引擎宿主项目。`dev_sha256`绑定 `role_runner.py`、`dev_patient_broker.py`、`dev_patient_cb`、`dev_patient_bootstrap.py`、`dev_patient_adapter.py`；期限固定2040秒。配置与路径/hash/角色矛盾在世界及凭据前拒绝，输出和run身份须为新的唯一值。

操作者只把选定的OPENCODE_API_KEY注入runner。controller若需从本地.env读取凭据，使用受审包装器只读取该项；不得把整个.env挂给runner或world。runner通过包外 `role_runner.py` 显式调用原 `go_chi_entry.main(development=...)`，原包身份、公开输入、Q→CHI锁、历史/B门禁及封存继续执行。原CLI没有开发开关，官方Anthropic默认、评分器和 `evaluation_entry` live拒绝保留；包清单排除操作者、患者适配器和测试shim。

world仅连接本轮internal网络；CM能力文件只读提供给world/runner，结束后删除并只留hash。runner的broker仅监听内部接口，与Agent共用单账和billing锁。等待策略及请求上限见W规格；MCP与本地工具在共享派发锁内检查fatal，患者故障后同批后续动作也停止。模型HTTP结束不等于世界工具结束；包外跟踪器只在所有工具完整返回、无未知在途且broker已收束时允许权威终态捕获，模型失败后仍可保留已确认静止的终态。断开/超时后服务端状态不确定则明确记录capture_error，不能用等待时长冒充已静止。

输出含 `orchestration.json`、runner/world容器日志、`runner-logs/lifecycle.json` 与原SDK结果/轨迹、`world-artifacts/`、初末capture及两侧完整 `resource-snapshots/`。CM保留原导出与实际初始化来源；payer先核对四份公开PDF投影。主错、捕获错、清理错分别保存，精确容器/网络ID删除后再次核验。程序检查显式关闭semantic judge，结果不构成临床内容verdict或官方reward。

## Y：payer证据核对的纯原型与开发shadow

`scripts/payer_evidence.py` 只核对引用边界：来源必须是本次payer运行实际送入主模型请求的公开instruction或已观察工具文本；片段用UTF-8文本的0起始、结束不含字符索引。文件来源从既有workspace allowlist的 `<case>/<role|shared>/...` 结构取case，公开handbook/instruction/tool reference标 `shared_public`；无路径case且无结构 `case_id` 的结果标不可归属，不能支持任意case。同一 `local-fs-read` 路径被重读且内容变化后，旧来源标 superseded，旧hash仍保留但不再作为当前支持。目标case只在整份核对通过后原子绑定，失败核对不污染后续。它不判断临床解释、必需性、签署效力或政策时效，`reference_validation=valid` 不是批准/证据充分。默认关闭，生产入口和正式包启动不会启用。

纯测试与合成shadow测试复用固定controller镜像、原SDK/PDF卷和固定vendor，禁网、只读根、无Key、无world；不要为运行本节安装或升级依赖：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$PWD:/workspace:ro" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  chi-agent-a-control:latest /opt/venv/bin/python -m pytest -q \
  tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py
```

包外开发装配仅在payer且显式设置 `CHI_DEV_EVIDENCE_SHADOW=shadow` 时，向 `run_chi()` 传 `evidence_shadow="shadow"`，增加 `local-evidence-sources`、`local-evidence-excerpt`、`local-evidence-check` 三个有界只读工具；它们经原dispatch lock、fatal检查、ToolContract与journal记录，只返回核对结果，不拦截业务MCP、不替Agent选择动作、不新增模型或账根。`off` 不增加工具、提示或请求。实际范围、go/no-go与限制只见[Y报告](reviews/payer-evidence-prototype-review.md)；本轮真实B/C/患者/评审请求为0。

## DeepSeek 本地开发评审

`scripts/development_review.py` 用固定 PA 规则和完整证据做本地诊断，报告名为 `development-review.json`，official reward 为 null。原版 Claude 评分与正式交付仍按 [审核状态](reviews/REVIEW_STATE.md) 的范围处理。

新的 K C 在确认 runner 退出后保存 `runs/development-review-inputs/<run-id>/`，包含有来源/hash 的业务 export、expectations 和原始 world；目录不挂给 participant。新题的非零退出也尝试捕获完整终态，wait 异常先停止并确认 runner；无法确认静止时标记 unavailable。捕获失败仍清理本次资源，并拒绝评审。旧 C 只有 trace/workspace 时不能补造成完整导出。participant 源码变更仍须 rebind 和当前源码 B，见上节；仅调整独立评审器不改变已捕获 C 的 participant 身份。

下面函数在 Bash/Zsh 中从 `chi-agent/` 运行。`plan` 不读输入/密钥、不写状态；`deterministic` 禁网，只返回部分程序检查；只有显式 `review` 注入已有 `.env` 并调用一次 DeepSeek，不自动重试。评审容器没有 Docker socket，不挂整个项目或受限手册。

执行 `review` 前按 [DeepSeek 开发评审的数据来源与审批证据](docs/docker-workflow.md#deepseek-开发评审的数据来源与审批证据)核对本次载荷，并在审批说明中引用固定官方合成数据声明、既有用户授权、实际发送范围及秘密缺席的离线证据。“本地”指本地编排，实际仍向外部 DeepSeek API 发送材料；检查通过与后续审批是否获准分别记录。

```sh
mkdir -p runs/development-review-inputs runs/development-review
chi_development_review() {
  typeset -a review_connection
  review_connection=(--network none)
  if [ "$1" = review ]; then
    review_connection=(--env-file "$PWD/.env")
  fi
  docker run --rm --read-only --tmpfs /tmp "${review_connection[@]}" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONPATH=/pdf-deps:/model-deps:/workspace/vendor/chi-bench/src \
    -v "$PWD/scripts:/workspace/scripts:ro" \
    -v "$PWD/profiles:/workspace/profiles:ro" \
    -v "$PWD/project.yaml:/workspace/project.yaml:ro" \
    -v "$PWD/requirements-model.lock:/workspace/requirements-model.lock:ro" \
    -v "$PWD/requirements-pdf.lock:/workspace/requirements-pdf.lock:ro" \
    -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
    -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
    -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
    -v "$PWD/runs/development-review-inputs:/workspace/runs/development-review-inputs:ro" \
    -v "$PWD/runs/real-c-development:/workspace/runs/real-c-development:ro" \
    -v "$PWD/runs/development-review:/workspace/runs/development-review:rw" \
    -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
    scripts/development_review.py "$@"
}
chi_development_review plan
chi_development_review deterministic \
  --input-dir runs/development-review-inputs/m-c-example-001
# 下一条是真实评审：使用实际已完成的 C ID 和一个新 review-id
chi_development_review review \
  --input-dir runs/development-review-inputs/m-c-example-001 \
  --review-id review-example-001
```

评审只把官方 adapter 生成的目标患者证据、Agent 产物和 rubric 按文件路径内联，不向模型提供 tools，也不发送整个原始 world。单次请求大小上限 2 MiB；本地审计 journal 可读到 32 MiB，其内容不直接内联给模型。独立评审生成上限为 32,768 tokens、360 秒总截止，单次在途网络读取最多额外约 60 秒；参赛 Agent 的生成参数由其原 profile 管理。超限、缺材料、字段/引用不合法或 verdict 缺项返回 incomplete，不能当作通过；stdout 只输出安全摘要，逐项判断保存在本地报告。

新题评审核对 task/resource、claim、journal、捕获、清理和已结算用量，付费评审持共享 controller 锁。可信失败终态可作开发诊断，输出保留 `attempt_status`，不把失败改成完成；未知用量、缺来源或未清理时拒绝。确定性结果与 DeepSeek verdict 分别保存，均不生成官方分数。

新增费用在 `runs/development-review/accounting.json` 独立累计，保留原 B/C 账目。发送前先持久占用，可信 usage 先结算；未知响应保留 pending 并阻止下一 review-id，不能删除目录清零后重试。估算使用峰值价格，不等于账单；模型替换后的逐项 verdict 不与主办方 Claude 分数混报。

## 首次真实 B/C 开发联调（J 历史入口）

`scripts/live_development.py` 是单独的本地真实入口：`plan`/`preflight` 只读，`init-prior` 显式初始化已有审核来源的首次真实账目，`b-smoke` 做真实模型工具往返，`c-once` 仅在 B 成功且预算足够后尝试一次固定官方题。先核对 [当前授权与实际结果](reviews/REVIEW_STATE.md)；本轮允许 B/C 合计最多 5 CNY，官方判分暂停。既有评测包入口仍固定 record_only/null cap，旧 live 拒绝不变。

以下仅保留 J 命令以复查历史；当前使用上面的 K 入口。复用已有 dev/controller/world 镜像、固定 vendor 和 H 的 SDK 卷；`.env` 只配置 `DEEPSEEK_API_KEY`，不提交 GitHub。不要删除旧 J 账目、回执或失败 claim 来重新执行。

```sh
# 只读，不读取密钥、不调用模型、不创建世界/账目
chi_live_control plan
chi_live_control preflight

# 仅在实际核对此前没有本项目真实 B/C 花费时初始化一次；已有记录拒绝覆盖
chi_live_control init-prior

# 真实执行：每次用独立 run-id；不自动重试失败或未知用量
chi_live_control b-smoke --run-id real-b-example-001
# 只有真实 B 成功且账目/身份/剩余预算符合要求后才允许下一条
chi_live_control c-once --run-id real-c-example-001
```

本地真实账目固定在 `runs/real-b-c/`，不因 run-id 或日志目录改变而重新获得 5 元；不要删除/复制状态来重跑。C 在创建世界前占用一次 claim，启动失败也保留。源码/profile/SDK 变化会使旧账目和 B 回执不匹配，此时停止，另行审查累计费用与身份接续，不能删除旧证据重新初始化。已知用量按 provider 回报记录，金额按 profile 高峰价估算，不能当成账单；未知用量/pending 不清零。详细证据位置、错误代码和实际通过范围见 [本轮审核](reviews/real-b-c-ungraded-review.md)。

runner 保留任务结果、轨迹、stdout/stderr、逐请求账目与工具 dispatch 记录；官方 reward 始终为 null。只有官方 MCP 业务工具和受限资源文件工具提供给模型，任务由模型自主执行，人工不在试跑中代选动作或修改结果。程序退出、模型声称完成与官方判分分别判断；正式冻结、评分和其他架构另行验收。

## 资料来源

核对日期：2026-10-19。

- [官方仓库与安装说明](https://github.com/actava-ai/chi-bench)
- [官方单任务 Quickstart](https://www.actava.ai/benchmarks/docs/quickstart)
- [自定义 Agent 接入](https://github.com/actava-ai/chi-bench/blob/main/docs/extending.md)
- [OpenSpec 结构与场景格式](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)

依赖版本、任务 ID 和命令以实施时固定的上游提交及对应文档为准；不把示例模型名当作已经可用的配置。
