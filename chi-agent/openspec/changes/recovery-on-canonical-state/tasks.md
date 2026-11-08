# 任务清单：恢复基于规范状态

状态：**P1 + P2 离线实现完成，待独立复审与用户合并。** 本清单只用于离线实现与测试；真实 B/C、judge、Trial、发布不在本变更内。

## P1：记录视图身份（不改变行为）

- [x] `go_chi_recovery.py`：新增 permit v2 字段（source/view/anchor hash、history_length、frozen_view、projection_rule、pressure）。
- [x] `go_chi_journal.py`：请求条目记录 source/view/anchor hash；旧 v1 permit 只读兼容。
- [x] `go_chi_guard.py`：每次 attempt 写入视图身份；不改变 recovery 决策。
- [x] reader：能复算 `view_sha256`；不一致拒绝。
- [x] 测试：permit v2 字段、旧 permit 兼容、reader 复算、hash 缺失拒绝。

## P2：打开 v3 + recovery

- [x] `go_chi_entry.py`：新增显式组合策略（默认关闭）；只有显式启用才允许 v3 + recovery。
- [x] `go_chi_guard.py`：`partial` 校验冻结视图；视图不一致拒绝。
- [x] `go_chi_guard.py`：`regenerate` 从 L0 重放，记录新视图。
- [x] `go_chi_recovery.py`：mode 判定与视图绑定。
- [x] `go_chi_diagnostics.py`：新错误码与 cause。
- [x] 测试：A1–A3、B1–B3、C1–C2、D1–D2、F3、G1–G3。
- [x] 文档：design/runbook/README；明确默认关闭。

## P3：摘要 + recovery（另行评估）

- [ ] 仅在 P2 有真实证据后评估；检查点带 hash；轮次边界。
- [ ] 不在本变更内实现。

## 文档与复审

- [x] 阶段报告：实现范围、证据、失败、未验证项。
- [ ] 独立复审；0 Blocker 后再谈真实运行。
- [ ] 用户最终合并；不 auto-merge。
- [ ] 重建 bundle + 新 B 后，才允许真实最小验证。

## 不在本变更内

- LLM 摘要 + recovery（P3）；
- 任务级 resume；
- 向量 RAG/L1/L2；
- 真实 B/C、judge、Trial、发布；
- 修改 240s 或默认 `main_max_tokens=8192`。

## 停止条件

- 任一测试出现未解释失败；
- 旧 v1 permit 不可读；
- 视图复算不一致且无法解释；
- 需要真实模型才能验证的项，停止并另立授权。
