# t023 正常 16384 基线通过（2026-11-09）

范围：target 绑定修复（PR86）+ unattributed 回读修复（PR87）合并后，重建 bundle/B 并重跑 t023 payer 正常 16384。**未跑 judge/Trial/发布；`official_reward=null`。**

## 1. 结果

| 项 | 值 |
| --- | --- |
| 代码 | main `8d351679afd11198d22802e6a34cd912d81c1be0` |
| bundle | `9fbc329c1ea3e18ce79b147e169a0e81c1311a556ff704b6f58223f98dc9ab2a` |
| identity | `dbe143ec8a05bef4d98e514aa5bd245d99e6ac696ad83ef4441c80b8ad6728af` |
| B | `ce-b-005`，complete，3 main，1378/104，charged 0 |
| C | `ce-c-baseline-003`，t023 payer，正常 16384 |
| C 结果 | **complete**，`final_output_claimed=true`，claim 已记录 |
| target | `CASE-7D075BE2`（正确） |
| 请求 | 41 main，全部 settled |
| recovery | 0 |
| drift | 0 |
| pending / halted | null / null |
| 用时 | runner 858,036 ms；operator 872,108 ms |
| 用量 | input 3,129,137 / output 37,198 |
| 计费 | list 0.48087013 / allowance 0.28852207 / charged 0 |
| 清理 | network/runner/world removed，quiescence confirmed |
| `inspect_history` | inspected |

claim：

```json
{"kind": "model_claim", "target": {"case_id": "CASE-7D075BE2"},
 "verified_status_call_id": "call_d68c4195207b421f846925e5", "version": 72}
```

最终状态：

```text
CASE-7D075BE2 finalized APPROVED: determination DET-e9290b8c final_decision=approved
(source md_decision MCD-fd8b5cc8, overridden=false), workflow determination/finalized
outcome=approved, 5/5 criteria met, 0 documentation gaps.
Authorization AUTH-CASE-7D075BE2-6E609F; approval letter LET-d9f638b8 delivered on portal.
```

## 2. 验证到的修复

1. **target**：本地 workspace 首读 `case:CASE-7D075BE2` 后绑定，没有再被同名 `CASE-E33A4F82` 覆盖。
2. **回读门禁**：`payer_letter_center.deliver` 仍是 `unattributed`，但后续 case-scoped `business_status` 回读可通过；本次最后 business mutation 是 `generate_notification`，回读在 seq 71，claim 成功。
3. **完成门禁**：41 轮内完成，无 recovery、无 drift、无 pending，未撞 50 轮上限。

## 3. 与前一基线的差异

| run | target | 结果 | 原因 |
| --- | --- | --- | --- |
| `ce-c-baseline-001` | `CASE-E33A4F82`（错） | failed | MCP 首读绑错 target |
| `ce-c-baseline-002` | `CASE-7D075BE2`（对） | failed | unattributed `deliver` 无法回读 |
| `ce-c-baseline-003` | `CASE-7D075BE2`（对） | **complete + claim** | 两项修复后通过 |

## 4. 身份与后续

- `ce-b-004`/bundle `108bf7d8…`/`ce-c-baseline-002` 对应 PR87 前代码；
- 本次 `ce-b-005`/bundle `9fbc329c…`/`ce-c-baseline-003` 对应 PR86+PR87 后代码；
- 旧 pending（C-002 round 8、t022/t024 429/timeout）保留，不重试、不清。

## 5. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 仅 t023 一题通过；其余 4 个失败题、CM/provider 正常任务、更广模型/锚点兼容性未验证。
