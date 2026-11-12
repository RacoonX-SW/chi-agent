# 审核接续状态

## 开发成果

按公开任务 ID 去重，已核对至少 20 个不同任务有实际模型调用。Go 的 17 个任务各有至少一次 `complete + claim`。早期 DeepSeek 直连的 Provider t013、t018、t019 各有 `completed_ungraded` 记录。开发运行使用各自的冻结版本，`official_reward=null`。

| 领域 | 已核对任务 | 来源 |
| --- | --- | --- |
| Provider | t012、t013、t014、t015、t016、t017、t018、t019、t021、t032 | [早期 t013/t019](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/request-budget-awareness-review.md)、[早期 t018](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/deepseek-development-review.md)、[Go 三题](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/go-chi-timeout-recovery-review.md)、[九题 BDE](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/nine-task-bde-execution-20261107.md)、[三角色](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/unified-role-cm-lifecycle-review.md) |
| Payer | t011、t022、t023、t024、t027、t030 | [三角色](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/unified-role-cm-lifecycle-review.md)、[九题 BDE](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/nine-task-bde-execution-20261107.md)、[t027](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/c5-p2p-public-path-review.md)、[t030](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/c1-c3-admission-package-review.md) |
| CM | AFib、anorexia、asthma、CKD | [三角色](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/unified-role-cm-lifecycle-review.md)、[九题 BDE](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/nine-task-bde-execution-20261107.md) |

最近一组 `16384` 开发基线为 Payer t022、t023、t024 和 CM anorexia、asthma、CKD，均完成并记录 claim，`inspect_history` 返回 `inspected`。[六题结果及历史身份](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/cm-asthma-baseline-rerun-20261111.md#3-当前六题状态)

## 当前授权与未决事项

- PR #101 已进入基线 `fdff6cf`。仓库布局调整按批准的 OpenSpec Change 做离线迁移。已执行的 B/C 与摘要授权按原范围保存，新包的真实调用及候选准入另由用户决定。
- Go 使用 `record_only`。缺失费用明细按原规则留空，新出现的请求结果或用量未知会阻断继续运行。旧 `payer-010`、t015 传输和重跑、asthma nullfix 及恢复探针的 pending 保留，具体处置和所有历史身份见[迁移前的审核状态](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/REVIEW_STATE.md)。
- 上次独立通过的包外候选 `bfc1d8f` 限于原审核范围。Harbor 真实模型 Trial、最终配送、F.5 与官方评分仍待验证。[独立审核](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/final-validation-admission-review.md#8-gpt-独立复审与历史结论2026-11-06)
