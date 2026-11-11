# CM asthma 正常 16384 基线通过（2026-11-11）

范围：CM no-second-outreach guidance（PR100）合并后，重建 bundle/B 并重跑 asthma 正常 16384。**未跑 judge/Trial/发布；`official_reward=null`。**

## 1. 结果

| 项 | 值 |
| --- | --- |
| 代码 | main `a67052f` |
| bundle | `f346cca627b5efddd18200f4977fa79ed21863eec3c3d8c3d52f29c44a53adc6` |
| identity | `1715a86062a23f6ab2ff639ebfd02417394e31475428ce8287263e37e123dbd2` |
| B | `ce-b-013`，complete，3 main，1368/100，charged 0 |
| C | `ce-c-cm-asthma-rerun-008` |
| C 结果 | **complete + claim**，`final_output_claimed=true` |
| target | `CM-CASE-CM_ASTHMA_LOW_COOP_001` |
| 请求 | 43 main + 10 patient_simulator，全部 settled |
| recovery / drift / pending | 0 / 0 / null |
| 用时 | runner 1,133,651 ms；operator 1,144,306 ms |
| 用量 | input 1,779,312 / output 28,455 |
| 计费 | list 0.27811802 / allowance 0.16687078 / charged 0 |
| 清理 | network/runner/world removed，quiescence confirmed |
| `inspect_history` | **inspected** |
| official_reward | null |

## 2. 验证到的流程

- 只开了一次 outreach session；
- 10 次 `send_message` 后，session 到 turn 20 结束；
- 模型读取 transcript，调用 `cm_outreach.end_outreach_call`（seq 29），**没有重开 outreach**；
- 继续 `cm_assessment.start_assessment` → 4 次 `save_section` → `complete_assessment`；
- `cm_care_plan.create_draft` → `save_care_plan` → `finalize`；
- 最后 claim，care plan `CP-57D40E44` finalized。

## 3. 当前六题状态

| 题 | 结果 |
| --- | --- |
| t023 payer | complete + claim，inspect inspected |
| t022 payer | complete + claim，inspect inspected |
| t024 payer | complete + claim，inspect inspected |
| CM anorexia | complete + claim，inspect inspected |
| CM CKD | complete + claim，inspect inspected |
| CM asthma | complete + claim，inspect inspected |

## 4. 身份与后续

- `ce-b-012`/bundle `d0258448…`/asthma rerun-007 对应 PR100 前代码；
- 本次 `ce-b-013`/bundle `f346cca6…`/`ce-c-cm-asthma-rerun-008` 对应 PR100 后代码；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 六题通过只代表这些正常 16384 开发运行；provider 检查项、其他任务/模型和官方评分未验证。
