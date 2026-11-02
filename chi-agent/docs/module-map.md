# 模块、调用与发布边界地图（M1）

建立：2026-11-02。只读分析 + 包外工具 `scripts/import_inventory.py` 生成；基线 `origin/main` `fc7d678`；分析时另核对了 PR39 文档树 `04cf1a8`。本图不移动文件、不改包、不把旧模块整体判废。

## 1. 三个发布边界

| 边界 | 定义处 | 内容 |
| --- | --- | --- |
| 内层 bundle | `go_chi_bundle.PACKAGE_FILES` | 31 个自有 `.py` + profile/lock/runbook；`build_bundle` 计算 manifest |
| 外层 release | `go_chi_release.TOP_LEVEL` | `package/` + `release-manifest.json` + `SHA256SUMS` + `supply-plan.example.json` |
| 供应检查 | `go_chi_delivery.check_plan` | 调用方是否提供包/依赖/vendor/资源/日志/state/凭据 |

`PACKAGE_FILES` 是唯一进包依据；目录名和文件位置不构成边界。

## 2. 分类

- **runtime**：参赛包执行链
- **tool**：包外可靠性工具（不进包）
- **guard**：发送前校验、账目、证据、时间策略
- **capability**：F1–F6 自有能力（状态/指导/检索/上下文/本地工具）
- **tools**：MCP 工具面、路径、实体、PDF
- **build**：内层包、外层 release、供应检查
- **devop**：包外开发调度/实验/预检
- **devsim**：开发患者模拟（不进入参赛包）
- **legacy**：旧入口或兼容模块；**只要仍被导入就不算废弃**

## 3. 全量模块表（60 个：58 个业务/平台模块 + 2 个包外可靠性工具）

