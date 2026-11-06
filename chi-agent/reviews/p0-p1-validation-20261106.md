# P0/P1 实际验证：1800s t015 与 requirements on

日期：2026-11-06（Asia/Shanghai）。基于合并后的 `origin/main=dbbd356`（PR65/PR66 已合并）。本报告是开发验证记录，不是独立复审，也不是官方分数。

## 1. 共同身份

| 项目 | 值 |
| --- | --- |
| release | `runs/final-validation-20261105/exports/release-p0p1-20261106` |
| bundle manifest SHA-256 | `eabec08e905edeac81ee6eea7819132d16b3c54981368e1a5a3c7c706c841c77` |
| release manifest SHA-256 | `836e043a19f591be197424cf5ebaf218c2bdfd5fd34a4715f87822aec158f7c4` |
| runtime identity | `f41021f4f869cbd26d1a289a109ad17e796c5139ae1839ac38154a1417554b76` |
| source commit | `dbbd356f85a18031050d98c52a6a417403cd87ad` |
| verify/preflight | valid / identity_verified，upstream clean，exit 0 |

## 2. P0：t015 off + 1800s

| 项目 | 实际值 |
| --- | --- |
| state | `runs/final-validation-20261105/p0-1800c/state` |
| B | `final-b-005`：3 main settled、1357/89、charged 0 / list 0.0002881 / allowance 0.00017286；receipt/seal 匹配 |
| C run | `final-c-provider-t015-p0` / `attempt-1`；evaluation `eval-final-20261106-p0` |
| 结果 | **complete**，runner exit 0；393.6s；无 pending/halt |
| 物理 HTTP | **34**（33 main + 1 confirmation），全部 settled |
| completion | `chi-completion-v3`，`mechanical_pass` / `observed`，claim 已记录 |
| 业务进度 | case created、service request、procedure/diagnosis/service type/site、cross.forward true；case_status/final_action/provider_determination false；packet_absent false；required_documents N/A |
| 确定性检查 | 7 true / 4 false / 1 N/A |
| usage | input 4,226,254 / output 42,870；list 0.69348377 / allowance 0.41609026 / charged 0 |
| 最终输出 | PA 已通过 portal 提交，状态 submitted，等待 payer decision；不是 approval |
| 清理 | runner/world/network removed；capture/cleanup error null；quiescence confirmed |

**结论**：1800s 窗口足够；t015 在 393.6s 内完成，claim/readback 通过。确定性检查仍显示部分 new-referral/final-determination 项为 false，不能称为官方通过或完整业务终态。

## 3. P1：t015 requirements on + 1800s

| 项目 | 实际值 |
| --- | --- |
| state | `runs/final-validation-20261105/p1-req-on/state` |
| B | `final-b-006`：3 main settled、1417/146、charged 0 / list 0.0001308 / allowance 0.00007848；receipt/seal 匹配 |
| C run | `final-c-provider-t015-p1` / `attempt-1`；evaluation `eval-final-20261106-p1`；requirements `chi-requirements-v1` |
| 结果 | **failed / chi_run_time_limit**；runner exit 1；1829.0s；无 pending/halt |
| 物理 HTTP | **37**（36 main + 1 confirmation），全部 settled |
| completion | `chi-completion-v4`，`blocked` / `not_verified`，reason `completion_requirements_undeclared`；claim null |
| requirements | `declared=false`、`count=0`、`status=undeclared`；`instruction_sha256=ae40b530…` |
| 业务进度 | 与 P0 相同的 case/service 检查 7 true / 4 false / 1 N/A；有 `auth.submit_authorization` 和文件写，但无最终 business status readback |
| usage | input 5,626,924 / output 51,997；list 0.87326112 / allowance 0.52395663 / charged 0 |
| 最终输出 | null（时间上限截断） |
| 清理 | runner/world/network removed；capture/cleanup error null；quiescence confirmed |

**模型实际尝试了 requirements，但全部被拒绝**：

- 提交了 4 项，id 为 `patient_identified` / `workup_non_diagnostic` / `thyroid_electrolytes_normal` / `further_evaluation_recommended`；
- 又尝试 `REQ1`、`req-1`；
- 还尝试 quote `"Palpitations"`（归一化长度 11，低于 16）；
- 每次返回 `REFUSED: chi_state_requirement_invalid`；没有一次成功声明。

## 4. P1 失败原因

不是 requirements 门禁“误放行”，而是**契约约束对模型不可发现**：

- 工具 schema 的 `id` 只有 `{"type": "string"}`，没有 `^r[0-9]{1,2}$` 的 pattern/描述；模型自然使用描述性 id。
- schema/description 没有说明 quote 必须为 instruction 逐字子串、归一化长度 16..400；模型使用了短 quote。
- `local-state-update` 描述和 v4 guidance 没有给出 `r1..r8` 的具体格式示例；模型只能通过 `REFUSED: chi_state_requirement_invalid` 反复试错。
- 模型在 1800s 内做了 37 个请求、5.6M input tokens，仍未能声明；时间上限先到，claim 未发生。

这是 P1 的真实可用性负结果：**默认 off 是正确的；当前 on 路径的 schema/guidance 需要先修复，才能做有意义的 off/on 对照**。

## 5. 建议

1. **先修 schema/guidance 的可发现性**（新分支/新候选）：
   - `id` 增加 `pattern: "^r[0-9]{1,2}$"` 和“use r1..r8”描述；
   - `quote` 增加 `minLength: 16`、`maxLength: 400` 和“exact instruction substring”描述；
   - `note`/`evidence_call_id`/`waiver_reason` 的 done/waived 规则写进 description/guidance；
   - 可考虑在 `REFUSED` 结果中附安全、固定的字段提示（不改四个错误码）。
2. **再跑一次有界 P1 on**：新 state + 新 B（新 bundle 身份）；同一 t015、同一 1800s；观察模型是否能一次声明并闭合。不要复用当前 P1 state（无 pending，但该 attempt 已失败）。
3. **P0 结果保留**：1800s/off 的 t015 已完成；不要因为 P1 失败改写 P0 的完成结论，也不要把它写成官方通过。
4. **requirements 默认 off** 保持；在 schema/guidance 修复并通过一次 on 验证前，不进入九题候选。

## 6. 边界

- 未执行官方 Harbor、judge、患者模拟器或发布；`official_reward=null`。
- P0 的确定性检查 7/4/1，P1 相同；不是临床或官方 verdict。
- P1 失败是时间上限，不是 pending/unknown；两 state 均无 pending/halt。
- 旧 900s/429/1800b 的 pending 状态不变；本报告不处理旧 pending。
- 本报告是执行者记录，不替代独立复审。
