# 提案：按类处理故障（输出契约 / 业务前置 / 连接前重试）

## 为什么

九题 BDE 运行暴露的失败不是单题问题，而是几类反复出现的故障：

- 输出契约：`name:null`、arguments JSON 非法、schema 非法、未知工具/字段；
- 业务/工具前置：CM case root 未创建导致 `local-fs-write` 失败；
- 基础设施：连接前失败、read 超时、429/5xx、未知副作用。

继续“测一题修一题”会把同类问题拆成多个补丁，且难以复审。需要按类定义处理边界、恢复上限和验收。

## 范围

1. **输出契约层**：response shape、tool name、call id、arguments JSON、arguments schema 的统一校验与有界重生成。
2. **业务/工具前置条件层**：状态/业务拒绝、CM case root bootstrap、文件写失败、可确定修正 vs 业务失败。
3. **基础设施层**：只对 connect 前失败做有界重试；read 超时/429/5xx/工具写继续保守停止。

## 非目标

- 不处理 reasoning/输出预算（t022）；另立设计。
- 不改变输入 context budget（1.5M 实验）。
- 不判断临床正确性、官方得分或语义完成。
- 不自动重试业务写、工具调用或未知副作用。
- 不授权真实模型/B/C/Trial/judge/发布。

## 状态

设计文档，未实现、未运行。实现前先独立复审本设计；通过后按 `tasks.md` 分阶段实施。
