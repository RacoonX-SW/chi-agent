# 故障处理分层任务清单

状态：设计文档，未实现、未运行。下列任务全部未开始；真实模型/B/C/Trial/judge/发布不在本变更内。

## 1. 输出契约层

- [ ] 定义统一失败类：`response_shape`、`arguments_json`、`tool_unknown`、`call_shape`、`call_id`、`arguments_schema`。
- [ ] 在 guard/contract 中实现“整批原子 REFUSED”，JSON 语法/schema/shape 失败均不执行任何 call。
- [ ] 实现短反馈格式：工具名、字段/路径、缺失字段/允许字段；不含参数值/PHI/完整 schema。
- [ ] 实现每类 2 次、每 run 3 次的恢复上限；同错重复提前停止；run log 记录计数。
- [ ] 允许 recovery 形状中的 `name: string|null`，避免 length 响应被误判 `chi_response_invalid`。
- [ ] 保持默认/合法批次行为不变；补 off/合法路径回归测试。
- [ ] 补单元/合成 runtime 测试：JSON 非法、缺字段、未知字段、`name:null`、重复上限、反馈安全。

## 2. 业务/工具前置条件层

- [ ] 定义 `local-fs-write` 的 case root bootstrap 条件：case 已观察/绑定 + allowlist + 非 symlink/隐藏/fixture。
- [ ] 在条件满足时创建缺失的 case 根/角色目录（0700），再写文件。
- [ ] 未观察/越界/跨 case/symlink 仍拒绝；不创建目录；错误信息可操作。
- [ ] 保持 provider binding/payer 路径行为不变；补回归测试。
- [ ] 确认 completion `completion_file_write_failed` 仍阻断 claim；同路径成功写可修复。
- [ ] 补 CM/provider/payer 文件写测试。

## 3. 基础设施层

- [ ] 定义请求阶段：connect / send / read；只在 connect 前失败重试。
- [ ] 实现有界 connect 重试（次数/退避/总预算可配置），不产生 usage/pending；每次 attempt 可审计。
- [ ] read 超时/断连、429/5xx、工具/业务写不自动重试；保持 pending/unknown。
- [ ] 默认关闭连接前重试；单独开关/配置；不改变现有零自动重试默认。
- [ ] 补测试：connect 失败重试成功、最终失败、read 超时不重试、429 不重试、工具写不重试。

## 4. 文档与验收

- [ ] 更新 `REVIEW_STATE.md` 短状态与报告链接。
- [ ] 写阶段报告：实现范围、证据、失败、未验证项、独立复审重点。
- [ ] Docker 定向/全量测试；既有 3 个 import error 单列。
- [ ] Gemini 独立复审；0 Blocker 后再决定是否合并/重建 bundle。
- [ ] 不授权真实模型/B/C/Trial/judge/发布；不自动重跑九题。

## 5. 待讨论（未决）

- [ ] 每类/每 run 恢复上限是否 2/3。
- [ ] JSON 语法错误的 REFUSED 如何穿过 SDK/guard/contract/wrapper。
- [ ] CM case root 创建是否需要额外 state 绑定条件。
- [ ] connect 重试次数/退避/开关；是否只用于 C。
- [ ] 429/5xx 是否另立预算/对账设计。
- [ ] reasoning/output 预算（t022）另立设计。
