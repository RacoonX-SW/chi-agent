# Design

## Context

动机见 [proposal.md](proposal.md)。基线 `e2404fb` 的 `src/chi_agent/` 有 42 个 Python 文件，包含 `__init__.py` 和 41 个功能模块。

已查明的迁移接点如下。

- `bundle.py` 和 `evaluation_bundle.py` 分别以 `PACKAGE_FILES` 声明显式源文件映射，并保留 v1 清单。当前导出成员位于 `scripts/chi_agent/*.py`，当前 manifest 为 v2。
- 根 `cli.py`、`evaluation_cli.py`、`bundle.py`、`evaluation_bundle.py` 是已使用的模块入口。`docker/entrypoints/` 的三个脚本导入根 CLI 和 Harbor 适配器。
- `evaluation_cli.py` 有运行身份源文件清单。若干模块使用 `Path(__file__).parents[...]` 定位仓库或包资源。
- `runtime.py` 会从 `model_runner_adapter.py` 加载 SDK 兼容处理。子包之间将继续存在这种实际依赖。
- `scripts/tools/inspect_imports.py` 已递归扫描源码和导出包，并静态读取根 bundle 模块中的 `PACKAGE_FILES`。`scripts/tools/replay_trace.py` 已提供合成轨迹的 `run` 和 `compare`。
- 工作树另有未跟踪的 `provider-location-tool-recovery` 提案。本变更的文件范围为 `organize-source-packages` 及后续获批的迁移路径。

## Goals / Non-Goals

### Goals

- 让文件夹直接表达职责，将 35 个模块移入七个子包。
- 沿用当前文件名、现有命令和直接导入方式，以显式迁移表核对每个原文件。
- 仓库和独立包各自完成依赖闭合，按三个版本区分包身份。
- 以固定基线的离线回归和合成轨迹复演检验迁移后的执行行为。

### Non-Goals

本轮工作限定于文件归属、导入、资源路径、打包边界及其验证。函数拆分、业务规则调整、模型或 Prompt 调优和新的真实模型试跑留在各自的功能变更中。历史数据和本地旧 `chi-agent/` 目录继续按原身份管理。

## Decisions

### 1. 七个职责子包与包根入口

```text
src/chi_agent/
├── __init__.py
├── cli.py
├── bundle.py
├── evaluation_bundle.py
├── evaluation_cli.py
├── harbor_adapter.py
├── delivery.py
├── agent/          Agent 运行、任务状态、完成核验、运行策略
├── context/        上下文组装、预算、摘要和输出恢复
├── tools/          MCP、本地工具、调用契约和授权资源读取
├── models/         模型协议、配置、传输和请求控制
├── accounting/     账本、证据、费用策略和安全诊断
├── roles/          角色阶段、患者绑定和保险证据规则
└── evaluation/     评测预检和官方 runner 适配
```

每个子包增加轻量 `__init__.py`。初始化文件只建立包边界。根目录的 7 个文件继续承担已有入口和交付职责，使现有命令直接定位原入口实现。

目录按当前职责命名，保留现有模块名。完整迁移表包括保留在根的文件，便于检查遗漏和重复实现。

| 当前文件 | 目标路径 |
| --- | --- |
| `__init__.py` | `__init__.py` |
| `auxiliary_transport.py` | `models/auxiliary_transport.py` |
| `budget_evaluation.py` | `accounting/budget_evaluation.py` |
| `bundle.py` | `bundle.py` |
| `cli.py` | `cli.py` |
| `completion.py` | `agent/completion.py` |
| `context_assembly.py` | `context/context_assembly.py` |
| `context_budget.py` | `context/context_budget.py` |
| `delivery.py` | `delivery.py` |
| `diagnostics.py` | `accounting/diagnostics.py` |
| `evaluation_bundle.py` | `evaluation_bundle.py` |
| `evaluation_cli.py` | `evaluation_cli.py` |
| `evaluation_preflight.py` | `evaluation/evaluation_preflight.py` |
| `evidence.py` | `accounting/evidence.py` |
| `execution_policy.py` | `accounting/execution_policy.py` |
| `harbor_adapter.py` | `harbor_adapter.py` |
| `input_summary.py` | `context/input_summary.py` |
| `journal.py` | `accounting/journal.py` |
| `local_history.py` | `accounting/local_history.py` |
| `local_tools.py` | `tools/local_tools.py` |
| `mcp_tools.py` | `tools/mcp_tools.py` |
| `model_adapter.py` | `models/model_adapter.py` |
| `model_runner_adapter.py` | `evaluation/model_runner_adapter.py` |
| `opencode_go_provider.py` | `models/opencode_go_provider.py` |
| `output_recovery.py` | `context/output_recovery.py` |
| `patient_identity_binding.py` | `roles/patient_identity_binding.py` |
| `payer_evidence.py` | `roles/payer_evidence.py` |
| `pdf_resource_reader.py` | `tools/pdf_resource_reader.py` |
| `provider_inspection.py` | `models/provider_inspection.py` |
| `provider_profile.py` | `models/provider_profile.py` |
| `provider_transport.py` | `models/provider_transport.py` |
| `referral_field_guidance.py` | `roles/referral_field_guidance.py` |
| `request_budget.py` | `accounting/request_budget.py` |
| `request_guard.py` | `models/request_guard.py` |
| `resource_index.py` | `tools/resource_index.py` |
| `role_guidance.py` | `roles/role_guidance.py` |
| `runtime.py` | `agent/runtime.py` |
| `runtime_policy.py` | `agent/runtime_policy.py` |
| `task_state.py` | `agent/task_state.py` |
| `text_search.py` | `tools/text_search.py` |
| `tool_contract.py` | `tools/tool_contract.py` |
| `workspace_paths.py` | `tools/workspace_paths.py` |

