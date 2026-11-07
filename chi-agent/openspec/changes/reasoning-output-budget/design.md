# Reasoning/输出预算：8192 → 16384 单变量实验

建立：2026-11-07（Asia/Shanghai）。状态：**设计文档，未实现、未运行真实 B/C。** 本页只记录 t022/t024 的 reasoning 预算问题、16384 实验方案、代码触点与兼容性风险；不授权真实模型/judge/Trial/发布。

## 1. 现象

t022/t024 的 length 响应：

```text
completion_tokens = 8192
reasoning_tokens = 8192
content = ""
tool_calls = []
finish_reason = "length"
```

- t022：recovery 2 次（round10 `regenerate` 成功；round12 `partial` 仍 length）。
- t024：length 响应带 `name:null`，recovery shape 直接 `chi_response_invalid`；修 `name` 后预计走 `partial`。
- 模型在 reasoning 里做任务理解、政策权衡、工具调用计划，但没把计划变成 `tool_calls` 就撞到 8192。

## 2. 关键区分

- `reasoning_content` 是 **output token**；partial recovery 把它放进下一轮 **input**，不占下一轮 output 的 8192。
- `tool_calls` 的 arguments 也是 output token；和 reasoning 共享同一次响应的 `max_tokens`。
- 8192 是**本地 harness 策略**，不是 CHI 官方硬性要求；官方 task.toml 只规定 agent timeout 900s（submission ×2 = 1800s）。
- 官方 agent runner 没有硬编码 max_tokens；官方 judge 固定 `claude-opus-4-7`，judge timeout 900s，max output 128k。

## 3. 决策：先做 16384 单变量实验

- 主请求 `max_tokens`：8192 → **16384**。
- 保持 `reasoning_effort=high`、确认 32768、B 1024、患者 8192 不变。
- 只跑 t022 一题（或最小合成复现），不改其他任务/不跑九题。
- 记录：`reasoning_tokens`、`completion_tokens`、`finish_reason`、是否产生 `tool_calls`、实际耗时、usage/费用。

### 决策规则

- 16384 完成且有 tool_calls，reasoning 约 9–12k：保留 16384。
- 16384 仍 length，但耗时 <200s：再考虑 reasoning medium 或 3 倍；一次只改一个变量。
- 16384 已接近/超过 `main_read_seconds=240`：不要 3 倍；优先降 reasoning effort 或改 recovery 指令。
- 3 倍（24576）只有在时间余量足够、并单独评估 read/IO 上限后才考虑。

## 4. 时间估算

DeepSeek t022 最后一次 8192 output 约 119.8s，粗估 ~68 tokens/s：

| max_tokens | 理论时间（68 t/s） | 对比限制 |
| ---: | ---: | --- |
| 8192 | ~120s | 安全 |
| 16384 | ~240s | 接近 `main_read_seconds=240` |
| 24576 | ~360s | 超过 read 240s / IO 300s |

这是粗略估算，实际可能因提前停止而更短；但最坏情况要按上限评估。

Opus 4.7 的公开第三方速度（非 Anthropic 官方单一数值）：

- Artificial Analysis：Opus 4.7（non-reasoning, high）约 **45.0 tokens/s**；
- Caylent 文章：约 **81 tokens/s**（与 AA 口径/条件不同）；
- 因此可按 **45–81 t/s** 区间估算：8192 ≈ 101–182s；16384 ≈ 202–364s；24576 ≈ 303–546s。
- 官方 judge 是 Opus 4.7，timeout 900s，8192/16384 都在 judge 预算内；但 **judge 不是 agent**，240s 主请求 read 限制不适用于 judge。
- 如果未来用 Opus 4.7 作为 agent，16384 在 45 t/s 下约 364s，可能超过 240s read；需要单独评估，不要直接套 DeepSeek 的 68 t/s。

## 5. 代码触点（实现时）

- `scripts/go_chi_policy.py`：`output_limit()` 主请求 8192 → 16384。
- `scripts/go_chi_runtime.py`：`ModelSettings(max_tokens=8192)` → 16384；预算校验里的 `max_tokens` 同步。
- `scripts/go_chi_entry.py`：`CONFIG["chi_max_output_tokens"]` 8192 → 16384。
- `profiles/go-chi-entry.json`：`chi_max_output_tokens` 同步。
- `scripts/go_chi_journal.py`：recovery/history 校验里硬编码 `max_tokens == 8192` 的位置要版本化或兼容旧证据；不能直接改成 16384 导致旧 run 无法 inspect。
- `scripts/go_chi_auxiliary.py`：患者模拟器仍 8192，不随主请求改。
- bundle/runtime identity 会变化；需要新 release、新 B/state/准入。

## 6. 兼容性风险

- 旧 run 的 request/recovery evidence 里 `max_tokens=8192`；新校验如果只接受 16384，会破坏历史 inspect/recovery。
- 需要版本化输出策略（例如 `chi-output-budget-v2`）或允许历史 8192/新 16384 双值，并在 run log 记录版本。
- 旧 pending/旧 state 不能因新策略回写或重判。
- 官方 judge/任务 timeout 不受影响；但 bundle 身份变化，九题候选要重建。

## 7. 非目标

- 不改变官方 judge 模型/配置。
- 不声称 16384 一定解决 reasoning；只是单变量实验。
- 不改变输入 context budget（1.5M）。
- 不授权真实 B/C/Trial/judge/发布。

## 8. 待讨论

1. 输出预算策略是否版本化（v2）还是双值兼容。
2. 16384 实验只跑 t022，还是加一个合成 reasoning-heavy 复现。
3. 若 16384 仍 length，优先 reasoning medium 还是 3 倍 + 调 read/IO。
4. Opus 4.7 仅作 judge 还是也可能作 agent；若作 agent，240s read 是否要单独调整。
