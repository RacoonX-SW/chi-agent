# 九题开发验证准入准备（新 1800s + requirements 修复后）

日期：2026-11-06（Asia/Shanghai）。状态：**prepared_not_authorized**。本文件只准备新九题的配置、state 和准入绑定；**未运行任何 B/C，未调用模型、judge、患者模拟器、world 或 Trial，未发布**。

## 1. 绑定身份

| 项目 | 值 |
| --- | --- |
| source commit | `e3b58ba932f1f4a9ce8691ed857aff1232ca6a61`（PR68 合并后 main） |
| bundle manifest SHA-256 | `454b048ec5b52c39ccb3f0b730fdd30b5a8a5a2b750c6ee1a5bafad89b2d38fa` |
| release manifest SHA-256 | `58037fd47d1180663d1bd17f052735abb4a0458710cbaaa20e5a6e357191599b` |
| runtime identity | `4835ee369beb988fd6812bee78d5f2e73fc4e4c7fd1edbf5f2dd7594d2f7b3f8` |
| release 目录 | `runs/final-validation-20261105/exports/release-nine-20261106` |
| time policy | `chi_admission_seconds=1800`（bundle 内已确认） |
| verify / preflight | `valid` / `identity_verified`，upstream clean，exit 0 |
| config set SHA-256 | `f48488b86152e655e43abbbb98276a2f2cbb429c368a5bb1f4aaec09d64fb51e` |
| 机器清单 | [nine-task-config-set-20261106.json](nine-task-config-set-20261106.json) |

该 bundle 与 P1fix3 使用的 package 相同；P1fix3 的 requirements-on 证据（4/4 done、claim 已记录）直接适用于此 package。但本九题基线**不自动启用 requirements**。

## 2. 范围

同一九题、每题一次 attempt、每题新 world、新 state；不按结果换题、不自动重试、不换账根。

| # | role | task_id | run_id | config SHA-256 | manifest SHA-256 |
| ---: | --- | --- | --- | --- | --- |
| 1 | provider | `pa_t015_t015_o002_p01_new_referral_provider` | `final-c-provider-t015` | `a8c380ab9fc7…` | `5cd655f63b6e…` |
| 2 | provider | `pa_t016_t016_o001_p01_new_referral_provider` | `final-c-provider-t016` | `cee855a0f5a9…` | `fde037d0b733…` |
| 3 | provider | `pa_t021_t021_o003_p01_new_referral_provider` | `final-c-provider-t021` | `a935190ae268…` | `aa227b695699…` |
| 4 | payer | `pa_t022_t022_o001_p01_nurse_review_payer` | `final-c-payer-t022` | `f0bb7a3317d6…` | `1c10857de9f2…` |
| 5 | payer | `pa_t023_t023_o003_p01_triage_payer` | `final-c-payer-t023` | `94d176aa856e…` | `ab2f0362d335…` |
| 6 | payer | `pa_t024_t024_o001_p01_nurse_review_payer` | `final-c-payer-t024` | `352c957573a6…` | `f6b448c7adc2…` |
| 7 | cm | `cm_anorexia_hard_refuses_001` | `final-c-cm-anorexia` | `ba6438f73739…` | `fc2c9d4badf5…` |
| 8 | cm | `cm_asthma_low_coop_001` | `final-c-cm-asthma` | `0d6fe6de101d…` | `7508e7ac84cd…` |
| 9 | cm | `cm_ckd_moderate_anxious_001` | `final-c-cm-ckd` | `655bc2b70e69…` | `08bf58537813…` |

资源根不变：`runs/final-validation-20261105/resources/dataset`；manifest 根：`runs/final-validation-20261105/resources/manifests`。任务选择沿用[九题预登记](nine-task-preregistration-20261105.json)，没有按结果替换。

## 3. 新 state 与 B

| 项目 | 值 |
| --- | --- |
| state | `runs/final-validation-20261105/nine-20261106/state`（空，700） |
| output | `runs/final-validation-20261105/nine-20261106/c-runs/<run_id>` |
| evaluation | `eval-final-20261106-nine` |
| B | `final-b-010` **尚未运行**；必须先成功且 receipt/seal 与 runtime 匹配，才可启动 C |
| 旧状态 | 旧九题 state 的 t015 round4 pending 原样保留；不读取、不清除、不复用 |

新九题的 t015 是**新 state 的独立 attempt**，不是对旧 pending 的自动重试；旧 pending 仍需单独决定。

## 4. requirements 配置

- 本基线为 **off**：9 个 config 均不含 `requirements` 字段，`role_operator._validation_flags` 为空。
- 若要改为 **on**：在每个 config 增加 `"requirements": "chi-requirements-v1"`，重新计算 config SHA，并重新做一次准入绑定；不能沿用本文件的 config SHA。
- P1fix3 已证明同一 package 的 on 路径可完成并 claim（32 HTTP、451.8s、4/4 done），但 completion 只做 provenance 检查，4 项覆盖度不等于语义完整；on 是否进入九题需单独决定。

## 5. 预算与停止条件

- provider/payer：每 run 主请求+确认共享最多 50 HTTP，确认≤2。
- CM：主请求+确认共享最多 50 HTTP，另加开发 Go 患者辅助≤10，一般总 HTTP≤60。
- 九题合计最多 480 模型 HTTP；主/确认/患者输出 8192/32768/8192；thinking high；自动重试 0。
- 停止条件：任一 unknown token/result、pending/halt、跨 case/patient 写、越界副作用、预算/时间、取消、持久化或清理失败；身份/profile/资源 hash 不符；B 收据不匹配或缺失。停止后续题目，不重试、不换题、不改名、不换账根。

## 6. 未授权事项

- 未授权正式 Harbor、官方患者、judge、发布或额外已见题回归。
- 未授权 requirements on；本文件只准备 off 基线。
- `official_reward=null`；开发 role_operator 结果只能称“开发未见验证”，不是官方分数或临床通过。

## 7. 待用户确认

> 请确认是否按本文件的新身份执行 9 次开发 `role_operator` C：bundle `454b048e…`、runtime `4835ee36…`、新 state `nine-20261106/state`、新 B `final-b-010`、requirements off、每题一次、1800s、合计≤480 HTTP；任一 pending/unknown/halt 即停止，不重试、不换题。旧 t015 round4 pending 保持不动。

确认后再运行 B-010；B 成功并核验收据后才启动九题 C。
