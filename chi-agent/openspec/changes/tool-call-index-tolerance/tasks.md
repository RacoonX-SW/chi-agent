# 工具调用索引兼容执行清单

当前：实现与离线定向测试完成；真实运行未重跑，等待复审。

## 实现

- [x] `_canonical_calls()`：允许可选 `index`、校验非负 `int`、剥离后存储。
- [x] `accept_batch()` 存储规范化消息，其余键仍严格。
- [x] `validate_history()` 用 `_same_assistant()` 容忍回放索引。
- [x] 失败路径保持 `tool_batch_invalid` / `request_history_invalid` 与原子性。

## 验证

- [x] 新增 4 个定向 tests（contract 3 + guard 1）全通过。
- [x] 真实证据回归：payer 002 `018-response.json` 修改后 `ACCEPTED raw`。
- [x] Docker 全量：470 tests，2 个既有环境错误（缺 `anthropic`），8 skipped。
- [ ] 外部 Gemini 复审固定候选。
- [ ] PR 审查/合并。

## 明确不做

- [x] 不重试 payer 002、不改 `state-v2`/`state-v3`、不换账根。
- [x] 不放宽未知字段、参数 schema、调用数量或顺序。
- [x] 不改变真实运行审批、额度或官方判分。
