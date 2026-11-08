# recovery-on-canonical-state 阶段报告

日期：2026-11-08
分支：`deepseek/recovery-canonical-state`
基线：`670c5984c468779b9da8a996ee03dba2e5a503b9`
范围：P1 + P2 离线实现；**未跑真实 B/C、judge、Trial、发布**。

## 结论

- permit v2 记录 `source_sha256`、`view_sha256`、`anchor_sha256`、`history_length`、`frozen_view`、`projection_rule`、`pressure`。
- journal 请求条目记录 `view_identity`；reader 复算 `view_sha256` 并核对 anchor/history。
- v3 + `output_recovery` 只有显式 `recovery_view_policy=canonical-v1` 才允许；默认仍拒绝。
- partial 冻结视图；regenerate 从 L0/冻结投影重新派生并记录新 hash；mutation 不重放。
- 旧 v1 permit、v2 行为、v3-without-recovery 行为保持不变。

## 实际改动

| 模块 | 改动 |
| --- | --- |
| `go_chi_recovery.py` | permit v2 校验；`derive_view` 支持 `messages[2]` 锚点；v1 分支保留 |
| `go_chi_journal.py` | `issue_recovery` 签发 v2；请求条目 `view_identity`；inspect 复算 view/anchor/history；旧 v1 兼容 |
| `go_chi_guard.py` | v3 视图身份；组合策略；partial 冻结；regenerate 记录新视图；continuation 用 source body 校验、wire 视图 hash 冻结 |
| `go_chi_entry.py` | 新增 `--recovery-view-policy canonical-v1`，默认关闭 |
| `role_operator.py` | config 支持 `recovery_view_policy`，要求同时有 `output_recovery` |
| `go_chi_diagnostics.py` | 新增 `chi_recovery_view_mismatch`、`chi_recovery_policy_incompatible` 及 cause |

## 测试

新增 `tests/test_recovery_view_binding.py`：

- partial v2 permit 字段、冻结视图、continuation view hash；
- regenerate 新视图、`frozen_view=false`；
- permit 缺字段拒绝；
- anchor hash 不符拒绝；
- v3 + recovery 未启用策略拒绝。

既有：

- `tests.test_go_chi_recovery_journal` + `tests.test_go_chi_guard_recovery`：48 passed（pytest）。
- 全量 `unittest discover`：**748 tests / 23 skipped / 3 个既有 import error**。
- `role_operator` 离线容器：11 tests OK。

## 旧 v1 兼容

- `chi-recovery-permit-v1` 仍走原字段和原 `derive_view` 语义；不迁移、不改写。
- v2/v3-without-recovery 请求条目没有 `view_identity` 时按旧 schema 读取。
- 旧 v1 permit 的 reader 回归通过。

## 组合开关

- launch 字段：`recovery_view_policy="canonical-v1"`。
- 默认缺省：拒绝 `chi_context_policy_incompatible`。
- 只有在 `output_recovery` 存在且 `input_summary` 不存在时允许组合。
- 5 题 config 若要启用：保留 `output_recovery` 并加入 `recovery_view_policy: canonical-v1`；只验证 v3 基础链路则移除 recovery。

## 残余风险

- `messages[2]` 锚点与真实 SDK/DeepSeek 的兼容性仍未实测；需要真实最小 length + continuation 验证。
- regenerate 从 L0 source body 按当前压力重新投影并记录新视图；不重放 mutation。
- reader 不复算 source body 的投影（journal 不保存完整 source）；source hash 只比对记录，view hash 复算。
- 未实现 P3（LLM 摘要 + recovery）、任务级 resume、RAG/L1/L2、reasoning 压缩。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表。
- 未重建 bundle、未取得新 B。

## 下一步

1. 独立复审差异与离线证据。
2. 重建 bundle + 新 B；真实最小验证另行授权。
3. 用户审核 PR 后决定合并；不 auto-merge。
