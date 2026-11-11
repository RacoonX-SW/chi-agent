# CM CKD 正常 16384 基线通过（2026-11-10）

范围：CM target 绑定修复（PR95）合并后，重建 bundle/B 并重跑 CM CKD 正常 16384。**未跑 judge/Trial/发布；`official_reward=null`。**

## 1. 结果

| 项 | 值 |
| --- | --- |
| 代码 | main `0637edd` |
| bundle | `ec8b3307646dd66c80d7c611ad0e49d099989b08619c88e0e56bd4e34453d38e` |
| identity | `431867bde6808eeb36fb2affb843f628fd13dd9b6f0fa15fd000bbfa8b92f8bd` |
| B | `ce-b-009`，complete，3 main，1418/135，charged 0 |
| C | `ce-c-cm-ckd-rerun-003`，CM CKD，正常 16384 |
| C 结果 | **complete + claim**，`final_output_claimed=true` |
| target | `CM-CASE-CM_CKD_MODERATE_ANXIOUS_001` |
| 请求 | 42 main + 10 patient_simulator，全部 settled |
| recovery / drift / pending | 0 / 0 / null |
| 用时 | runner 990,328 ms；operator 1,003,409 ms |
| 用量 | input 2,296,584 / output 42,795 |
| 计费 | list 0.36337199 / allowance 0.21802317 / charged 0 |
| 清理 | network/runner/world removed，quiescence confirmed |
| `inspect_history` | **inspected** |
| official_reward | null |

最终状态：

```text
Case CM-CASE-CM_CKD_MODERATE_ANXIOUS_001: full CM pipeline completed —
intake (chronic_disease/standard), chart review CMR-97202CE5,
outreach OUT-7BFD83BB (engaged, consent obtained),
assessment ASSESS-F9CE0C33 complete, care plan CP-E483F09A saved and finalized.
```

## 2. 验证到的修复

- target 在早期 `cm_chart.get_chart_data` 后绑定，不再依赖本地 case 文件；
- `local-state-update` 不再被 `chi_state_target_required` 拒绝；
- 42 轮内完成并 claim，无 recovery、无 drift、无 pending；
- tool evidence replay 通过，`inspect_history` inspected。

## 3. 当前 CM 状态

| 题 | 结果 | 说明 |
| --- | --- | --- |
| anorexia | complete + claim | inspect inspected |
| ckd | complete + claim | inspect inspected |
| asthma | failed | 模型连续 3 次漏传 `session_id`，用户决定是否手动重跑 |

## 4. 身份与后续

- `ce-b-008`/bundle `20b4dd75…`/`ce-c-cm-ckd-rerun-002` 对应 PR95 前代码；
- 本次 `ce-b-009`/bundle `ec8b3307…`/`ce-c-cm-ckd-rerun-003` 对应 PR95 后代码；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- asthma 的 `session_id` 漏传是模型行为，本次未改提示词/工具描述。
