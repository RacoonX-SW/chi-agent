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

## 7. P1fix：schema/guidance 可发现性修复与第二次 P1 on

### 7.1 修复

从合并后 `origin/main=7969e32` 新建 `deepseek/requirements-discoverability`，修复提交 `47b5417a9b374a427e1e10407cfead9845c626ad`：

- `scripts/go_chi_tools.py`：`requirements` 数组增加快照说明；`id` 增加 `pattern: "^r[0-9]{1,2}$"` 及 `r1..r8` 描述；`quote` 增加 `minLength: 16`、`maxLength: 800`（归一化后 16..400）及“exact substring”描述；`status`/`evidence_call_id`/`waiver_reason`/`note` 写明 open→done/waived 的终态、来源和说明规则；`state_update_description` 同步这些约束。
- `scripts/go_chi_guidance.py`：v4 invariant 增加 `r1..r8`、`^r[0-9]{1,2}$`、quote 逐字子串/16..400（raw ≤800）。
- `tests/test_go_chi_requirements.py`：新增 schema pattern/长度/描述断言、guidance 断言和描述性 id 拒绝回归。

测试（Docker，无网）：28 requirements tests OK；129 相关 tests OK / 3 skipped；全量 654 tests、18 skipped、3 个既有 import 错误（`anthropic` ×2、`docker.types` ×1），无新增回归。

新 release：`runs/final-validation-20261105/exports/release-p1fix-20261106`；bundle `454b048ec5b52c39ccb3f0b730fdd30b5a8a5a2b750c6ee1a5bafad89b2d38fa`、release manifest `933d41368ba4dc6c1a5753335d0889ec9c5f3678b2ee9ab25cd580ec5c3c23cd`、runtime `4835ee369beb988fd6812bee78d5f2e73fc4e4c7fd1edbf5f2dd7594d2f7b3f8`；verify `valid`，preflight `identity_verified`、upstream clean。

### 7.2 B-007 与 P1fix C

| 项目 | 实际值 |
| --- | --- |
| state | `runs/final-validation-20261105/p1fix-on/state` |
| B | `final-b-007`：3 main settled、1400/118、charged 0 / list 0.00011145 / allowance 0.00006687；receipt/seal 匹配 |
| C run | `final-c-provider-t015-p1fix` / `attempt-1`；evaluation `eval-final-20261106-p1fix`；requirements on |
| 结果 | **failed / `chi_http_error`**；runner exit 1；elapsed 27.994s |
| 物理 HTTP | **2**（2 main）：round1 settled，round2 `pending` |
| round2 原因 | HTTP **429** `prefill_cap_refused`（“cell is at capacity; retry shortly (after 30 s)”），657ms，无 response |
| completion | v4 `blocked` / `not_verified`，reason `completion_requirements_undeclared`；claim null |
| requirements | `declared=false`、`count=0`、`status=undeclared`；`instruction_sha256=ae40b530…` |
| 业务进度 | 无业务写：target `case_id=null`/`patient_id=null`；provider 资源前后同为 2202 项、payer 同为 0 项；确定性检查除 `packet_absent=true` 外全 false |
| usage | input 12,699 / output 230（已知部分；round2 unsettled，billing_complete=false）；list 0.00215430 / allowance 0.00129258 / charged 0 |
| 清理 | runner/world/network removed；runner quiescent=true、world quiescence=confirmed；capture/cleanup error null |

### 7.3 结论

- **P1fix 没有走到 requirements 声明阶段**：round1 只有读取类工具事件，round2 在第一次模型调用就被提供方 429 容量拒绝；因此修复后的 schema/guidance 是否可发现**仍未在真实 on-run 中验证**。
- 这不是新的 requirements 契约失败，也不是门禁误放行；是提供方容量/传输问题。不能据此判定修复有效或无效。
- 当前 `p1fix-on` state 保留 `pending={run: final-c-provider-t015-p1fix, round: 2}`；按停止条件**未自动重试**，也未清除 pending。
- 旧 900s/429/1800b pending 仍原样保留。

### 7.4 下一步

1. 由用户决定：等待提供方恢复后使用**新 state + 新 B-008** 再跑一次有界 P1 on，或对本次 429 走显式 acknowledgement 路径；不得静默清除 `p1fix-on` 的 pending。
2. 修复代码已在新分支，建议先以 base=main 的 PR 提交修复与本节记录，供独立复审；不 merge、不启用 requirements。
3. 在至少一次 on-run 真正声明并闭合 requirements 之前，`chi-requirements-v1` 保持默认 off，不进入九题候选。
