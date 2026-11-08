# source-evidence-replay 收口审计矩阵

日期：2026-11-08
分支：`deepseek/source-evidence-replay`
候选 HEAD：`7a585f8`
基线：`14a7acd0c4798529f64d99836cc6dfbb6dc94452`
范围：离线审计；未跑真实 B/C、judge/Trial、发布。

## 结论

**矩阵中无 P1。** 建议冻结当前候选，不再扩展功能；剩余项均为 P2（测试缺口、存储治理、文档/身份/真实运行限制）。

## 验证基线

- 全量 `unittest discover`：**754 tests / 23 skipped / 3 个既有 import error**。
- 既有 recovery pytest：**48 passed**。
- 定向：`test_recovery_view_binding`、`test_context_projection_guard`、`test_go_chi_diagnostics`、`test_context_error_run_log`：**24 passed**。

3 个既有 import error：

- `test_dev_patient_adapter`：缺 `anthropic`
- `test_dev_patient_network`：缺 `anthropic`
- `test_role_payer_projection`：缺 `docker.types`

## 矩阵

| 维度 | 单元 | 结果 | 证据 |
| --- | --- | --- | --- |
| 上下文策略 | v1/v2 recovery | 通过 | 48 pytest；v1 分支未改 |
| 上下文策略 | v3 无 recovery | 通过 | `test_context_projection_guard`、`test_intent_anchor`、全量 |
| 上下文策略 | v3 + recovery 未显式启用 | 通过（拒绝） | `test_recovery_view_binding` F3、`test_context_policy_compat` |
| 上下文策略 | v3 + recovery `canonical-v1` | 通过 | `test_recovery_view_binding` |
| 恢复模式 | partial | 通过 | partial 冻结、父/新 hash 相等、inspect |
| 恢复模式 | regenerate | 通过 | 新视图、`keep_recent_batches=1`、`project_results=True`、父/新 hash 不同、inspect |
| 恢复上限 | per-chain / per-run | 通过 | 48 pytest 的 limits/duplicate 用例 |
| 工具事件 | returned | 通过 | main replay、48 pytest |
| 工具事件 | returned_error | 代码路径覆盖；无独立 v3 重放测试 | **P2 测试缺口** |
| 工具事件 | refused | 通过 | `test_replay_includes_refused_and_failed_tool_events` |
| 工具事件 | failed | 通过 | 同上 |
| source evidence | 新 v3 main 写入 | 通过 | source 文件、`source_evidence_sha256` |
| source evidence | 新 v3 main 缺失 | 通过（拒绝） | `chi_source_evidence_missing` |
| source evidence | continuation 指向无 source 的 main | 通过（拒绝） | `chi_source_evidence_missing` |
| source evidence | 旧 v3 无 policy / 无 source | 通过（只读兼容） | `view_identity` legacy、source_policy false |
| source evidence | 篡改 source body | 通过（拒绝） | `chi_view_source_mismatch` |
| source evidence | redacted tool evidence | 代码 fail closed；无独立测试 | **P2 测试缺口** |
| permit | v1 | 通过 | 48 pytest |
| permit | v2 partial | 通过 | 重新派生视图 + 冻结校验 |
| permit | v2 regenerate | 通过 | parent/new view hash、`projection_rule` |
| permit | 缺 hash/字段 | 通过（拒绝） | `test_recovery_view_binding` |
| view_identity | claimed 存在/缺失 | 通过 | 新证据写入；legacy 缺失读取 |
| view_identity | parent_round → source | 通过 | source policy 检查 |
| view_identity | projection_rule | 通过（允许两种规则） | main/continuation/regenerate |
| reader | main replay | 通过 | source + tool evidence + anchor |
| reader | regenerate replay | 通过 | source + aggressive projection + derive_view |
| reader | partial | 通过 | 父 wire derive_view + source hash |
| 预算/装配 | 50% 投影阈值 | 通过 | `test_context_projection_guard` |
| 预算/装配 | 8K/32KB、JSON 合法 | 通过 | `test_tool_truncation` |
| 预算/装配 | `full_results` 64MB | 通过 | `test_context_projection_guard` |
| 预算/装配 | reducer `result/data/records` | 通过（result 有测试） | `test_tool_truncation`；其余为同实现 |
| 完成门禁 | 无 claim / 失败终态 / 缺回读 | 通过 | `test_completion_gate` |
| 检索 L0 | role alias / cache / next_offset | 通过 | `test_retrieval_l0` |
| 诊断 | 新错误码 / run_log | 通过 | `test_go_chi_diagnostics`、`test_context_error_run_log` |
| 旧证据 | v1/v2 旧 run | 通过 | 48 pytest + 全量 |

## 剩余 P2

1. **source 存储治理**：source 文件先写、entry 后写，失败可能留下孤儿文件；source 总存储未设上限。
2. **测试缺口**：`returned_error` 的 v3 source 重放、redacted tool evidence 的 fail-closed、v3 mutation replay 没有独立用例；目前依赖共享代码路径和 v1 回归。
3. **字段语义**：`history_length` 实际是视图长度，不是源历史长度；`_active_permit["parent_view_sha256"]` 是未使用字段。
4. **mode/rule 交叉校验**：`view_identity.projection_rule` 允许两种规则，但未按 `recovery_mode` 强制 main 只能 v1、continuation regenerate 只能 regenerate。
5. **真实运行限制**：`messages[2]` 锚点与真实 SDK/DeepSeek 兼容性、真实 source 重放收益未验证；未重建 bundle、未取得新 B。
6. **范围外**：P3、RAG/L1/L2、任务级 resume、reasoning 压缩未实现。

## 冻结建议

- 当前 HEAD `7a585f8` 可冻结为候选。
- 不再为 P2 项扩功能；如后续有真实运行证据，再单独开小变更。
- 用户/主代理决定是否合并；**不 auto-merge**。
