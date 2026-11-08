# context-engineering 施工决定（Q1–Q6）

日期：2026-11-08。范围：离线实现与测试；不跑真实 B/C、judge/Trial、发布。以下结论先于代码，后续若与代码冲突以本文件为准并记录修订。

## Q1：read 占位符放在哪一层？`validate_history` 的输入是什么？

- **占位符/reducer/去重放在 `ChiGuard` 的 wire 投影层**，不放进 `ToolContract`，也不改写 SDK 历史。
- **`validate_history` 的输入是源历史（source history）**：完整 system、instruction、assistant/tool 批次和完整工具结果。
- 投影只生成发给模型的 `wire_body`；源历史仍在 SDK/contract 中保留完整结果。
- 投影必须在源历史通过 `validate_history` 之后执行；投影后的 wire 只做预算计量和发送，不再用投影结果反推 contract。
- journal 记录请求的 wire 证据，并记录投影的 `source_sha256`、`wire_sha256`、节省字节和替换/去重计数；旧 v2 请求没有该字段时按无投影解释。

## Q2：锚点放 `messages[2]` 是否与 SDK/DeepSeek 兼容？

- **锚点作为 wire 中的第二条 user 消息放在 `messages[2]`**，即 `[system, instruction, anchor, ...history]`。
- SDK 的源历史保持 `[system, instruction, ...history]`，不把锚点写进 SDK 的内部消息列表；guard 在投影时确定性插入锚点。这样不会改变 SDK 的 tool-call 回放结构，也不会让 contract 把锚点误认为批次。
- `validate_history` 新增可选 `anchor` 参数：允许零条（旧历史）或恰好一条固定 schema 的锚点；缺失/重复/hash 不符拒绝。
- **离线回放验证**：用构造的 wire body 验证锚点位置、schema、hash 和 history 校验；真实 SDK/DeepSeek 对 `messages[2]` 的兼容性仍需真实模型验证，本阶段只保证离线契约。
- summary/recovery 默认关闭；本阶段不把锚点与这两个可选机制组合，作为残余风险记录。

## Q3：mutation 规范记录里哪些字段由程序推导？

规范记录固定为：

```json
{
  "schema": "chi-tool-record-v1",
  "call_id": "<contract call id>",
  "tool": "<canonical tool name>",
  "event": "returned|returned_error|refused|failed",
  "status": "ok|error|refused|unknown",
  "key_ids": {"case_id": "...", "patient_id": "...", "...": "..."},
  "result_sha256": "<full result sha256>"
}
```

程序只从以下来源推导，**不采用模型写的摘要**：

- `call_id`、`tool`、`event`：contract/journal 事件；
- `status`：event 映射；
- `key_ids`：从工具参数和完整结果 JSON 的固定 ID 字段提取；
- `result_sha256`：完整结果原文的 SHA-256。

各类 mutation 的 `key_ids`：

| 类别 | key_ids |
| --- | --- |
| `local-fs-write` / `local-fs-edit` | `path` |
| `local-confirm-patient` | `patient_id` |
| `local-claim_done` / `local-state-update` | 无 |
| `cases.create_from_order` | `order_id`, `case_id` |
| `cases.get_case` / `auth.check_status` | `case_id` |
| `forms.save_form_response` | `case_id`, `form_id` |
| `docs.upload_evidence` / `docs.upload_evidence_file` | `case_id`, `document_id` |
| `docs.create_submission_bundle` | `case_id`, `bundle_id` |
| `auth.submit_authorization` | `case_id`, `request_id` / `authorization_id` |
| `auth.*peer_to_peer` / `p2p_session.*` | `case_id`, `request_id` |
| `payer_intake_hub.*` | `case_id`, `intake_case_id` |
| `triage.*` | `case_id`, `triage_id` |
| `review.*` | `case_id`, `review_id` |
| `determination.finalize` | `case_id`, `determination_id` |
| `payer_letter_center.*` | `case_id`, `letter_id` |
| `cm_intake.*` | `case_id`, `referral_id` |
| `cm_chart.*` | `case_id`, `review_id` |
| `cm_outreach.*` | `case_id`, `call_id` |
| `cm_assessment.*` | `case_id`, `assessment_id` |
| `cm_care_plan.*` | `case_id`, `care_plan_id` |

