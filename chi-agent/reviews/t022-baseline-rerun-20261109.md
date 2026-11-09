# t022 正常 16384 基线通过（2026-11-09）

范围：target 成功读取绑定（PR90）+ tool evidence 反斜杠文本（PR91）合并后，重建 bundle/B 并重跑 t022 payer 正常 16384。**未跑 judge/Trial/发布；`official_reward=null`。**

## 1. 结果

| 项 | 值 |
| --- | --- |
| 代码 | main `fc85879da80accd4f30dd9ba631fef89b92efc34` |
| bundle | `eedb73d814f281c48cffdffb7575a122f7652ca033575283b1ead160a590c2d5` |
| identity | `25a3eab3d43a4c88a6eeacf90544efaadc38a154979613241d3d5a138ab5af78` |
| B | `ce-b-007`，complete，3 main，1400/135，charged 0 |
| C | `ce-c-t022-rerun-003`，t022 payer，正常 16384 |
| C 结果 | **complete + claim**，`final_output_claimed=true` |
| target | `CASE-27EFB677`（正确） |
| 请求 | 42 main，全部 settled |
| recovery / drift / pending | 0 / 0 / null |
| 用时 | runner 882,947 ms；operator 897,265 ms |
| 用量 | input 3,687,301 / output 38,385 |
| 计费 | list 0.57507244 / allowance 0.34504345 / charged 0 |
| 清理 | network/runner/world removed，quiescence confirmed |
| `inspect_history` | **inspected** |
| official_reward | null |

最终状态：

```text
CASE-27EFB677 final determination DET-1b3395ce = approved
(source md_decision MCD-1b8c68fb, overridden=false);
case_status approved, auth AUTH-CASE-27EFB677-C65931;
workflow_state determination/finalized, outcome approved, action_owner none;
approval letter LET-f219f9ce delivered on portal.
```

## 2. 验证到的修复

1. **target 绑定**：seq 8 的失败 `local-fs-list case:CASE-E33A4F82` 不再绑定；seq 19 成功读取 `CASE-27EFB677` 后绑定正确。
2. **tool evidence**：含 `\*` 的 policy/PDF 文本逐字保存，round 11 的 replay 不再失败。
3. **完成门禁**：42 轮内 claim，无 recovery、无 drift、无 pending。

## 3. 与前一基线的差异

| run | target | inspect | 结果 | 原因 |
| --- | --- | --- | --- | --- |
| `ce-c-t022-rerun-001` | `CASE-E33A4F82`（错） | — | failed | 失败 `local-fs-list` 绑定 target |
| `ce-c-t022-rerun-002` | `CASE-27EFB677`（对） | failed | complete+claim | `unparseable_escaped_body` 清空正文 |
| `ce-c-t022-rerun-003` | `CASE-27EFB677`（对） | **inspected** | **complete+claim** | 两项修复后通过 |

## 4. 身份与后续

- `ce-b-006`/bundle `64a1c05d…`/`ce-c-t022-rerun-002` 对应 PR91 前代码；
- 本次 `ce-b-007`/bundle `eedb73d8…`/`ce-c-t022-rerun-003` 对应 PR90+PR91 后代码；
- 旧 pending（C-002 round 8、旧 t022/t024 429/timeout）保留，不重试、不清。

## 5. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 仅 t022 一题通过；其余失败题（t024、CM 等）、provider/CM 正常任务、更广模型/锚点兼容性未验证。
