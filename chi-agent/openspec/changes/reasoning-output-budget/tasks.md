# Reasoning/输出预算任务清单

状态：**per-run `main_max_tokens` 覆盖已实现（2026-11-07）**；默认仍 8192；单题实验未运行。真实 B/C/Trial/judge/发布不在本变更内。

## 0. 实现记录（2026-11-07）

- [x] 采用按 run 的 `main_max_tokens` 覆盖，不全局改默认 8192。
- [x] `role_operator` config/`--main-max-tokens` 透传。
- [x] `go_chi_entry` parser/launch/runtime 透传。
- [x] `go_chi_runtime` 使用 override 的 `ModelSettings`/预算校验。
- [x] `go_chi_guard` 对 main/continuation 使用 override；确认/患者/B 不变。
- [x] `go_chi_journal` 记录/校验 override；旧 run 无 key 默认 8192。
- [x] 测试：override 到达 runtime/journal、config/parser、默认 8192 回归。
- [x] 全量：678 tests、21 skipped、3 个既有 import error。
- [ ] 单题实验：5 个失败重跑 config 设 16384，需用户合并后运行。

## 1. 代码与兼容

- [x] 输出预算策略采用 per-run override，历史 8192/新 16384 双值兼容。
- [x] `go_chi_runtime` 的 `ModelSettings(max_tokens=...)` 与预算校验同步。
- [x] `go_chi_entry` 与 `role_operator` 的 `main_max_tokens` 透传。
- [x] `go_chi_journal` 的 recovery/history 校验兼容旧 8192 证据，不破坏 inspect。
- [x] 患者模拟器 8192、确认 32768、B 1024 保持不变。
- [x] 更新测试：config/parser/runtime/journal、默认 8192 回归。

## 2. 测试

- [x] 合成 override：main request 16384 到达 runtime/journal；默认 8192 不变。
- [x] 旧 run 的 8192 request/recovery evidence 仍可 inspect（兼容逻辑）。
- [x] 非法 max_tokens 被拒绝。
- [x] 定向测试 + 全量 discover；3 个既有 import error 单列。
- [x] 不运行真实 B/C。

## 3. 单题/失败重跑实验（需另行授权）

- [ ] 5 个失败重跑 config 设 `main_max_tokens=16384`：t022、t024、cm-anorexia、cm-asthma、cm-ckd。
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
- [ ] 旧证据兼容策略（已实现双值）。
