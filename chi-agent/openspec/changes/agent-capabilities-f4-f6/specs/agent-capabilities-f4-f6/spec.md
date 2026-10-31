# F4–F6 行为契约

本契约定义可验收的离线行为，不授予真实调用、官方判分或临床评审权限。接口细节见 [design](../../design.md)，实际状态见 [REVIEW_STATE](../../../../../reviews/REVIEW_STATE.md)。

## 需求：上下文必须可测量且在发送前有界

### 场景：记录输入构成

每次通过 contract 的请求，在 `journal.reserve()` 前记录 system/instruction/tools/history/tool_result/reasoning 的字符数、总字节、估计 token、输出上限和 purpose。记录不得包含消息正文。

### 场景：超过预算

`total_chars` 超过配置上限，或 `estimated_tokens + output_reserve` 超过估计 token 上限时，返回 `chi_context_budget_exceeded`，不写请求预留、不发送。预算配置非法返回 `chi_context_budget_invalid`；记录文件写失败返回 `chi_context_persistence_failed`。

### 场景：自动压缩不可行

当前 `ToolContract.validate_history()` 要求完整已接受工具批次逐项匹配。未取得新 contract 版本、reasoning/tool 关联规则、替换 hash、旧检查点防覆盖和真实 SDK/API 证据前，不得删除/重写历史来“压缩”；必须明确“未采用自动压缩”及已交付的测量/预算/组织/停止能力。

## 需求：完成声明必须与公开效果分开

### 场景：无写操作的完成

无 mutation 且无业务状态时，完成报告为 `not_applicable / not_observed`；claim 仍是模型声明，不写成业务成功。

### 场景：写后已回读

存在 mutation，且 `latest_business_status.source_seq` 晚于最后一次 mutation 时，报告为 `mechanical_pass / observed`；这仅证明机械/来源边界，不是临床或官方 verdict。

### 场景：写后未回读

存在 mutation 但无更晚状态回读时，报告为 `blocked / not_verified`，claim 返回 `completion_readback_required:<call_id>`。

### 场景：未知写或 claim 违规

open unknown → `blocked / unknown`；claim 后写 → `blocked / violation`。报告不得把未知写成成功或失败。

## 需求：未知写只允许只读查证

### 场景：写结果未知

MCP mutation dispatch 异常（非取消、非 fatal）返回 `UNKNOWN_WRITE_EFFECT: <code>`；journal 记 failed，state 登记 open unknown，不自动重发。

### 场景：未知期间再写

存在 open unknown 时，任何 mutation 返回 `REFUSED: unknown_write_effect_pending:<id>`；不得用旧状态证明未执行或直接重写。

### 场景：后续只读查证

模型只能在同目标、更晚的只读 observation 后通过 `resolve_unknown` 解决；旧状态不自动证明未执行。未解决就结束 → `chi_unknown_write_effect`，run incomplete。

## 需求：停滞识别不自动重试

### 场景：重复读

连续第 3 次相同 `tool+kind+arguments` 读，结果追加 `STAGNATION` 警告；第 5 次返回 `REFUSED: stagnation_detected`。模型应改计划或如实结束。

### 场景：重复写

连续第 2 次相同写返回 `REFUSED: repeated_write_forbidden`，不调用服务器。不得自动 HTTP/SDK/MCP 重试、后台轮询或换模型。

## 需求：旧行为与边界不被扩大

### 场景：关闭能力

`capabilities=None` 保留旧工具集、旧 claim、无状态/上下文工具行为。

### 场景：真实运行

本契约只覆盖合成 SDK/MCP 与 Docker 离线测试；真实 tokenizer、服务端预算、真实任务、官方分数和临床正确性未验证。正式运行仍需新 bundle manifest、合规 B 凭据和配额校验。
