# 九题 nullfix 执行记录（requirements off）

日期：2026-11-06（Asia/Shanghai）。身份：source `1c008bb`、bundle `b7e247f6…`、runtime `dafc9ce9…`、1800s、requirements off。**本记录是开发未见验证，不是官方分数或临床通过；`official_reward=null`。**

## 1. 结果总表

| # | role | run | 结果 | 物理 HTTP | 耗时 | claim | 确定性检查 |
| ---: | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | provider | `final-c-provider-t015` | failed / `chi_tool_batch_invalid` | 34 | 434.5s | null | 7 true / 5 false / 1 N/A |
| 2 | provider | `final-c-provider-t016` | **complete** | 36 | 702.2s | 已记录 | 7 true / 4 false / 1 N/A |
| 3 | provider | `final-c-provider-t021` | failed / `chi_context_budget_exceeded` | 20 | 400.0s | null | 6 true / 5 false / 1 N/A |
| 4 | payer | `final-c-payer-t022` | failed / `chi_output_truncated` | 13 | 595.7s | null | 3 true / 16 false / 4 N/A |
| 5 | payer | `final-c-payer-t023` | failed / `chi_output_truncated` | 18 | 276.8s | null | 10 true / 13 false / 2 N/A |
| 6 | payer | `final-c-payer-t024` | complete / completion blocked | 33 | 458.3s | null | 11 true / 1 false / 10 N/A |
| 7 | cm | `final-c-cm-anorexia` | failed / `chi_tool_batch_invalid` | 11 | 100.3s | null | 2 true / 4 false / 8 N/A |
| 8 | cm | `final-c-cm-asthma` | failed / `chi_timeout` + **pending round21** | 21 | 156.5s | null | 2 true / 4 false / 8 N/A |
| 9 | cm | `final-c-cm-ckd` | **not_run** | 0 | — | — | — |

- B-011：3 main settled、1367/101、receipt/seal 匹配。
- C 合计：provider HTTP 179、物理 186（含患者辅助）、input 20,494,515 / output 233,047；加 B 共 189 HTTP、input 20,495,882 / output 233,148。
- 所有已启动 run 的 runner/world/network 均 removed，quiescence confirmed；无容器/网络残留。

## 2. 停止原因

`final-c-cm-asthma` 第 21 轮 main 请求 `chi_timeout`（stage=transport），主账保留：

```json
{"run": "final-c-cm-asthma", "round": 21}
```

按准入停止条件，**`final-c-cm-ckd` 未启动**；没有自动重试、没有换题、没有清除 pending。旧 t015 round4、P1fix round2 429、旧 900s/429/1800b pending 均未改变。

## 3. 失败分类

| 类型 | run | 说明 |
| --- | --- | --- |
| 模型未知字段 | t015、cm-anorexia | `local-state-update` 传入 schema 不允许的字段（t015 为 `put_plans`），整批 `arguments_schema` 被拒；不是 state 业务校验错误 |
| context 预算 | t021 | `chi_context_budget_exceeded`，20 HTTP、400s；未超 1800s |
| 输出截断 | t022、t023 | `chi_output_truncated`；恢复策略按准入保持 off，未自动恢复 |
| 业务回读缺口 | t023、t024、cm-anorexia、cm-asthma | 有 business mutation，但无后续 business status readback；completion `blocked`/`required_readback=business_status` |
| 传输超时 | cm-asthma | `chi_timeout`，round21 pending；已停止 |

## 4. 成功/可用结果

- **t016 complete**：36 HTTP、702.2s、claim 已记录、7/4/1；PA 已提交、payer intake `in_progress`，不是批准。
- **t024 complete 但 blocked**：33 HTTP、458.3s、无 claim；`payer_intake_hub.save_requesting_provider` 后缺 business status readback，completion 正确阻断。
- t015 业务上已创建 case、提交 PA 并完成状态回读，但最后一批工具调用因 `put_plans` 被拒，未 claim；说明工具 schema 的未知字段拒绝仍然很硬。

## 5. 结论

- nullfix 修复有效：没有再出现 `target.case_id: null` 的 `arguments_schema` 失败。
- 但九题 off 运行没有完成：8 个已启动任务中 2 个 complete（其中 1 个 blocked/no claim），6 个失败，1 个未运行；失败集中在模型工具参数格式、context 预算、输出截断、业务回读缺口和一次传输超时。
- 1800s 不是主要瓶颈：t021/t022/t023 都在 1800s 前因 context/output/格式失败；cm-asthma 是 transport timeout。
- 不能把这些结果写成官方分数、临床通过或九题全通过；`official_reward=null`。

## 6. 下一步（未授权）

1. 先处理 `final-c-cm-asthma` 的 round21 pending：等待/新 state+新 B/显式 acknowledgement，由用户决定；不得静默清除。
2. 若继续九题，建议先修工具参数格式的可用性（未知字段提示、`put_plans` 类错误、可恢复的 batch 错误）并评估 context/output 预算，再决定是否用新 bundle 重跑；不要复用当前失败 state。
3. 旧 pending 和本轮失败记录保留；不自动重试、不换题、不换根。
