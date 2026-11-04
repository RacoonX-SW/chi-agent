# 输入摘要 length 失败的离线观测与候选方案（未隔离根因）

日期：2026-11-04。范围：只读回放 `vprep-s-001` 第 20 笔 summary 的原响应，解释固定 guard 的拒绝与摘要可用性缺口；不实现生产修改、不跑真实请求、不改账。详细受限证据留在本地忽略目录，本报告只含聚合数字与哈希。

## 1. 现场与证据

- `origin/main` 已含 PR54/PR55；本任务从 `9db7fdb` 新建 `deepseek/summary-failure-diagnosis`，未续写已合并分支。原运行 worktree 保留；本目录无并行写入者。
- 只读证据（`runs/validation-live-20261104/`）：
  - `state/chi-accounting.json` SHA `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`；
  - `state/wire-evidence/vprep-s-001/020-request.json` raw SHA `1fc57c6e…`，`020-response.json` raw SHA `254454dd…`；
  - `020-summary-selection.json`、`summary-trace.jsonl`、`probe-summary/runner-logs/result/{run_log,summary-trace}`。
- 未读取 Key/.env，未启动 world/Trial/judge，未重跑 attempt。

## 2. 独立复现 guard 拒绝

禁网 Docker/Python 3.12，加载固定 `go_chi_guard.ChiGuard._response`（只调用该分支，不伪造身份）：

```
payload = json.load(020-response.body_utf8)
object.__new__(ChiGuard)._response(payload, 'summary')
→ GoFailure: chi_summary_invalid
```

同一账本只读检查：

```
pending None / halted None / execution_allowed False
attempt failed chi_summary_invalid, requests 20
summary_events: status=requested, candidate/checkpoint=null, projections=[]
request20 status=settled, purpose=summary
```

结论：**拒绝机制正确**。响应 `finish_reason=length`、`content` 为空、无 tool_calls，guard 在 `install_summary` 之前停止；请求已结算，不是“仍在途”；没有安装半成品 checkpoint，也没有后继 main。

补充区分：合成 `stop`+非空正文可被 guard envelope 接受，但候选解析仍可能 `chi_summary_invalid`；真实失败停在前者之前，尚未检验候选 schema 层。

## 3. 输入体量与预算

| 项 | 值 |
| --- | --- |
| summary 请求体 | 852,823 bytes（2 messages） |
| system / user | 370 / 751,563 bytes |
| 选中 source messages | 58 条（assistant 17、tool 41），702,513 bytes |
| 其中 tool 结果 / assistant 正文 / reasoning | 557,475 / 2,986 / 70,750 bytes |
| protected 快照 | 40,464 bytes |
| output_schema | 1,554 bytes（很小） |
| 模型输入 tokens | 212,561 |
| 输出 tokens | 8,192（reasoning 8,192，content 0） |
| 请求参数 | max_tokens 8192、thinking enabled、high、无 tools、无 response_format |

口径说明：source/protected/schema 为 canonical JSON 字节，tool/content/reasoning 为正文 UTF-8 字节，body 为原 HTTP JSON 字节；二次 JSON 编码/转义导致各列不能直接相加。输入大头是旧工具观察（557KB），schema 仅 1.5KB；选区为 58 条闭合消息（start=2、end=60、source_used=19），保护快照与 selection hash 均在。严格离线校验未发现选区越界、未闭合批次或保护字段异常；**schema 字节占比小只说明字节占比，不代表生成/引用它的推理成本低**。

## 4. 判断：停止正确，根因未隔离

- 端点接受请求并返回 HTTP200/可信 usage；但固定 `high + 8192` 下，本样本把全部输出预算用于 reasoning，未产出最终 JSON。
- guard 的拒绝是**安全且必要**的：不能把空正文、length 或 reasoning 文本当摘要候选；也不能据此安装 checkpoint 或继续 main。
- 本样本在固定 high+8192 下耗尽输出预算，未产出最终正文，暴露**摘要可用性不足**。严格离线校验未发现选区闭合/hash 或保护快照一致性异常；但**输入规模、选区内容、提示/schema 复杂度与模型推理行为的相对影响尚未隔离**。
- HTTP200 只证明传输与计费，不证明结构化输出或端到端可用；不能据一次失败断言全部模型/端点行为。
- 方案 B 只是待验证候选，不是已定位根因或已证明有效。

