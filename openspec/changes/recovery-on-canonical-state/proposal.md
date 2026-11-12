# 恢复基于规范状态（recovery-on-canonical-state）

状态：**设计草案（2026-11-08），未实现、未运行真实 B/C。** 真实模型/judge/Trial/发布不在本变更内。当前 v3 与 `output_recovery`/`input_summary` 仍显式互斥；本变更只定义解除互斥的分层协议。

## 1. 为什么

- `context-engineering` v3 与 `output_recovery` 目前互斥：entry、journal、guard 以 `chi_context_policy_incompatible` 拒绝组合。
- 现有 5 个失败题 config 都开着 `output_recovery`；要么关掉恢复，要么实现组合。
- 两者不是天然冲突：上下文压缩管**轮次之间**，输出恢复管**单次生成之内**；冲突只发生在请求体被投影改写的边界。

## 2. 做什么

按四层分离：

| 层 | 内容 | 时机 |
| --- | --- | --- |
| L0 规范状态 | SDK 已接受历史、完整工具结果、TaskState、journal | 正常执行时更新 |
| L1 视图派生 | 从 L0 确定性生成 wire（占位符、reducer、锚点、预算） | **只在轮次边界** |
| L2 尝试 | 一次模型调用：source/view/anchor hash、purpose | 每次请求 |
| L3 恢复 | `partial` 或 `regenerate`；绑定 L2 hash | `finish_reason=length` 后 |

五条规则：

1. 压缩只在轮次边界；length 响应后、continuation 前不重新投影。
2. `partial` 冻结视图：复用超时那次的 `view_sha256`、锚点、预算。
3. `regenerate` 从 L0 重放：丢弃不完整输出，重新派生视图，记录新 view hash。
4. 视图变化就不能 `partial`；只能 `regenerate`。
5. mutation 永不重放；只重生成未执行的工具批次。

## 3. 不做什么

- 不做 LLM 摘要 + recovery 的组合（P3，另行评估）；
- 不做向量 RAG/L1/L2；
- 不做任务级 resume；
- 不跑真实 B/C、judge/Trial、发布；
- 不改变 v2 与 v3-without-recovery 的现有行为。

## 4. 成功标准

- 离线测试覆盖：partial 冻结、regenerate 重放、视图不匹配拒绝、mutation 不重放、hash 审计；
- v3 + recovery 可以同时启用，且 continuation 不因投影漂移失败；
- journal/reader 能复算 source/view/anchor hash；
- 真实最小验证（一次 length + continuation）另行授权。

## 5. 依赖

- 已合并的 `context-engineering`（PR79/PR80）；
- `full_results` 与确定性投影；
- 新 bundle + 新 B；
- 真实 SDK/DeepSeek 对 `messages[2]` 锚点的兼容性验证。
