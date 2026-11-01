# F7 实验工具接口与行为冻结（待外部 Gemini 审查）

状态：离线实现候选 `fd617c3`，基线 `4ade699`。本页冻结 manifest/record/summary 的最小接口。

## 1. Manifest：运行前冻结

`schema=chi-experiment-campaign-v1`，JSON 必须严格匹配以下结构（未知字段拒绝）：

```json
{
  "schema": "chi-experiment-campaign-v1",
  "campaign_id": "f7-example-001",
  "candidate": {
    "source_sha256": "<64 hex>",
    "bundle_sha256": "<64 hex>",
    "model": "deepseek-v4.1-flash",
    "endpoint": "opencode-go",
    "simulator": "dev-go-patient-v1",
    "capabilities": "f0-f6-v1"
  },
  "cells": [
    {
      "cell_id": "F4-off",
      "mechanism": "F4",
      "mode": "off",
      "toggle": "context_budget",
      "hypothesis": "baseline without the mechanism",
      "tasks": [
        {
          "task_id": "pa_t013_t013_o002_p01_new_referral_provider",
          "role": "provider",
          "attempt": 1,
          "resources": {
            "manifest_sha256": "<64 hex>",
            "world_image_id": "world-v1"
          },
          "checks": ["request_budget", "case_status"]
        }
      ],
      "limits": {"provider_requests": 50, "output_tokens": 8192}
    }
  ],
  "stop_conditions": ["unknown_usage", "cross_patient_write", "cleanup_unconfirmed"],
  "created_at": "2026-11-01T00:00:00Z"
}
```

规则：

- `mechanism` ∈ F1–F6；`mode` ∈ off/on/na。
- 每个 mechanism 要么有同一组任务的 off+on 两臂，要么只有一个 `na` 臂并给 `reason`；不能只有单臂 on/off。
- off/on 两臂的 `(task_id, role, attempt)` 集合和 `limits` 必须完全一致；否则 `manifest_comparison_mismatch`。
- 同一 cell 内 `(task_id, role, attempt)` 不能重复；checks 不能重复。
- 资源只登记 manifest SHA 与世界镜像 ID，不登记任务答案、rubric、隐藏路径。
- `freeze_manifest()` 输出规范 JSON 与 SHA-256；manifest 在运行前固定，后续不能靠改 ID 换条件。

## 2. Record：一次计划单元的观察

`schema=chi-experiment-record-v1`：

```json
{
  "schema": "chi-experiment-record-v1",
  "campaign_id": "f7-example-001",
  "cell_id": "F4-off",
  "task_id": "pa_t013_t013_o002_p01_new_referral_provider",
  "role": "provider",
  "attempt": 1,
  "candidate": { "...same as manifest..." },
  "run": {"status": "completed|failed|skipped|blocked", "safe_error_code": null},
  "logs": {"present": true, "reason": null},
  "checks": [{"id": "request_budget", "status": "pass|fail|na"}],
  "business": {"state": "observed|not_observed|unknown", "evidence": "..."},
  "content": {"status": "not_performed|performed", "result": null},
  "official_reward": null,
  "usage": {"input_tokens": 10, "output_tokens": 5, "cost_usd": null},
  "failure": null
}
```

规则：

- `candidate` 必须与 manifest 完全一致；否则 `record_candidate_mismatch`。
- `(cell_id, task_id, role, attempt)` 必须对应 manifest 的计划；否则 `record_unplanned`。
- 同一计划单元只能有一条 record；重试必须使用新 attempt 并在 manifest 中预先登记，不能覆盖历史。
- `logs.present=false` 必须给 `reason`；汇总计入 `missing_evidence`，不改写 `completed`，也不当成通过。
- checks 必须是 manifest 中该任务的子集；缺失的检查计入 `not_run`，不会被补成 pass。
- `business.state=observed` 必须有非空 evidence；否则 `record_business_evidence_missing`。
- `failed/blocked` 必须有 `failure`；`completed` 不能带 failure。
- `official_reward` 只保留原值或 null；缺失不补 0，不计算均值/成功率。
- usage 三项分别可为 null；汇总给 known sum 与 missing count，不把缺失当 0。

## 3. Summary：全分母、不合成结论

`experiment_summary.summarize(manifest, records)` 输出 `chi-experiment-summary-v1`：

- `planned_tasks`：manifest 中所有计划单元数。
- 每个 cell：`attempted/completed/failed/skipped/blocked/not_run/missing_evidence`；`not_run = planned - attempted`。
- checks：`pass/fail/na/not_run`；skipped/blocked 的计划检查计入 `not_run`，不补 pass。
- business：`observed/not_observed/unknown`；content：`not_performed/performed`。
- official：`present/absent`，不求和。
- usage：`*_known_sum` 与 `*_missing` 分开。
- `failure_codes` 计数；`by_role` 保留计划/运行/未运行分母。
- `mechanisms` 只标 `off_on` 或 `not_applicable`，不计算因果效应。
- 不输出 `success_rate`、不推导官方分数、不把 NA/跳过/缺日志算通过。

## 4. CLI

```bash
python scripts/experiment_manifest.py validate --manifest campaign.json
python scripts/experiment_manifest.py freeze --manifest campaign.json
python scripts/experiment_summary.py summarize --manifest campaign.json --records records.json
```

records 支持 JSON 数组或 `.jsonl`。有效返回 0；无效返回 1 和 `{"status":"invalid","code":"..."}`。

## 5. 与 Z4/Z5 的接入

- Z4 先用 manifest 固定候选、任务/资源、机制 off/on、上限与停止条件；运行后把每条 record 写入同一 campaign。
- Z5 的九题未见集用独立 campaign；看过结果后改候选，旧题转开发题，新候选不能复用旧未见结论。
- 汇总只提供计数和分母；是否采用某机制、是否继续实验由用户/规格决定。

## 6. 待外部 Gemini 审查

1. off/on 必须同任务/同 limits 是否足够保证单变量？是否还需固定请求上限之外的资源/镜像/时间？
2. `na` 臂只给 reason 是否足够，是否需要记录“不采用”的替代证据？
3. skipped/blocked 的检查全部计 `not_run` 是否正确？blocked 可能已执行部分检查。
4. 缺日志仍保留 `completed` 但计 `missing_evidence`，是否会被误读为完成？
5. attempt 只能预先登记，是否支持问题驱动回归？回归应用新 attempt/campaign，不能覆盖旧记录。
6. record 的严格字段是否适合真实运行产物？是否需要与 run_log/completion 的字段映射表？
7. 是否需要把 manifest SHA/record 的日志 hash 写入 journal 或独立 seal？
