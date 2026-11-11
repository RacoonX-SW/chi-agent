# 工具调用位置索引兼容（`index` 字段）

建立：2026-11-01。基于 `origin/main` `dac6080`。本变更只修离线协议校验；不重跑真实运行、不改账目/身份/提示。

## 为什么需要

真实 external 批次 payer 002（`real-ext-payer-002`）在 18 轮被 `chi_tool_batch_invalid` 终止，全部请求已结算、无 pending。事后离线复现确认根因不是模型选错阶段工具：

- 第 18 轮原始响应的 tool_call 多了 `"index": 0`，是 OpenAI 兼容端点偶发带上的位置字段；
- `go_chi_contract.ToolContract.accept_batch` 用 `set(call) != {"id","type","function"}` 做全等判断，直接判整轮失败；
- 同一响应把 `index` 去掉后，`determination__get_summary({case_id})` 通过校验；
- 前 17 轮响应恰好没有该字段，因此表现为“运行中途随机死亡”。

`index` 在非流式 tool_call 中是合法的位置提示，不带调度语义。把整轮判死会浪费真实请求与预算，也掩盖真正的模型/业务问题。

## 范围

- `go_chi_contract._canonical_calls()`：允许可选 `index`，校验为非负 `int`，提交前从调用中剥离；其他未知键仍然失败。
- `accept_batch()` 存储规范化后的 assistant 消息，保持历史可重放。
- `validate_history()` 用 `_same_assistant()` 比较，允许回放消息带可选 `index`（SDK 是否保留该字段不影响校验）。
- 失败路径保持不变：非法 index 类型/负值、未知字段、重复 id、schema 不合法、参数不是 JSON 仍返回 `tool_batch_invalid`。

## 非范围

- 不改变工具定义、阶段可见性、MCP 行为或 guard 的其他校验。
- 不改 `opencode_go_provider.GoGuard`：该路径只用于离线 probe，历史消息由 `b_model_adapter` 在本地规范构造，不会出现端点回传的 `index`。
- 不放宽参数 schema、调用数量、顺序或结果回放要求。
- 不重试 payer 002、不修改 `state-v2`/`state-v3`、不使用旧账根。
- 不改变真实运行审批或额度。

## 证据

- `runs/real-external/state-v3/wire-evidence/real-ext-payer-002/018-response.json`（真实响应，含 `index`）
- `runs/real-external/state-v3/wire-evidence/real-ext-payer-002/018-request.json`（51 个工具定义）
- 离线复现：修改前 `REJECTED raw` / `ACCEPTED without index`；修改后 `ACCEPTED raw`。