| 模块 | 分类 | 进包 | 行数 | 用途 | 被谁导入 |
| --- | --- | --- | ---: | --- | --- |
| `a_environment` | devop | 否 | 1095 | Docker/world 环境辅助 | go_chi_operator, go_chi_operator_snapshot, live_development… |
| `a_tools_probe` | legacy | 否 | 544 | A 工具探针 | — |
| `b_execution_policy` | legacy | 是 | 163 | B 执行策略 | b_live_preflight, b_provider_transport, evaluation_entry… |
| `b_live_preflight` | legacy | 否 | 385 | B 现场预检 | evaluation_entry, live_development |
| `b_model_adapter` | legacy | 是 | 237 | 旧 B 模型适配 | b_model_probe, model_runner_adapter |
| `b_model_probe` | legacy | 否 | 411 | B 探针 | — |
| `b_provider_profile` | legacy | 是 | 209 | B 提供方 profile | b_live_preflight, b_provider_transport, development_review… |
| `b_provider_transport` | legacy | 是 | 1071 | 旧 B 传输/usage 校验（guard 复用） | b_live_preflight, development_review, go_chi_auxiliary… |
| `c_run_control` | legacy | 否 | 664 | 旧 C 运行控制 | — |
| `check_readiness` | devop | 否 | 522 | 环境/依赖就绪检查 | — |
| `d0_gate_policy` | legacy | 否 | 289 | 旧 gate/预算策略 | check_readiness, run_baseline |
| `dev_patient_adapter` | devsim | 否 | 34 | 开发患者适配器 | dev_patient_bootstrap, dev_patient_probe |
| `dev_patient_bootstrap` | devsim | 否 | 28 | 开发患者启动参数 | — |
| `dev_patient_broker` | devsim | 否 | 101 | 开发患者 broker（HTTP） | role_runner |
| `dev_patient_probe` | devsim | 否 | 118 | 患者通道探针 | — |
| `development_review` | devop | 否 | 628 | 开发评审轨迹 | go_chi_operator, role_operator, role_world_preflight |
| `evaluation_bundle` | build | 是 | 369 | 路径/组件安全校验 | dev_patient_probe, evaluation_entry, go_chi_entry… |
| `evaluation_entry` | legacy | 否 | 319 | 旧评测入口 | — |
| `experiment_manifest` | devop | 否 | 194 | 实验清单校验 | experiment_summary |
| `experiment_summary` | devop | 否 | 256 | 全分母汇总 | — |
| `go_chi_auxiliary` | runtime | 是 | 94 | 患者辅助通道计量与守卫 | dev_patient_broker, dev_patient_probe |
| `go_chi_bundle` | build | 是 | 393 | 内层包 allowlist/构建/校验 | go_chi_delivery, go_chi_entry, go_chi_release |
| `go_chi_context` | capability | 是 | 88 | 上下文预算测量/检查 | go_chi_guard, go_chi_runtime |
| `go_chi_contract` | guard | 是 | 202 | 工具批次与历史契约 | go_chi_guard |
| `go_chi_delivery` | build | 否 | 231 | 调用方供应检查 | go_chi_release |
| `go_chi_entry` | runtime | 是 | 422 | CLI 入口：preflight/coding-b/live/对账/审计 | dev_patient_probe, role_runner |
| `go_chi_evidence` | guard | 是 | 128 | 证据文件读写与校验 | go_chi_journal |
| `go_chi_guard` | guard | 是 | 270 | 请求/响应/历史/超时守卫 | go_chi_entry, go_chi_runtime |
| `go_chi_guidance` | capability | 是 | 164 | 版本化角色阶段指导 | go_chi_runtime, go_chi_tools |
| `go_chi_harness` | runtime | 是 | 281 | Harbor adapter（合成 Trial 验证过，真实未跑） | — |
| `go_chi_inspect` | guard | 是 | 83 | 只读历史检查 | go_chi_entry, go_chi_journal |
| `go_chi_journal` | guard | 是 | 1090 | 账本、pending、seal、receipt | dev_patient_probe, go_chi_entry |
| `go_chi_local` | runtime | 是 | 14 | 本地 Q 历史接续 | dev_patient_probe, go_chi_entry |
| `go_chi_mcp` | tools | 是 | 250 | 官方 MCP 发现/角色工具面 | go_chi_runtime, role_runner |
| `go_chi_operator` | devop | 否 | 240 | 旧开发 operator | — |
| `go_chi_operator_snapshot` | devop | 否 | 63 | operator 状态快照 | go_chi_operator, role_operator, role_world_preflight |
| `go_chi_policy` | guard | 是 | 14 | 固定时间/费用策略 | dev_patient_probe, go_chi_entry, go_chi_guard… |
| `go_chi_release` | build | 否 | 201 | 外层 release 包装/校验 | — |
| `go_chi_resources` | tools | 是 | 31 | 角色工作区路径约束 | go_chi_runtime, go_chi_tools, role_operator |
| `go_chi_runtime` | runtime | 是 | 317 | 单角色运行循环与工具装配 | go_chi_entry |
| `go_chi_search` | capability | 是 | 154 | 有界文本检索 | go_chi_tools |
| `go_chi_state` | capability | 是 | 571 | 有界任务状态与校验 | go_chi_mcp, go_chi_runtime, go_chi_tools |
| `go_chi_tools` | capability | 是 | 512 | 本地工具面（fs/state/guidance/completion） | go_chi_runtime |
| `import_inventory` | tool | 否 | 220 | 包外导入/打包边界清单 | — |
| `live_development` | legacy | 否 | 2718 | 旧开发主循环（2718 行） | development_review, go_chi_operator, role_operator… |
| `make_role_manifest` | tool | 否 | 209 | 包外资源 manifest 生成 | — |
| `model_runner_adapter` | legacy | 是 | 1205 | 旧 SDK 适配；Go 复用兼容补丁 | b_live_preflight, go_chi_entry, go_chi_runtime… |
| `opencode_go_provider` | runtime | 是 | 817 | Go provider 常量/传输/账本原语 | go_chi_auxiliary, go_chi_entry, go_chi_evidence… |
| `patient_identity_binding` | tools | 是 | 401 | provider 患者实体绑定 | b_provider_transport, go_chi_mcp, go_chi_runtime… |
| `payer_evidence` | tools | 是 | 457 | payer 证据影子原型 | go_chi_tools |
| `pdf_resource_reader` | tools | 是 | 85 | PDF 受限读取 | go_chi_entry, go_chi_tools, live_development |
| `provider_task_resources` | devop | 否 | 67 | provider 任务资源选择 | development_review, live_development |
| `referral_field_guidance` | capability | 是 | 37 | 转诊字段提示 | go_chi_mcp, live_development |
| `request_budget` | guard | 是 | 41 | 剩余请求/预算反馈 | b_provider_transport, go_chi_contract, go_chi_runtime… |
| `role_cm_capture` | devop | 否 | 119 | CM 世界产物捕获 | role_operator, role_world_preflight |
| `role_operator` | devop | 否 | 303 | 开发运行编排（world+runner） | — |
| `role_resource_preflight` | devop | 否 | 105 | 角色资源 manifest 校验 | make_role_manifest, role_operator, role_world_preflight |
| `role_runner` | devop | 否 | 122 | 开发 runner 包装（broker/能力开关） | — |
| `role_world_preflight` | devop | 否 | 189 | world/资源预检 | — |
| `run_baseline` | legacy | 否 | 871 | 旧单任务 baseline 入口 | b_model_probe, c_run_control, check_readiness… |

