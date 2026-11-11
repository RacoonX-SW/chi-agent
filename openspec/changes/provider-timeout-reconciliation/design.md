# Provider timeout 对账：接口与行为冻结（待外部 Gemini 审查）

状态：实现候选（本分支），基于 main `dac6080`。**尚未应用到正式 state-v2**；正式 pending 仍在，需复审后执行。

## 1. 输入与前置

- `root`：external state 根，含 `chi-accounting.json`、原 `.lock`、wire/tool evidence、run seal。
- `identity`、`accounting_sha256`：当前账本身份/旧账 SHA。
- `run`/`round`/`request_sha256`：必须精确指向 `state.pending`。
- `provider_record`：OpenCode Console 的**单请求** JSON `{event: {...}}`；当前由 1000 条导出中提取，SHA 固定。
- `reason`：用户可见的处置原因。

## 2. 必须通过的校验

1. 账本 SHA 与 `identity` 校验通过；`state.pending == {run, round}`，无 halt。
2. attempt 必须是 `failed`；request 必须是 `pending|unknown`，`request_sha256` 匹配，`diagnostic=chi_timeout`，`response_evidence=null`。
3. 无未清 tool-inflight。
4. 请求 evidence 的 dispatch 存在；`inspect_provider()` 要求：
   - Console `statusCode=200`、`outcome=succeeded`、固定 model/provider/product/path；
   - `x-opencode-session` 的 SHA-256 等于 dispatch `session_sha256`；
   - content-length 等于 dispatch `body_bytes`；
   - Console `startedAt` 与 dispatch 时间差 ≤30 秒；
   - input/output token 合法且 output ≤ 本次 max_tokens；
   - cost 为有限非负数。
5. 不要求 response evidence；不允许把 Console 记录伪装成 response body。

## 3. 写入

- 在 `reconciliations/` 下写三份不可覆盖文件：
  - `NNNN-accounting-<old_sha>.json`：原 accounting 原字节；
  - `NNNN-provider-<sha>.json`：provider 单请求记录原字节；
  - `NNNN-event-<sha>.json`：`chi-go-provider-reconciliation-v1` 事件。
- 事件字段：identity、accounting/provider SHA、provider request ID、run/round、request SHA、input/output tokens、console cost、reason。
- 更新 accounting：`pending=null`，`reconciliations` 追加 event hash；**request 状态保持 pending/unknown，attempt 状态保持 failed，seal 不变**。
- 用 `reconciliation.pending` 标记事务；失败/中断保留标记，后续校验拒绝，需人工调查。

## 4. 结果语义

成功返回：

```json
{
  "status": "reconciled_provider_timeout",
  "run": "...", "round": 17,
  "execution_allowed": false,
  "request_retry_allowed": false,
  "admission_cleared": true,
  "settled": false,
  "event_sha256": "...",
  "provider_request_id": "...",
  "tokens": {"input_tokens": 369422, "output_tokens": 8192},
  "console_cost": "0.0603285"
}
```

- `execution_allowed=false`、`request_retry_allowed=false`：原请求明确不可重发；只有 `admission_cleared=true` 表示该 pending 不再阻断**新的** attempt。
- `settled=false`：原请求仍是 unknown；`usage_totals` 仍把它列为 unsettled，billing 三项仍不完整。
- 不自动重发、不自动换 candidate、不自动判业务成功。

## 5. CLI

```bash
python scripts/go_chi_entry.py reconcile-provider \
  --bundle-sha256 <current identity> --history-mode external \
  --output-root /state \
  --expected-accounting-sha256 <old sha> \
  --target-run <run> --target-round 17 \
  --expected-request-sha256 <request sha> \
  --provider-record /provider.json \
  --provider-record-sha256 <sha> \
  --acknowledgement-reason "provider console 200 after client timeout"
```

需要当前包 identity 与账本身份一致；不读取 Key、不联网、不发模型请求。

## 6. 失败码

`chi_reconcile_invalid`、`chi_reconcile_hash_mismatch`、`chi_reconcile_target_invalid`、`chi_reconcile_inflight`、`chi_reconcile_provider_mismatch`、`chi_provider_record_invalid`；事务标记/事件文件损坏走 `chi_history_invalid`。

## 7. 验证

- 合成：正常对账后 pending null、request 仍 pending、seal 不变、可 reopen；session mismatch 拒绝且账不变。
- 真实副本：round 17 provider 记录（request ID `01a196e9…`、body 1,274,867、session hash `7bc5b6…`）试结算成功；正式 state-v2 未改。
- 现有全量测试仍通过（见报告）。

## 8. 待外部 Gemini 审查

1. 保留 request `pending` 仅清 `state.pending` 是否足以表达“准入解除但未结算”？是否应引入 `reconciled_unknown` 状态？
2. 事件不复制完整 response、只复制 provider 单请求记录，是否满足审计？
3. 三项 USD 账单不补、`usage_totals` 仍 incomplete，是否会让后续实验误读费用？
4. `execution_allowed=true` 是否容易被误读为原请求重试授权？CLI 文案/字段是否需更保守？
5. seal 不变但 state 增加 reconciliation，是否破坏“seal 绑定固定候选”的原意？是否应另存新 seal？
6. 30 秒/body/session 相关性是否足够；是否还要绑定 request ID 到 journal（目前只能靠 session/body/time）？
7. 事务标记/副本写入失败、重复对账、目标已被其他事件覆盖的行为是否闭合。
