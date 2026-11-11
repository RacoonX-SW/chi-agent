# F4–F6 接口与行为冻结（待外部 Gemini 审查）

状态：**离线实现候选，已自测，待独立复审**。基线 `066c9ae`，实现候选 `efc90190ff3b3ce2b313f119aa2c2abd7471366a`。本页冻结接口；实现证据见 [阶段报告](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/f4-f6-context-completion-review.md)。

## 1. 不变项

- 不改官方 `SYSTEM_PROMPT`、`ToolContract.validate_history()` 的完整批次要求、账目 schema、vendor、评分器或 MCP 目录。
- 不新增真实请求、模型、purpose、额度、judge 或临床评审。
- `capabilities=None` 保留旧工具集和旧 claim；`f0-f3-v1` 是内部能力信封名称，行为已扩展到 F0–F6。
- 不自动重试、不后台轮询、不换模型、不重建账根。

## 2. F4：输入测量与预算

### 2.1 测量

`go_chi_context.measure_request(body)` 在请求已通过 contract 校验后、`journal.reserve()` 之前测量：

| 字段 | 含义 |
| --- | --- |
| `system_chars` / `instruction_chars` | 系统提示/instruction 字符数 |
| `tools_chars` | 工具定义 JSON 字符数 |
| `history_chars` | 第 3 条起的消息内容字符数 |
| `tool_result_chars` | 其中 `role=tool` 的内容 |
| `reasoning_chars` | `reasoning_content` 字符数 |
| `total_chars` / `total_bytes` | 组成合计（字符/UTF-8 字节） |
| `estimated_tokens` | `ceil(total_chars/4)`，明确是估计，不是 tokenizer |
| `max_tokens` | 本次输出上限 |
| `token_estimate` | 固定 `chars_div_4_not_tokenizer` |

不保存消息正文，只保存计数；正文仍在 journal/日志。

### 2.2 预算与记录

- 默认预算：`chi-context-budget-v1`，`max_chars=3_500_000`、`max_estimated_tokens=1_000_000`、`output_reserve_tokens=8192`，`basis` 标 `configured_unverified`。这是保守字符估计，不是实测 tokenizer 或服务端硬上限。
- 发送前检查：`total_chars > max_chars` 或 `estimated_tokens + output_reserve > max_estimated_tokens` → `chi_context_budget_exceeded`，在 `journal.reserve()` 前停止，不产生请求。
- 预算字段非法 → `chi_context_budget_invalid`；`context.jsonl` 写入失败 → `chi_context_persistence_failed`。
- 每次通过 contract 的请求写一行 `logs/context.jsonl`，含 `purpose=main|confirmation` 和上述计数；不写正文。
- `run_log.txt` 增加 `context_budget`、`context_requests`、`context_max_chars`、`context_max_estimated_tokens`、`context_prompt_tokens`（服务返回的已结算输入 token 合计）。

### 2.3 组织与压缩可行性

- 组织：继续用 F1 的 `local-task-state` 摘要和 F3 的片段回读，减少“整份资料重复塞入”；状态本身有 64 KiB/条数上限。
- **自动压缩当前不采用**：`ToolContract.validate_history()` 要求完整已接受工具批次逐项匹配；要合法换历史，需要新的 contract 版本、reasoning/tool 关联重放规则、替换映射/hash、旧检查点防覆盖，以及真实 SDK/DeepSeek 路径证据。当前没有这些证据，强行删消息会绕过原校验。
- 因此 F4 交付的是：可测输入构成、发送前预算停止、状态/片段组织、明确“不采用自动压缩”的决策和原因；不是“上下文压缩已完成”。

## 3. F5：完成核验

`TaskState.completion_report()` 返回 `chi-completion-v1`：

```json
{
  "schema": "chi-completion-v1",
  "verification": "mechanical_pass|not_applicable|blocked",
  "business_effect": "observed|not_observed|not_verified|unknown|violation",
  "reason": null,
  "target": {"case_id": "...", "patient_id": null},
  "claim": null,
  "latest_business_status": null,
  "last_mutation_call_id": null,
  "open_unknowns": [],
  "claim_violation": false,
  "stagnation": null,
  "note": "mechanical/source check only; not a clinical or official verdict"
}
```

规则：

- 无 mutation、无 status：`not_applicable / not_observed`。
- 有 status、无未决写：`mechanical_pass / observed`。
- 有写但无更晚回读：`blocked / not_verified`，reason `completion_readback_required:<call_id>`。
- open unknown：`blocked / unknown`。
- claim 后写违规：`blocked / violation`。
- `local-completion-check` 只返回报告，不替代 `local-claim_done`；run_log 保存同一报告。
- 仍区分：claim、公开效果已观察、确定性检查、内容未评、官方未评；报告不是临床或官方 verdict。

