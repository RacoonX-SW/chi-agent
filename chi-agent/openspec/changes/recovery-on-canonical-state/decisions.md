# recovery-on-canonical-state 施工决定（Q1–Q6）

日期：2026-11-08。范围：P1 + P2 离线实现；P3 不做。不跑真实 B/C、judge/Trial、发布。

## Q1 partial 冻结范围

冻结整个 L1 视图：`messages`（含锚点、占位符）、预算 feedback 后缀、工具定义、`pressure`、`anchor_sha256`、`view_sha256`。continution 必须完全匹配 permit 的视图 hash；不得重新投影、重算压力或替换锚点。

## Q2 regenerate 的视图

允许从 L0 重新派生一个**新的**视图，使用 regenerate 专用策略：

- `projection_rule = "chi-context-projection-regenerate-v1"`
- `keep_recent_batches = 1`（父请求默认 2）
- `project_results = True`（即使父请求低压力也压缩旧结果）

必须记录新的 `view_sha256`、`source_sha256`、`anchor_sha256`、`pressure`、`parent_view_sha256` 和投影规则；不重放已执行 mutation。新视图与父视图 hash 必须不同（有旧结果可压缩时）。

## Q3 permit v1 兼容

旧 `chi-recovery-permit-v1` 继续只读：校验仍按 v1 字段和旧 `derive_view` 语义，不迁移、不改写。只有新 `recovery_view_policy=canonical-v1` 的 v3 run 签发 v2 permit；v2/v3-without-recovery 继续签发/读取 v1。

## Q4 组合开关

launch 字段 `recovery_view_policy="canonical-v1"`，默认缺省关闭。只有显式设置时，entry/journal/guard 才允许 `context_policy=chi-context-v3` + `output_recovery`；否则仍拒绝 `chi_context_policy_incompatible`。input_summary 仍不支持。

## Q5 partial 视图不一致

默认停止（fail closed），不自动改为 regenerate。只有显式策略才允许 regenerate；当前没有自动降级开关。

## Q6 reader 复算

reader 对 v2 视图身份复算 `view_sha256 = canonical_sha(request_body)` 并核对 `history_length`、anchor 字段、投影规则；源历史 hash 只比对记录。由于 journal 不保存完整 source body，reader 不能从 source 重放投影；源侧复算由 guard 在发送前完成并记录。v1 permit 仍只按旧字段读取。

## 实现边界

- P1：permit v2 字段、journal view identity、v1 兼容；不打开组合。
- P2：显式开关、partial 冻结、regenerate 从 L0 重放、新错误码、文档。
- 不修改 240s、默认 `main_max_tokens=8192`、REQUIRED 表。
