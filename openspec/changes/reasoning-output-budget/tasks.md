# Reasoning/输出预算任务清单

状态：**per-run `main_max_tokens` 覆盖已实现并合并（PR76 `526fd10`，2026-11-07）**；默认仍 8192。16384 已在 t022 上获得**部分真实验证**（round1 正常，round2 被提供方 429 中断）；其余 4 题未获新证据。真实 B/C/Trial/judge/发布不在本变更内。

## 0. 实现记录（2026-11-07）

- [x] 采用按 run 的 `main_max_tokens` 覆盖，不全局改默认 8192。
- [x] `role_operator` config/`--main-max-tokens` 透传。
- [x] `go_chi_entry` parser/launch/runtime 透传。
- [x] `go_chi_runtime` 使用 override 的 `ModelSettings`/预算校验。
- [x] `go_chi_guard` 对 main/continuation 使用 override；确认/患者/B 不变。
- [x] `go_chi_journal` 记录/校验 override；旧 run 无 key 默认 8192。
- [x] 测试：override 到达 runtime/journal、config/parser、默认 8192 回归。
- [x] 全量：678 tests、21 skipped、3 个既有 import error。
- [x] PR76 已合并 `526fd10`；bundle 重建为 `11d5a5c2…`（runtime `4f797f2d…`）。

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

## 3. 单题/失败重跑实验（2026-11-07 执行，部分完成）

- [x] 5 个失败重跑 config 设 `main_max_tokens=16384`：t022、t024、cm-anorexia、cm-asthma、cm-ckd（config-set `b647e463…` / `e10b6f6a…`）。
- [x] 记录 t022 的 reasoning/completion/finish_reason/tool_calls/耗时/usage（round1：61/188/tool_calls/14.5s/19,839·188）。
- [x] 实际 wire 请求体确认 `max_tokens=16384`（`nine-rerun4` 的 `001-request.json`）。
- [ ] 全程验证：t022 round2 起被提供方 429 中断；4 次尝试均未跑完。
- [ ] t024 / cm-anorexia / cm-asthma / cm-ckd 未启动，无新证据。
- [ ] 按设计决策规则判断：保留 16384 / reasoning medium / 3 倍 + 调 read/IO（需等 429 缓解后重跑）。
- [x] 不自动重跑、不换题、不换根；出现 pending 即停止（4 个 429 pending 保留）。
- [x] 记录见 [BDE 执行记录第 6 节](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/nine-task-bde-execution-20261107.md#6-失败题重跑16384-主输出预算2026-11-07)。

## 4. 文档与复审

- [x] 阶段报告：实现范围、证据、失败、未验证项（PR76 已合并；重跑结果补入 BDE 报告第 6 节）。
- [x] Gemini 独立复审：PR75 范围 Pass/0 Blocker；PR76 由用户授权合并。
- [x] 用户最终合并 PR76；不 auto-merge。

## 5. 待讨论

- [ ] 16384 是否足够；是否需要 3 倍。
- [ ] Opus 4.7 仅 judge 还是 agent；若 agent，240s read 是否调整。
- [ ] 旧证据兼容策略（已实现双值）。
