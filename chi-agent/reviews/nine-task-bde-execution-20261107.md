# 九题 BDE 执行记录（output recovery + 1.5M context cap + connect 30s）

日期：2026-11-07（Asia/Shanghai）。身份：source `c88f6e5`、bundle `16badf15…`、release `f97fd77d…`、runtime `05258a57…`、1800s、requirements off、`chi-output-recovery-v1`、`context_max_estimated_tokens=1500000`、`connect_seconds=30`。**本记录是开发未见验证，不是官方分数或临床通过；`official_reward=null`。**

## 1. 结果总表

| # | role | run | 结果 | 物理 HTTP | 耗时 | claim | 确定性检查 |
| ---: | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | provider | `final-c-provider-t015-bde` | **complete** | 41 | 509.5s | 已记录 | 7 true / 5 false / 1 N/A |
| 2 | provider | `final-c-provider-t016-bde` | **complete** | 41 | 442.7s | 已记录 | 7 true / 4 false / 1 N/A |
| 3 | provider | `final-c-provider-t021-bde` | **complete** | 45 | 614.4s | 已记录 | 7 true / 4 false / 1 N/A |
| 4 | payer | `final-c-payer-t022-bde` | failed / `chi_output_truncated` | 13 | 756.8s | null | 3 true / 16 false / 4 N/A |
| 5 | payer | `final-c-payer-t023-bde` | **complete** | 38 | 440.0s | 已记录 | 27 true / 0 false / 0 N/A |
| 6 | payer | `final-c-payer-t024-bde` | failed / `chi_response_invalid` | 12 | 287.1s | null | 3 true / 7 false / 11 N/A |
| 7 | cm | `final-c-cm-anorexia-bde` | complete / blocked `completion_file_write_failed` | 39 | 1271.7s | null | 2 true / 4 false / 8 N/A |
| 8 | cm | `final-c-cm-asthma-bde` | complete / blocked `completion_file_write_failed` | 45 | 530.2s | null | 14 true / 0 false / 0 N/A |
| 9 | cm | `final-c-cm-ckd-bde` | failed / `chi_tool_batch_invalid`（`arguments_json`） | 38 | 384.7s | null | 8 true / 6 false / 0 N/A |

- B-012：3 main settled、1384/109、receipt/seal 匹配；list 0.00010365 / allowance 0.00006219 / charged 0。
- C 合计：物理 HTTP **312**、input **35,044,814** / output **352,730**；list 5.18939390 / allowance 3.11363619 / charged 0。
- 无 pending/halt；所有已启动 run 的 runner/world/network removed，quiescence confirmed。

## 2. 与上一轮 nullfix 的对比

| 项 | nullfix（2026-11-06） | BDE（2026-11-07） |
| --- | --- | --- |
| complete + claim | 1（t016） | **4（t015、t016、t021、t023）** |
| complete 但 blocked | 1（t024） | 2（cm-anorexia、cm-asthma） |
| failed | 6 | 3（t022、t024、cm-ckd） |
| not_run | 1 | 0 |
| 主要失败 | 工具参数、context、output、timeout | output、response shape、JSON、file write |

本轮 A/C/B/D/E 的实际效果：

- **A**：t015 从 `put_plans` 失败变为 complete + claim；工具参数 schema 纠正生效。
- **C**：t024 不再卡 target/readback，payer target 规则生效；但出现新的 response shape 失败。
- **D**：t021 从 context budget 拦截变为 complete + claim；峰值 950,317，低于 1.5M。
- **E**：cm-asthma 不再 timeout；14 项确定性检查全 true，但被文件写失败 blocked。
- **B**：t023 从 output truncation 变为 complete + claim；t022 recovery 两次仍失败。

## 3. 失败原因分析

### 3.1 t022：`chi_output_truncated`，recovery 两次仍失败

- 13 物理 HTTP = 11 main + 2 continuation；`recovery_permits_consumed=2`。
- recovery trace：
  - round10 length → continuation11 `regenerate`，返回 3 个 tool calls（completion 5,644 / reasoning 5,365），settled；
  - round12 再次 length → continuation13 `partial`，仍 `finish_reason=length`，completion 8,192 / reasoning 8,192，content 为空。