缺失字段只是省略，不补猜测值；同一 call 的规范记录在投影中保持稳定。

## Q4：payer/provider/CM 的终态对象与必要步骤

终态对象与必要步骤由程序从 journal + TaskState 推导，模型引用不作为证据。

### payer

- 终态对象：`PayerDetermination`（`determination.finalize` 返回）或明确的 `denied`/`stopped` 状态对象；终态 case 状态与 determination 一致。
- 必要步骤（按任务需要取子集，由 role guidance/requirements 约束）：
  1. intake 读取/确认；
  2. triage（urgency/SLA/lane）；
  3. nurse review（criteria + recommendation）；
  4. MD review（需要时）；
  5. determination finalize；
  6. letter/notification（需要时）；
  7. 终态回读。

### provider

- 终态对象：`submission_packet`（`docs.create_submission_bundle`）和 `auth.submit_authorization` 后的 case 状态；拒绝类为 `finalize_provider_determination` 的 `do_not_submit`/`gather_more_evidence` 记录。
- 必要步骤：chart 读取 → case 创建 → forms/evidence → provider determination → submit/停止 → `check_status` 回读。

### CM

- 终态对象：`care_plan` finalized（`cm_care_plan.finalize`）；拒绝对话为 `cm_outreach.end_outreach_call` 的明确停止对象。
- 必要步骤：chart review → assessment complete → care plan draft/save/finalize → outreach/consent（需要时）→ 终态回读。

### 无动作结局

拒绝/停止/转交类任务不要求写业务 mutation；门禁检查明确终态对象（denied/stopped）和回读，而不是“有没有写”。

## Q5：`max_results` 单文件 50 与 8K 截断如何叠加？

- `max_results` 只控制命中条数：默认 10，目录/多文件上限 20，单文件允许 50。
- 无论条数多少，文本结果仍受 **8K 码点 / 32KB 字节** 工具层截断；先取前 N 条，再截断，返回 `total_matches`、`omitted`、`truncated`。
- 单文件 50 条可能被 8K 截断，这是预期行为：条数上限不替代字节上限，预算仍然安全。
- 路径/ID/mutation 参数永不 clamp；只有安全数值参数（`max_results`）在重复违反 2 次后 clamp，并记录 `requested`/`effective`/`capped`。

## Q6：哪些常量/schema 进入 bundle/runtime 身份？旧 v2 如何只读兼容？

进入身份（bundle/runtime 哈希）：

- `chi-context-v3`、`chi-context-budget-v3`；
- `chi-context-assembly-v1`、`chi-context-anchor-v1`；
- `chi-tool-record-v1`；
- `chi-completion-v5`（mandatory claim）；
- 预算 profile 常量（provider window、safety fraction、floor/observed、max bytes）和工具 schema/描述；
- 新增/修改的 `scripts/go_chi_*.py` 与测试不进入 runtime 身份，但脚本内容会改变 bundle 哈希。

只读兼容：

- `go_chi_context.check_budget` 保留 v1/v2 分支，旧 `chi-context-v2`/`chi-context-budget-v2` 证据可继续 inspect，不迁移、不改写、不重算；
- 旧 run 的 launch 没有 `context_policy` 时按 v2 语义解释；
- 新 run 在 launch 写 `context_policy: chi-context-v3`；
- 旧 `run_log` 字段保留，新增字段缺失时按旧语义读取；
- journal/inspect 对旧请求没有投影字段时按无投影解释。

## 实施顺序

Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8；每个 Task 定向测试通过后再进入下一个。发现设计/代码冲突时停止并记录，不静默扩大范围。
