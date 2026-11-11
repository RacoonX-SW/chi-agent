# 仓库整理设计

## Context

`fdff6cf` 是 PR #101 的合并提交。当前 Git 根下有一个 `chi-agent/` 外层目录，两种 bundle 各自通过显式源路径映射构建与校验。Go 入口预检、Harbor 导入、角色开发调度及 A 阶段 Compose 还有各自的路径约定。累计开发记录跨多个候选，最新六题基线也对应多份冻结包。

## Goals / Non-Goals

目标是让干净检出可直接浏览、测试和导出程序包，保持已有交付入口及旧包校验能力。范围限于重排、命名、依赖接线和离线复验。运行策略变更、旧账处置、真实模型、官方评分及比赛交付按各自规格和授权处理。

## Decisions

### 1. 根目录与维护资料

- 将 `Dockerfile`、两份 Compose、`docker/`、`pyproject.toml`、`project.yaml`、依赖锁及输入文件、`profiles/`、`tests/`、`openspec/` 与 `.env.example` 提至 Git 根目录。合并根和原项目的 Git 忽略规则。根 Docker 忽略规则覆盖遗留的本地 `chi-agent/`、凭据和数据目录。仅迁移 Git 跟踪文件。
- 根 README 保留项目简介、代码导航、从根目录构建和导出 Go 包的 Docker 快速开始，以及一段成果摘要。摘要给出累计覆盖和三领域数量，再用一句话记录最新六题基线，附一个成果证据索引链接。首页不列逐轮验证、测试数量或阶段过程。
- `docs/` 仅保留 `go-chi-entry-runbook.md` 和 `evaluation-entry-runbook.md`。两份手册保留当前配置、运行前置条件、导出和使用命令，并作为对应包的输入。现行协作、Docker、GitHub 和授权规则归入根 `AGENTS.md`，短版 `REVIEW_STATE.md` 迁至 `openspec/`，记录当前授权、审核、未决事项和成果证据索引。学习约定与长账本、协作过程文档、历史复盘和 `reviews/` 阶段报告移出默认分支文件树，从 [固定提交](https://github.com/xsw932187210-cell/chi-agent/tree/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d) 查阅。
- `openspec/` 保留配置、现有增量规格及所属变更，并保留用于当前入口和未决事项的 `chi-go-evaluation-entry`、`final-validation-admission`、`harbor-launch-coverage`、`opencode-go-provider`、`reasoning-output-budget`、`representative-role-baseline`、`score-readiness-hardening`、`unified-role-cm-lifecycle`。其余六个旧变更和 `bootstrap-baseline` 的早期交接与复审草稿通过固定提交查阅。旧待处理事项保留在其原清单，仍相关的条目从审核状态链接。更新现行入口的相对链接，将指向历史的链接固定到原路径和提交。

### 2. 成果口径

累计覆盖按公开 `task_id` 去重。Go 运行以实际结算的主模型请求为依据，早期直连运行以正用量的 runner 结果和对应任务记录为依据。当前核对到至少 20 个，分布如下。

| 领域 | 已核对任务 | 数量 |
| --- | --- | ---: |
| Provider | t012、t013、t014、t015、t016、t017、t018、t019、t021、t032 | 10 |
| Payer | t011、t022、t023、t024、t027、t030 | 6 |
| CM | AFib、anorexia、asthma、CKD | 4 |

- Go 的 17 个任务各有至少一次 `complete + claim`。早期直连的 Provider t013、t018、t019 各有一次或以上 `completed_ungraded`。这些是不同版本下的开发记录，官方评分字段为 `null`。[直连 t013/t019](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/request-budget-awareness-review.md) · [直连 t018](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/deepseek-development-review.md)
- 最近的 `16384` 基线包含 Payer t022、t023、t024 和 CM anorexia、asthma、CKD。六题均有完成声明及 `inspect_history=inspected`，已计入累计覆盖。[最新六题汇总](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/cm-asthma-baseline-rerun-20261111.md#3-当前六题状态)
- 成果索引从固定报告追溯每批候选、结果和失败。九题 BDE 当轮有 4 个完成声明、2 个被完成检查阻断、3 个失败。原始账本和运行轨迹留在本地。[Go 三题](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/go-chi-timeout-recovery-review.md) · [三角色运行](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/unified-role-cm-lifecycle-review.md) · [九题 BDE](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/nine-task-bde-execution-20261107.md#1-结果总表) · [Payer t027](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/c5-p2p-public-path-review.md) · [Payer t030](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/c1-c3-admission-package-review.md#3-payer-010及后继的事实链)

### 3. 源码、命令与容器

- `src/chi_agent/` 收两种包原显式清单中 Python 源文件的并集。包内使用相对导入，包外使用限定模块名。将源码安装路径和 Compose 的源码挂载对齐 `/workspace`。从根目录运行的包外 Python 入口使用 `python -m scripts.<目录>.<模块>`。保留两个运行环境中的路径校验与身份检查。
- `scripts/development/` 保留当前角色调度依赖的开发功能，含仍被调度调用的旧开发采集逻辑。`scripts/experiments/` 保留早期探针、演练和旧版操作者。`scripts/tools/` 提供构建、检查与汇总命令。仓库内的旧路径以本页对照迁移，导出包的兼容入口按下节维护。
- 按显式文件映射调整 controller、开发 runner 和 CM world 的挂载。现有 `dev_sha256` 的键继续用于验证对应的已更名文件，哈希按实际新版字节生成。继续仅挂载各容器使用的开发文件，保留 CM world 的 `cb` 入口、runner 和 world 的权限边界。同步测试用导入、动态导入、子进程命令和模块归属检查。
- 干净检出的测试可将原 checkout 的固定 vendor 源码只读挂到容器约定路径。原目录下的本地输入和运行产物留在原处。工作流注明在新根目录使用调用方提供的有效资源路径，已有运行可用对应冻结 checkout 或只读汇总入口查阅。

### 4. 两种导出包与身份兼容

| 导出包 | 新 manifest schema | 新 bundle ID | 保留的启动入口 |
| --- | --- | --- | --- |
| Go | `chi-go-evaluation-bundle-v2` | `go-chi-evaluation-record-only-v2` | `scripts/go_chi_entry.py`、`go_chi_harness:GoChiHarness` |
| 兼容评测 | `chi-evaluation-entry-bundle-v2` | `evaluation-entry-identified-record-only-v2` | `scripts/evaluation_entry.py` |

- 保留按包维护的源文件到目标文件白名单，按原包的源码归属把模块复制到 `scripts/chi_agent/`，包含包初始化文件。把薄启动文件放在源码 `docker/entrypoints/`，导出到原 CLI 和 Harbor 路径。配置、依赖锁、安装脚本、随包手册以及 vendor 挂载点沿用各自的交付位置。从包外工作目录用原命令启动，按包自身路径解析配置与身份，禁止写入字节码缓存。
- 构建器只生成 v2。两个校验器分别内置 `fdff6cf` 对应的 v1 固定成员集合和 v2 清单，用有界读取及准确的 schema、bundle ID 选择对应清单。沿用完整树、拒绝链接、字节摘要及缺失和额外成员检查。外层 release 沿用原 schema 和四个顶层成员，依据已验证内层包的清单复核文件与校验和。
- 当前迁移基线的 v1 包可由新版工具校验。历史包继续配原导出程序、依赖与冻结的开发配置运行。新版开发调度使用新版 bundle 和匹配的配置哈希。两代包各自从其清单和依赖计算身份，新包需要独立准入。六题证据、已知失败、未结算记录和旧 B 收据继续绑定原身份。
- `scripts/tools/inspect_imports.py` 扫描限定模块名和函数内导入，并按两个显式清单检查包内闭包。维护者可以从设计中的迁移表核对模块归属。选择显式映射可以同时审阅仓库路径和导出边界。

### 5. 验证入口与记录

- `scripts/tools/verify_offline.sh` 是运行手册中的常规离线入口。开发镜像内一次执行完整 pytest，收集适用的 unittest 和 pytest 用例。Controller 镜像只执行它独有的专项检查。两种包各构建、校验并做一次隔离预检。
- 布局迁移 PR 还复验 v1 兼容、成员篡改拒绝、角色挂载和合成 Harbor 启动。复用现有测试与演练。PR 描述集中记录通过、失败、跳过和环境限制。

## Risks / Trade-offs

- 路径变动分布在代码、Compose、包构建器和 Harbor 适配器中。按已固定清单完成迁移，通过隔离导出的启动测试验证路径接线。
- 两代包的 manifest 需要保留两个成员集合。以基线生成的 v1 样本和新构建的 v2 样本验收，包含未知版本、成员不匹配及篡改反例。
- 阶段结果来自不同的冻结候选。首页呈现累计开发覆盖和最新六题基线，重排候选的验证结果在 PR 中记录。

## Migration Plan

在独立工作树中审定提案，记录审批后依次提交根目录迁移、源码与包布局、文档收敛。迁移后从新根解析 OpenSpec。完成 Docker 回归和独立复验后同步并归档本变更，开一个面向 `main` 的 PR。用户合并后 GitHub 默认分支展示新入口。若需回到旧布局，可直接检出原固定提交。

## 72 个文件的迁移对照

原文件相对于 `chi-agent/scripts/`，新文件相对于各表标题目录。新增包初始化与导出入口文件单独按上述打包约定处理。

### src/chi_agent（41 个）

| 原文件 | 新文件 |
| --- | --- |
| `b_execution_policy.py` | `execution_policy.py` |
| `b_live_preflight.py` | `evaluation_preflight.py` |
| `b_model_adapter.py` | `model_adapter.py` |
| `b_provider_profile.py` | `provider_profile.py` |
| `b_provider_transport.py` | `provider_transport.py` |
| `budget_evaluation.py` | `budget_evaluation.py` |
| `evaluation_bundle.py` | `evaluation_bundle.py` |
| `evaluation_entry.py` | `evaluation_cli.py` |
| `go_chi_assembly.py` | `context_assembly.py` |
| `go_chi_auxiliary.py` | `auxiliary_transport.py` |
| `go_chi_bundle.py` | `bundle.py` |
| `go_chi_completion.py` | `completion.py` |
| `go_chi_context.py` | `context_budget.py` |
| `go_chi_contract.py` | `tool_contract.py` |
| `go_chi_delivery.py` | `delivery.py` |
| `go_chi_diagnostics.py` | `diagnostics.py` |
| `go_chi_entry.py` | `cli.py` |
| `go_chi_evidence.py` | `evidence.py` |
| `go_chi_guard.py` | `request_guard.py` |
| `go_chi_guidance.py` | `role_guidance.py` |
| `go_chi_harness.py` | `harbor_adapter.py` |
| `go_chi_index.py` | `resource_index.py` |
| `go_chi_inspect.py` | `provider_inspection.py` |
| `go_chi_journal.py` | `journal.py` |
| `go_chi_local.py` | `local_history.py` |
| `go_chi_mcp.py` | `mcp_tools.py` |
| `go_chi_policy.py` | `runtime_policy.py` |
| `go_chi_recovery.py` | `output_recovery.py` |
| `go_chi_resources.py` | `workspace_paths.py` |
| `go_chi_runtime.py` | `runtime.py` |
| `go_chi_search.py` | `text_search.py` |
| `go_chi_state.py` | `task_state.py` |
| `go_chi_summary.py` | `input_summary.py` |
| `go_chi_tools.py` | `local_tools.py` |
| `model_runner_adapter.py` | `model_runner_adapter.py` |
| `opencode_go_provider.py` | `opencode_go_provider.py` |
| `patient_identity_binding.py` | `patient_identity_binding.py` |
| `payer_evidence.py` | `payer_evidence.py` |
| `pdf_resource_reader.py` | `pdf_resource_reader.py` |
| `referral_field_guidance.py` | `referral_field_guidance.py` |
| `request_budget.py` | `request_budget.py` |

### scripts/development（14 个）

| 原文件 | 新文件 |
| --- | --- |
| `a_environment.py` | `world_environment.py` |
| `dev_patient_adapter.py` | `patient_adapter.py` |
| `dev_patient_bootstrap.py` | `patient_bootstrap.py` |
| `dev_patient_broker.py` | `patient_broker.py` |
| `dev_patient_cb` | `patient_cb` |
| `development_review.py` | `review_run.py` |
| `go_chi_operator_snapshot.py` | `capture_resources.py` |
| `live_development.py` | `run_development_legacy.py` |
| `provider_task_resources.py` | `provider_task_resources.py` |
| `role_cm_capture.py` | `capture_cm_state.py` |
| `role_operator.py` | `run_role.py` |
| `role_resource_preflight.py` | `role_resource_preflight.py` |
| `role_runner.py` | `run_role_in_bundle.py` |
| `role_world_preflight.py` | `check_role_world.py` |

### scripts/experiments（10 个）

| 原文件 | 新文件 |
| --- | --- |
| `a_tools_probe.py` | `probe_official_tools.py` |
| `b_model_probe.py` | `probe_model_tools.py` |
| `c_run_control.py` | `rehearse_single_run.py` |
| `check_readiness.py` | `check_readiness.py` |
| `d0_gate_policy.py` | `baseline_gate_policy.py` |
| `dev_patient_probe.py` | `probe_patient_simulator.py` |
| `experiment_manifest.py` | `validate_experiment_manifest.py` |
| `experiment_summary.py` | `summarize_experiments.py` |
| `go_chi_operator.py` | `run_provider_legacy.py` |
| `run_baseline.py` | `run_baseline.py` |

### scripts/tools（7 个）

| 原文件 | 新文件 |
| --- | --- |
| `dev_verify.sh` | `verify_offline.sh` |
| `go_chi_readiness_inventory.py` | `inspect_readiness.py` |
| `go_chi_release.py` | `release_bundle.py` |
| `go_chi_run_summary.py` | `summarize_runs.py` |
| `import_inventory.py` | `inspect_imports.py` |
| `install_model_dependencies.sh` | `install_model_dependencies.sh` |
| `make_role_manifest.py` | `build_role_manifest.py` |
