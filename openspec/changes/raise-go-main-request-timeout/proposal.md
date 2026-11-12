# 延长 Go 主请求读取窗口

## Why

payer t022 的 OpenCode Go 请求在客户端等待 240 秒时终止，服务端在 253.446 秒完成。此次开发评测在该轮后暂停。新批次需要接纳这一量级的慢响应，并让单轮超时成为有证据的评测结果。

## What Changes

- Go 主请求读取上限设为 300 秒，整次 I/O 上限设为 360 秒。源码和导出配置共同确定运行身份。
- 使用同一新候选重跑九个公开开发题，每题三次。每个槽位从独立世界和账本开始。已发出模型请求后超时的轮次计失败，调度继续下一槽位。
- 批次报告保存每轮身份、耗时、判分与账目。预先固定 27 个槽位，按该分母计算本地端到端指标。

## Capabilities

### New Capabilities

- `go-main-request-timing` 主模型调用的有界读取和总 I/O 行为。

### Modified Capabilities

## Impact

影响 `chi_agent.runtime_policy`、`profiles/go-chi-entry.json`、对应策略断言及 Go 导出包身份。独立轮次的调度和汇总由本地开发评测负责。

## 审批记录

用户在本会话批准读取 300 秒、总 I/O 360 秒的建议，随后明确要求改完重跑并在单轮超时后跑完所有轮次。公开开发评测继续使用已选的 OpenCode Go DeepSeek V4.1 Flash。
