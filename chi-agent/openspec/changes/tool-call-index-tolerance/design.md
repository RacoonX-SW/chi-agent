# 设计：工具调用位置索引兼容

## 契约面

`ToolContract` 只接受规范化后的 assistant 消息：

1. 每个 tool_call 必须是对象；允许键为 `id`、`type`、`function`、可选 `index`。
2. `index` 存在时必须是 `int` 且 `>= 0`（`bool` 不算）。
3. 其他任何键仍视为伪造/漂移，整批判失败，且不提交任何记录。
4. 规范化后的调用只保留 `id`/`type`/`function`，与已记录批次一起存储。

## 历史重放

`validate_history()` 原来用 `_same()` 对 assistant 消息做全等比较。现在对带 `tool_calls` 的 assistant 消息先用同一规范化函数比较：

- SDK 回放时保留 `index` → 通过；
- SDK 回放时丢弃 `index` → 通过；
- 其他字段（`content`、`reasoning_content`、`tool_call_id`、结果内容）仍逐字节比较。

规范化失败（未知字段、坏 index）时历史比较直接失败，错误码仍是 `request_history_invalid`。

## 为什么不放宽全部校验

未知字段可能是模型注入、端点 drift 或伪造证据。只承认一个已知、无调度语义的位置字段，比整体容忍未知键更安全；同时保留“整批提交前校验、失败不落盘”的原子性。

## 验证

- 单元：带 `index` 的调用被接受且存储时剥离；回放带 `index` 通过；未知字段、`-1`、`"0"`、`0.0`、`true`、`null` 被拒。
- guard 端到端：第 1 轮响应带 `index` → 成功结算；第 2 轮历史带 `index` → 请求校验通过并结算。
- 真实证据回归：`018-response.json` 原样通过 accept_batch。
