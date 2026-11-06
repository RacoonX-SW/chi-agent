# Reasoning/输出预算任务清单

状态：设计文档，未实现、未运行。真实 B/C/Trial/judge/发布不在本变更内。

## 1. 代码与兼容

- [ ] 决定输出预算策略版本化方式：`chi-output-budget-v2`，或历史 8192/新 16384 双值兼容。
- [ ] `go_chi_policy.output_limit()` 主请求 8192 → 16384。
- [ ] `go_chi_runtime` 的 `ModelSettings(max_tokens=...)` 与预算校验同步。
- [ ] `go_chi_entry.CONFIG` 与 `profiles/go-chi-entry.json` 的 `chi_max_output_tokens` 同步。
- [ ] `go_chi_journal` 的 recovery/history 校验兼容旧 8192 证据，不破坏 inspect。
- [ ] 患者模拟器 8192、确认 32768、B 1024 保持不变。
- [ ] 更新测试：policy literal、runtime ModelSettings、journal 旧/新证据、recovery permit。

## 2. 测试

- [ ] 合成 length 场景：8192 仍截断；16384 给 content/tool_calls 留空间。
- [ ] 旧 run 的 8192 request/recovery evidence 仍可 inspect。
- [ ] 新 run 的 16384 request 被接受；非法 max_tokens 被拒绝。
- [ ] 定向测试 + 全量 discover；3 个既有 import error 单列。
- [ ] 不运行真实 B/C。

## 3. 单题实验（需另行授权）

- [ ] 只跑 t022 一题，主 max_tokens=16384，reasoning high，其他不变。
- [ ] 记录 reasoning_tokens/completion_tokens/finish_reason/tool_calls/耗时/usage。
- [ ] 按设计决策规则判断：保留 16384 / reasoning medium / 3 倍 + 调 read/IO。
- [ ] 不自动重跑、不换题、不换根；出现 pending/unknown 即停止。

## 4. 文档与复审

- [ ] 阶段报告：实现范围、证据、失败、未验证项。
- [ ] Gemini 独立复审；0 Blocker 后再决定合并/重建 bundle。
- [ ] 用户最终合并；不 auto-merge。

## 5. 待讨论

- [ ] 16384 是否足够；是否需要 3 倍。
- [ ] Opus 4.7 仅 judge 还是 agent；若 agent，240s read 是否调整。
- [ ] 旧证据兼容策略。