## 5. 候选方案（离线，均未实施）

| 方案 | 需要改什么 | identity/B | 风险 | 评价 |
| --- | --- | --- | --- | --- |
| A 保持现状 + 文档限制 | 无代码 | 无 | 启用摘要时仍保留已知失败风险 | **推荐先采用**；无新增生产行为、内包/runtime 身份或账本变化；若重建 release，source_commit 包装变化另列 |
| B 选区字节上限 | 包内 `go_chi_summary` 选区算法（仍需闭合批次、保留最近 2 批） | 包字节变化 → 新 bundle/runtime，新 B | 可能降低 reasoning，但不保证；摘要信息减少 | 最小候选，需单独有界任务 + 一次授权探针 |
| C 摘要提示硬化（只输出 JSON/禁止长思考） | 包内摘要 prompt | 新身份/新 B | 对 reasoning 模型效果不确定 | 不建议单独做，缺证据 |
| D 调低 summary reasoning 或提高 8192 | profile/policy/contract | 新身份 + 契约变更 | 违反当前固定 high/8192；费用与可比性变化 | 需用户先改契约，不属本任务 |
| E length 后用更小选区自动重试 | 新重试/许可语义 | 新身份 + 新策略 | 与 0 自动重试、每 run ≤1 冲突 | 不采用 |

方案 A 的离线验收：

1. 原响应回放仍 `chi_summary_invalid`；请求 settled、pending=null、无 candidate/checkpoint/后继 main。
2. 默认关闭、无真实请求；文档明确“长选区下摘要可能不可用”，不把 HTTP200 写成通过。

若需要方案 B，建议另立有界任务，离线验收契约：

- 选区仍只取完整闭合批次、保留最近 2 批、≥1 旧批次；新增确定性字节/估算上限并记录未选原因；
- 若没有任何完整旧批次能容纳上限，必须停止/不发送；单个超大闭合批次也要有明确停止行为；
- 上限必须覆盖完整 summary 请求（protected、schema、JSON 转义开销），不能只算 source 正文；
- 安装后的 main 必须继续通过原 context 预算检查；减少 1024 字节不能替代预算适配；
- 不新增选区重试、摘要次数或隐藏回退；
- 用同一 source 生成新请求，证明请求体下降、selection/protected hash 自洽、最终 wire 仍比 source 小 ≥1024 bytes；
- guard/candidate/install 用 MockTransport 正向与 length 负向；不改变 high/8192/阈值；
- 包内字节变化 → 重建 identity，单独审核并重绑 B；真实端点是否改善必须另获一次探针授权，不能离线预填通过。

## 6. 未验证与边界

- 未证明方案 B 能让真实端点产出最终 JSON；需要一次新的授权探针（独立预算/停止条件）。
- 未评估摘要忠实度、净费用收益、其他任务/上下文规模；单样本不外推。
- 未改 production、账本、B 收据、pending/halt；payer-010 旧 unknown 保持。
- 本报告不构成新运行授权；剩余 30 次请求上限不是许可。

## 7. 结论

本样本是**正确的 guard 停止**，并暴露固定 high+8192 下的摘要可用性不足；严格离线校验未发现选区/hash/保护快照异常，但**输入规模、提示复杂度与模型推理行为的相对影响尚未隔离**。最小行动是保持默认关闭并记录限制（方案 A）。若摘要能力需要覆盖长选区，应另立方案 B 的有界实施任务，先验证上限设计与停止行为，并在新身份/B 与单独真实授权后验证；不得靠调整模型参数或阈值强制触发。
