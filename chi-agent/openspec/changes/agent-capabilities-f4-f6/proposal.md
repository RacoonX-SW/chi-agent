# F4–F6：上下文预算、完成核验与失败处理

建立：2026-11-01。基于已合并的 F0–F3（`066c9ae`）。本变更只做 F4–F6 的离线能力；真实模型、真实任务、官方判分和临床评审仍不在范围内。状态与授权只查 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。

## 范围

- **F4**：输入构成测量、字符/字节/估计 token 分列、发送前预算停止、`context.jsonl` 记录；组织继续复用 F1 状态摘要和 F3 有界检索。自动历史压缩做可行性判断，当前**不采用**并写明原因。
- **F5**：结束前机械完成核验 `chi-completion-v1`，区分 claim、公开效果已观察、未验证、unknown、claim 违规；`local-completion-check` 只报告，不代替 claim。
- **F6**：写效果未知的保守继续（只读查证、禁止重发写）、未知未解决时 run 结束为 incomplete、重复读警告/阻断、重复写阻断；不增加自动 HTTP/SDK 重试、后台轮询或换模型。

## 非范围

- 不重写历史、不删除消息、不做自动摘要/压缩；当前 `ToolContract.validate_history()` 要求完整已接受工具批次，任何历史重写都需要新契约版本和真实 SDK/API 证据。
- 不新增真实请求、purpose、额度、judge 或临床评审。
- 不改变官方系统提示、vendor、评分器、MCP 目录或账目 schema。
- 不承诺跨进程崩溃续跑或跨主机幂等。

## 与 F0–F3 的关系

F4 使用 F1 的状态摘要和 F3 的片段回读减少重复材料；F5 使用 F1 的 target/status/unknown；F6 使用 F1 的未知写和调用历史。`capabilities` 继续使用 `f0-f3-v1` 作为内部能力信封（为身份兼容保留名称），实际行为已扩展到 F0–F6；`capabilities=None` 仍保留旧工具集/旧 claim。
