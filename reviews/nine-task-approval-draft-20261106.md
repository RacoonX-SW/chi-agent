# 九题开发验证审批与首题执行记录（已批准；首题 pending 后停止）

日期：2026-11-06（Asia/Shanghai）。**本文件原为审批草案；用户已在对话中明确批准第6节文本。** 批准后只执行了首题 `final-c-provider-t015`：第4个 main 请求 240.022s `chi_timeout`，主账保留 `pending={本 run, round:4}`；按“任一 unknown、pending/halt 即停止”的停止条件，未执行其余8题，未重试/换题/换根。以下保留批准绑定和原文，执行结果见 `final-validation-nine-task-execution-20261106.json`。

## 1. 绑定身份

| 项目 | 值 |
| --- | --- |
| 候选 JSON SHA-256 | `0df12589c851b38423e6212997e7f4b9214912c25b7c84d7614f30e0c5f493d0` |
| 九题预登记 SHA-256 | `bb9d79308951e89939767697f82e3525b9e0f9d166e937c4158188de4edfb209` |
| 资源冻结 SHA-256 | `074fd38e98b7078de1f815cdf78114d64aee03d505999e1e41aa29b1d08de762` |
| Go manifest | `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d` |
| runtime | `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc` |
| 新 B 收据 | `final-b-001` 已成功；identity `2a9a3271…`，receipt SHA `ac6499ca…`，run seal SHA `6e229d76…` |
| 模型/端点 | `deepseek-v4.1-flash` / `https://opencode.ai/inference/go/openai/v1/chat/completions` |
| 推理/重试 | thinking enabled、reasoning_effort high、自动重试 0 |
| 开关 | 摘要 off、输出恢复 off、Y off |

## 2. 逐题范围与资源

| # | role | task_id | manifest SHA-256 | request PDF | run / attempt |
| --- | --- | --- | --- | ---: | --- |
| 1 | provider | `pa_t015_t015_o002_p01_new_referral_provider` | `5cd655f63b6e…` | 0 | `final-c-provider-t015` / `attempt-1` |
| 2 | provider | `pa_t016_t016_o001_p01_new_referral_provider` | `fde037d0b733…` | 0 | `final-c-provider-t016` / `attempt-1` |
| 3 | provider | `pa_t021_t021_o003_p01_new_referral_provider` | `aa227b695699…` | 0 | `final-c-provider-t021` / `attempt-1` |
| 4 | payer | `pa_t022_t022_o001_p01_nurse_review_payer` | `1c10857de9f2…` | 5 | `final-c-payer-t022` / `attempt-1` |
| 5 | payer | `pa_t023_t023_o003_p01_triage_payer` | `ab2f0362d335…` | 4 | `final-c-payer-t023` / `attempt-1` |
| 6 | payer | `pa_t024_t024_o001_p01_nurse_review_payer` | `f6b448c7adc2…` | 4 | `final-c-payer-t024` / `attempt-1` |
| 7 | cm | `cm_anorexia_hard_refuses_001` | `fc2c9d4badf5…` | 0 | `final-c-cm-anorexia` / `attempt-1` |
| 8 | cm | `cm_asthma_low_coop_001` | `7508e7ac84cd…` | 0 | `final-c-cm-asthma` / `attempt-1` |
| 9 | cm | `cm_ckd_moderate_anxious_001` | `08bf58537813…` | 0 | `final-c-cm-ckd` / `attempt-1` |

资源根：`runs/final-validation-20261105/resources/dataset`；manifest 根：`runs/final-validation-20261105/resources/manifests`。完整路径/size/hash 见 `nine-task-resource-freeze-20261106.json`。

## 3. 入口与计数

- 路径：开发 `role_operator.py` → `role_runner.py` → 冻结 release `package/scripts/go_chi_entry.py live`。
- 每题一次、独立新 world；同一 evaluation `eval-final-20261105` 和 state `runs/final-validation-20261105/state`；logs 每题独立目录。
- provider/payer：主请求+确认共享最多 50 HTTP，确认≤2，summary/continuation/患者 0。
- CM：主请求+确认共享最多 50，另加开发 Go 患者辅助≤10，一般总 HTTP≤60；确认≤2。
- 九题合计最多 480 模型 HTTP（provider 3×50 + payer 3×50 + CM 3×60）。
- 主输出 8192、确认 32768、患者 8192；high 不变。
- 开发 role_operator 只能称“开发未见验证”，不是正式 Harbor；官方患者/judge/发布不包含。

## 4. 成功证据

- 每题新 world、一次 attempt；全部实际请求/usage/费用留证；pending/halted null。
- 模型自主完成或停在合法 blocked/refused 分支；程序 claim/业务回读或明确缺口。
- 每题 final capture、资源 before/after hash、world quiescence、owned 容器/网络清理确认。
- 结果按题记录，不按结果替换任务；`official_reward=null`，不声称官方分数或临床通过。

## 5. 停止条件

- 新 unknown token/result、pending/halt、跨 case/patient 写、越界副作用、预算/时间、取消、持久化或清理失败。
- 身份/profile/资源 hash 不符、B 收据不匹配或缺失。
- 停止后续题目；不重试、不换题、不改名、不换账根、不追加请求。

## 6. 审批文本（用户已批准；保留原文）

> 我确认新 identity B `final-b-001` 已成功且收据与本候选/runtime 匹配；payer-010 旧 unknown 处置按另行明确决定保留，不修改旧 pending/账目。批准按候选 SHA `0df12589…`、预登记 SHA `bb9d7930…`、资源冻结 SHA `074fd38e…` 执行 9 次开发 `role_operator` C：provider/UM/CM 各 3 题、每题一次、新 world；provider/payer 每 run 主+确认≤50 HTTP，CM 另加开发患者辅助≤10；确认≤2；主/确认/患者输出 8192/32768/8192；摘要/恢复/Y off。任一 unknown、pending/halt、越界写、清理不明即停止；不按结果换题、不自动重跑。该批准不包含正式 Harbor、官方患者、judge、发布或额外已见题回归。

**当前状态：已批准；仅执行 `final-c-provider-t015`，round4 pending 后按停止条件中止；其余8题未运行。**