## 4. F6：未知写、停滞与有限重规划

### 4.1 未知写

- 只对 MCP mutation 的 dispatch 异常（非取消、非 fatal）返回工具结果 `UNKNOWN_WRITE_EFFECT: <code>`；不自动重发。
- journal 记 `failed`，state 登记 open unknown（call_id/scope/seq）。
- open unknown 存在时，任何 mutation 被拒绝：`REFUSED: unknown_write_effect_pending:<id>`。
- 模型只能用同目标、更晚的只读 observation + `local-state-update` 的 `resolve_unknown` 解决；旧状态不自动证明未执行。
- 运行结束仍有 open unknown → `chi_unknown_write_effect`，run 为 incomplete；不把未知写成 0/失败/成功。
- 本地 `local-fs-write/edit` 异常仍按原逻辑失败，不转成可继续的 unknown（保守；文件写入的副作用边界更弱）。

### 4.2 停滞

- 指纹 = `tool + kind + arguments` 的 SHA-256。
- 连续第 3 次相同读：工具结果追加 `STAGNATION: ...` 警告；第 5 次相同读：`REFUSED: stagnation_detected`。
- 连续第 2 次相同写：`REFUSED: repeated_write_forbidden`（不重发写）。
- 状态 `repeat`/`stagnation` 和 run_log 的 completion 报告保留计数；不自动生成新计划、不自动换动作、不后台重试。
- 停止是合法结果；模型可改计划或如实未完成。

## 5. 接线点

| 位置 | 变更 |
| --- | --- |
| `go_chi_context.py`（新） | 测量、预算检查 |
| `go_chi_guard.py` | 可选 `context_recorder`/`context_limit`；预算失败在 reserve 前；`GoFailure` 不被吞成 `chi_request_invalid` |
| `go_chi_runtime.py` | 默认 `context_budget`；`context.jsonl`；run_log 上下文/完成字段；open unknown 终态检查 |
| `go_chi_state.py` | `completion_report`、repeat/stagnation、`block_mutation` 未知/重复写、completion 字段 |
| `go_chi_tools.py` | `local-completion-check`、停滞警告/阻断、未知写拒绝 |
| `go_chi_mcp.py` | MCP mutation 异常转 `UNKNOWN_WRITE_EFFECT`；停滞/未知写阻断 |

## 6. 失败状态

| 场景 | 结果 |
| --- | --- |
| 发送前超预算 | `chi_context_budget_exceeded`，无请求 |
| 预算配置非法 | `chi_context_budget_invalid` |
| `context.jsonl` 写失败 | `chi_context_persistence_failed` |
| 写效果未知 | 工具 `UNKNOWN_WRITE_EFFECT`；state open unknown |
| 未知未解决就结束 | run `chi_unknown_write_effect` incomplete |
| 未知期间再写 | `REFUSED: unknown_write_effect_pending:<id>` |
| 重复读第 3 次 | 结果追加 `STAGNATION` |
| 重复读第 5 次 | `REFUSED: stagnation_detected` |
| 重复写第 2 次 | `REFUSED: repeated_write_forbidden` |
| 完成核验未回读 | `completion_readback_required:<call_id>` |

## 7. 测试与证据

- Docker/Python3.12 全量 436 tests：2 个既有环境错误（缺 `anthropic`）、8 skipped；新增 12 个 F4–F6 测试。
- 上下文：组成分列、无正文、预算停止、`context.jsonl`、run_log 字段。
- 完成：`not_applicable/blocked/mechanical_pass`、unknown、violation。
- 失败：未知写读回/resolve、未知期间写拒绝、未解决 unknown 终态、重复读警告/阻断、重复写阻断。
- 未验证：真实 tokenizer/服务端预算、真实模型是否遵守停滞提示、真实 MCP 超时后的服务端副作用、F4 压缩可行性、真实任务/判分/临床。

## 8. 待外部 Gemini 审查的问题

1. 3.5M 字符/1M 估计 token/8k reserve 的默认预算是否足够保守？字符估计与实际服务 token 的偏差如何披露？
2. 把所有非取消、非 fatal 的 MCP mutation 异常都转成 `UNKNOWN_WRITE_EFFECT` 是否过宽？是否应只限传输/超时类？
3. 任意 open unknown 期间阻断所有 mutation 是否过严？是否应按 case/scope 精确阻断？
4. 停滞阈值（读 3 警告/5 阻断、写 2 阻断）是否合理？是否会误伤合法的重复读？
5. F4 不采用自动压缩的理由是否充分？是否还需要一个不接入生产的 checkpoint 可行性实验？
6. `capabilities` 名称仍为 `f0-f3-v1` 但行为扩展到 F0–F6，是否需要新的能力版本标识？