## 4. 边界穿越与复用（实际调用，不按文件名判断）

- **包内 → 包外**：仅 `model_runner_adapter` 在函数内导入 `run_baseline.evaluate_budget`；`run_baseline` 不在 allowlist。Go 主链不调用 `_budget_check()`，属潜在 ImportError（已登记给 C3，未修）。
- **包外 → 包内**：开发 operator/runner/预检大量复用 `go_chi_entry`、`go_chi_bundle`、`evaluation_bundle`、`go_chi_operator_snapshot` 等；这是正常复用，不是包依赖缺陷。
- **仍被复用的旧函数**：`b_provider_transport`（guard 复用 usage 校验）、`model_runner_adapter._patch_empty_history_compatibility`（runtime 复用）、`live_development` 的捕获函数（`role_operator` 复用）。
- **动态导入**：`go_chi_runtime`/`go_chi_tools` 用 `__import__("asyncio")`、`go_chi_entry` 用 `importlib.import_module` 处理可选路径；静态清单单列为 dynamic，不当作未知外部包。

## 5. 检查工具

`python scripts/import_inventory.py [--json] [--root DIR] [--allow-unknown]`

- 输出模块、进包标记、顶层/函数内导入分类、importers、closure gaps、unknown、unlocked external；
- 发现缺口或未分类导入时退出码 1；
- 不导入项目模块（用 AST 读 `PACKAGE_FILES`），不写文件、不读凭据。

M1建立时运行结果（2026-11-02；后续C3修复见第7节）：

```
modules=60 packaged=31
GAP model_runner_adapter -> run_baseline
UNLOCKED a_environment: docker, huggingface_hub
UNLOCKED go_chi_operator: docker.types
UNLOCKED role_operator: docker.types
```

`docker` SDK 不在任何 `requirements*.lock` 中，只在 controller 镜像里安装；`huggingface_hub` 同样未锁（`a_environment` 使用）。这两项属环境漂移风险，登记给 C4/负责人，不在 M1 修复。

## 6. 未做

以下为M1建立时边界，C3后续变更见第7节；旧清单/行数不冒充新版本全量再生成结果。

- 未移动任何目录，未改 `PACKAGE_FILES`，未修 `run_baseline` 闭包；
- 未把 legacy 模块标为废弃（多个仍被 dev 路径导入）；
- 未做运行时导入对称性验证（M3 的隔离包检查负责）。

## 7. C3最小闭包修正

`model_runner_adapter._budget_check()`改为局部导入`budget_evaluation.evaluate_budget`，`run_baseline`从同一纯模块重导出原函数。新模块只依赖标准库`decimal`，同时列入Go和旧evaluation的`PACKAGE_FILES`及相关显式源码身份清单；没有把`run_baseline`或`d0_gate_policy`打进包。

| 模块 | 分类 | Go进包 | 用途 | 被谁导入 |
| --- | --- | --- | --- | --- |
| `budget_evaluation` | legacy/guard | 是 | 原CNY预算纯函数，保留拒绝语义及签名 | model_runner_adapter（局部）, run_baseline（重导出） |

当前静态检查Go包自有Python模块33个，`closure_gaps=[]`、`unknown_imports=[]`；C2另已加入`go_chi_recovery`。上面的M1模块表保留原快照，原“包内→包外”缺口现已关闭。`docker`/`huggingface_hub`未锁风险不在C3处理。隔离包实际调用、失败反例、真实身份及历史限制见[C1/C3阶段报告](../reviews/c1-c3-admission-package-review.md)。