- 根因：主请求的 8,192 output 预算被 reasoning 吃掉；第一次 recovery 成功，第二次仍被 reasoning 吃满。`chi-output-recovery-v1` 只能追加有界 continuation，不能强制模型停止 reasoning 或提高输出预算。
- 不是 context cap、不是 1800s、不是 pending。

### 3.2 t024：`chi_response_invalid`，recovery 校验不接受 `name`

- 最后响应：`finish_reason=length`，message keys 为
  `["content", "name", "reasoning_content", "role", "tool_calls"]`，其中 `name: null`，content 空、tool_calls 空。
- `go_chi_guard.py` 在 length 分支调用 `go_chi_recovery.mode_and_fragment(payload)`；该函数只允许
  `role/content/reasoning_content/tool_calls/function_call/refusal/annotations/audio`，遇到 `name` 直接 `ValueError`，guard 抛 `chi_response_invalid`。
- 根因：recovery 形状校验过严，把 OpenAI 允许的 `name: null` 当作非法；t024 因此连 recovery 机会都没有。
- 不是 target/readback 失败；C 的 target 修复已让 t024 不再卡在 `chi_state_target_invalid`。

### 3.3 cm-ckd：`chi_tool_batch_invalid`（`arguments_json`）

- 最后响应 `finish_reason=tool_calls`，调用 `cm_care_plan__save_care_plan`，arguments 长度 13,686。
- `json.loads` 在最后一个字符报 `Expecting ',' delimiter`；JSON 语法本身不合法/不完整。
- A 的可恢复路径只覆盖“JSON 合法但 schema 非法”；`arguments_json` 仍在 `_parse` 阶段直接 fatal，没有 REFUSED/纠正机会。
- 根因：模型生成 malformed JSON；系统没有 JSON 语法级兜底。

### 3.4 cm-anorexia / cm-asthma：`completion_file_write_failed`

- cm-anorexia 失败写入 `chatcmpl-tool-acfed37d49fdf646`：`ERROR: workspace parent unavailable`。
- cm-asthma 失败写入 `call_00_tlqg61u8ancfd8po9h7rvrlk`：`ERROR: workspace parent unavailable`。
- 同时有多次 `ERROR: directory is outside the role allowlist or unavailable` 的读写。
- 根因：`local-fs-write` 的目标父目录（case/role 目录）不可用或不在 allowlist；写入失败后 completion 正确 blocked。
- 不是业务状态缺失：cm-asthma 的 14 项确定性检查全 true，cm-anorexia 也有业务回读；缺的是文件交付。
- 候选修法：在 case 已绑定时允许 `local-fs-write` 创建缺失的 case/role 父目录（仍需 allowlist/binding 校验），或给出更可操作的错误并引导模型先创建目录。

## 4. 结论与候选修法

| 问题 | 根因 | 候选修法 | 优先级 |
| --- | --- | --- | --- |
| t022 output truncation | 8192 output 被 reasoning 吃满；recovery 两次仍 length | 提高主 max_tokens（如 16384）、降低 reasoning effort，或让 recovery 使用更大的输出预算 | 高 |
| t024 response_invalid | recovery 校验拒绝 `name: null` | 允许 `name` 为 string/null，或在 recovery 前剥离 `name` | 高（小修） |
| cm-ckd arguments_json | 工具参数 JSON 语法非法 | 扩展 A 到 JSON 语法错误：整批 REFUSED，返回 `chi_tool_arguments_json_invalid`，允许一次纠正 | 中 |
| cm-anorexia/asthma file write | workspace parent 不可用/越界 | case 绑定时创建缺失父目录，或改进错误提示与目录创建流程 | 中 |

## 5. 边界

- 未执行 judge、患者模拟器（官方路径）、world/Trial 或发布；`official_reward=null`。
- 确定性检查不是官方分数或临床 verdict；4 题 claim 也不等于官方通过。
- 旧 t015 round4、P1fix round2 429、旧 900s/429/1800b pending 均未改变；本轮无新 pending/halt。
- 本报告是执行者记录，不替代独立复审。