### 2. 调用方直接迁移到实现路径

同步调整相对导入、绝对导入、函数内导入、动态模块名和测试中的 patch 目标。保留现有延迟导入的时机，按原调用链加载跨组依赖。包根保留的入口直接引用迁移后的模块。

`models/` 中的 provider 表示模型服务提供方。医疗机构角色的业务规则集中在 `roles/`。`evaluation/model_runner_adapter.py` 的 SDK 兼容函数仍由正式运行链调用，Go 打包清单据此保留该模块及其依赖。

实现前后逐项对照工具描述、JSON Schema、业务状态 schema、错误码、预算策略和 Prompt 常量。路径与源码摘要按新文件位置计算，运行行为以既有测试和合成轨迹的观测为验收依据。

### 3. 新包使用 v3，旧清单冻结

| 程序包 | 新 manifest schema | 新 bundle ID |
| --- | --- | --- |
| Go | `chi-go-evaluation-bundle-v3` | `go-chi-evaluation-record-only-v3` |
| 兼容评测 | `chi-evaluation-entry-bundle-v3` | `evaluation-entry-identified-record-only-v3` |

在两个根 bundle 模块中保留现有 `V1_PACKAGE_FILES`，将 `e2404fb` 的当前成员映射冻结为 `V2_PACKAGE_FILES`，用字面量 `PACKAGE_FILES` 声明 v3 的目标到源路径映射，沿用现有静态导入检查器的读取方式。

新包中的 Python 源码按仓库子包关系放在 `scripts/chi_agent/` 下。每种包只收录其实际依赖的模块、必需的子包初始化文件和已有允许成员。构建器逐项复制显式映射中的字节。

校验器严格匹配 schema 与 bundle ID 后选择 v1、v2 或 v3 清单，并执行原有完整树、链接、大小和摘要校验。外层 release 继续核对其内层包实际成员与校验和。

导出的 `scripts/go_chi_entry.py`、`scripts/evaluation_entry.py` 以及 `go_chi_harness:GoChiHarness` 保持既有加载方式。根 CLI 的源码身份集合、配置身份和预检输出使用对应新包成员。旧历史身份使用旧源码和包做只读复核。

### 4. 路径与验证入口同步

逐项核对 `__file__` 根路径推导、vendor 查找、资源配置、运行身份文件集合和入口源路径。迁入一层子包的模块按其新固定深度解析路径，并分别验证仓库树与导出树的资源定位。

沿用 `scripts/tools/verify_offline.sh`，补齐它需要的新导入路径和包校验覆盖。README 的结构说明与两份运行手册指向新目录。验证结果集中放在本变更任务记录和最终 PR 中。

## Risks / Trade-offs

- 跨组循环依赖或错误的提前导入 → 保留函数内导入的位置，运行现有导入检查与真实入口预检，核对两类包的依赖闭合。
- 包内源码可以导入，隔离启动时缺模块 → 分别在仓库外、关闭网络的容器中加载两种包，用显式清单校验所有子包初始化文件。
- 旧包误用新清单 → 为 v1、v2 固定样本复核身份，并覆盖版本与目录互换、缺失初始化文件、额外成员、符号链接和内容篡改反例。
- 模块移动改变资源根定位或 runtime source 身份 → 对照 `evaluation_cli.py` 的显式源文件集合与所有 `parents[...]` 用法，分别验收仓库入口、包入口和合成 Harbor。
- 故障回归被路径更新掩盖 → 在基线与候选各运行固定的 Trace/Replay suite，以事件、状态、调用派发和完成声明对比行为，报告保留各自的源码与环境身份。

## Migration Plan

1. 用户审核本提案，批准依据写入 `proposal.md`，实施进度统一记入 `tasks.md`。
2. 在 `codex/source-package-layout` 固定基线的两个 v2 包与离线复演结果，并准备已有 v1 样本。记录实际依赖镜像和挂载资源。按根 AGENTS 的分工，由一名 `gpt-6.1-terra` / `high` 子代理实施并在 Docker 内自测，主代理固定候选并独立复验。
3. 迁移 35 个模块，加入七个初始化文件，同步导入、资源定位、身份集合和测试补丁目标。
4. 更新两类 v3 显式清单、历史版本选择和相关验收，独立构建并检查两个新包。
5. 主代理审阅差异，在 Docker Python 3.12 中独立复验入口、全量离线回归、controller 专项和合成 Harbor。通过、失败、跳过和环境限制按实际记录。
6. 对照源码和包的导入检查、历史包验证以及 Trace/Replay 行为差异，完成文档结构说明。按项目流程同步规格并归档，创建面向 `main` 的 PR，由用户验收和合并。

候选按普通提交审阅。需要撤回时，可检出本变更之前的固定提交并使用该提交对应的包与说明，历史运行继续引用原包身份。
