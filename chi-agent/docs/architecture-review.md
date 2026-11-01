# 架构与代码评审（2026-11-02）

范围：`chi-agent/scripts` 61 个模块 / 约 2.1 万行，加测试与证据链。只读分析，未改实现。
结论：已踩的坑（profile 漂移、`index` 字段、workspace 路径、guidance digest、8192 六处、包外 import）根因相同——**同一事实重复表达，缺少单一来源**。

## 1. 配置与常量分散（高影响）

| 事实 | 出现位置 |
| --- | --- |
| 主输出 8192 | `go_chi_entry.py:31`、`go_chi_guard.py:89/246`、`go_chi_journal.py:725/974`、`go_chi_inspect.py:65`、`go_chi_auxiliary.py:40/73`、`go_chi_context.py:19`、`go_chi_runtime.py:231` |
| 请求上限 50/6/2 | guard、journal、entry 各自计算 |
| 时间策略 | `go_chi_policy.py` + 手抄的 `profiles/go-chi-entry.json` |
| 角色/端口/白名单 | `go_chi_mcp.py`、`go_chi_delivery.py`、`role_operator.py` 各维护 |

建议：`limits.py` 单一来源；profile 改为生成或只校验子集。影响 identity：是。

## 2. 路径与白名单策略重复

`_check_components` 在 `evaluation_bundle.py:81` 与 `go_chi_bundle.py:105` 各一份；`workspace_path` 在 `go_chi_resources.py:16`、`go_chi_tools.py:94/115`、`live_development.py:1729` 各一版；禁止目录集合在多处复制。
建议：`paths.py` 统一。影响 identity：是。

## 3. 错误码坍缩

`go_chi_guard.py:173` 把 `ContractFailure` 一律映射为 `chi_tool_batch_invalid`；真实排查只能靠重放 wire evidence。
建议：对外码不变，diagnostic 增加 `cause` 子字段（如 `unknown_field:index`）。影响 identity：是（证据 schema）。

## 4. Journal 三合一

`go_chi_journal.py` 1090 行：持久化 + 状态合法性 + CLI。`_validate` 数百行 if，新增字段需同时改 journal/inspect/entry。
建议：状态校验抽成纯函数模块。赛后做。

## 5. 双轨遗留代码

`live_development.py`（2718 行）、`model_runner_adapter.py`（1205 行）、`run_baseline.py`、`c_run_control.py` 属旧开发路径；Go CHI 只用其中很小部分。导致打包边界难判断（`run_baseline` 潜在 ImportError）。
建议：赛后按“进包 / 开发工具 / 历史存档”分目录；赛前只加静态 import 检查测试。

## 6. 测试策略

既有问题：`patch.object(entry, "_identity")` 掩盖真实配置漂移；超时断言曾写死 60/360。
建议：配置等价性测试、guard/contract 表驱动用例、评审检查项“是否打桩核心校验”。无 identity 影响。

## 7. 资源 manifest 手工维护

每题 11 项 manifest 手写，易漏 `visibility`（本轮 t027/t030 各写错一次）。
建议：`make_role_manifest.py` 自动扫描/分类/哈希并跑 preflight。无 identity 影响。

## 8. 可观测性

每次分析都临时写 Python 读 journal。建议加只读 `summary --run`（进包，影响 identity）。

## 9. 身份与策略耦合

`TIME_POLICY` 进入 identity，调超时也要新 release + 新 B + 新 state（本轮已发生）。
建议：把“行为身份”（代码/提示/工具/上限）与“运行策略”（超时/窗口）分开版本化。架构级取舍，赛后评估。

## 10. 不建议现在做

大文件拆分、全面类型化、重写 guard/journal。它们是失败语义的核心，重写等于丢弃已验证行为。

## 11. 优先级

- 赛前（有 identity 影响）：`limits.py`、`paths.py`、诊断 `cause`。
- 赛前（无 identity 影响）：manifest 生成器、静态 import 检查、表驱动契约测试。
- 赛后：journal 拆分、双轨分目录、身份/策略解耦。
