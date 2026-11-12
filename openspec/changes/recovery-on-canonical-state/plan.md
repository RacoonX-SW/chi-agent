# 执行计划：恢复基于规范状态

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

来源：[`proposal.md`](proposal.md)、[`design.md`](design.md)、[`specs/recovery-on-canonical-state/spec.md`](specs/recovery-on-canonical-state/spec.md)、[`tasks.md`](tasks.md)。本计划只展开执行步骤；**不跑真实 B/C、不授权 judge/Trial/发布、不 auto-merge**。

## 0. 目标与边界

**Goal:** 让 v3 的上下文投影与 `output_recovery` 在同一 run 内安全共存：压缩只在轮次边界，恢复只绑定规范状态和冻结视图。

**Architecture:** 四层 L0 规范状态 / L1 视图 / L2 尝试 / L3 恢复；`partial` 冻结视图，`regenerate` 从 L0 重放。

**Tech stack:** Python 3.12、Docker `chi-agent-dev:latest`、`unittest`/`pytest`、现有 `go_chi_guard`/`go_chi_recovery`/`go_chi_journal`/`go_chi_contract`。

**非目标：**

- LLM 摘要 + recovery（P3）；
- 任务级 resume；
- 向量 RAG/L1/L2；
- 真实运行与发布；
- 修改 240s 或默认 `main_max_tokens=8192`。

## 1. 施工前检查

- [ ] **Q1 partial 冻结范围**：只冻结 messages，还是也冻结 budget feedback/锚点/工具定义？建议全部冻结。
- [ ] **Q2 regenerate 的视图**：允许重新投影到更小视图，还是强制与源视图一致？建议允许，但记录新 hash。
- [ ] **Q3 permit v1 兼容**：旧 permit 无 view hash 时，是否只允许旧行为（v2）？建议是。
- [ ] **Q4 组合开关**：用 launch 字段还是 config 字段？建议 `recovery_view_policy=canonical-v1`，默认关闭。
- [ ] **Q5 视图不一致**：partial 失败后是否自动 regenerate？建议显式策略，默认停止。
- [ ] **Q6 reader 复算**：是否需要重放投影规则，还是只比对记录 hash？建议复算。

## 2. 标准测试命令

```bash
cd /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent
docker run --rm --network none \
  -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts:/workspace/tests \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

## 3. 任务

### Task 1：permit v2 与 journal 字段（P1）

**Files:** `scripts/go_chi_recovery.py`、`scripts/go_chi_journal.py`、`scripts/go_chi_guard.py`、`tests/test_go_chi_recovery_journal.py`、新增 `tests/test_recovery_view_binding.py`

- [ ] permit v2：source/view/anchor hash、history_length、frozen_view、projection_rule、pressure。
- [ ] journal 请求条目记录视图身份。
- [ ] 旧 v1 permit 只读兼容。
- [ ] 测试：字段校验、旧 permit、hash 缺失拒绝。

**Verify:** 定向 + 全量。

### Task 2：reader 复算视图 hash（P1）

**Files:** `scripts/go_chi_journal.py`、`scripts/go_chi_contract.py`、`tests/test_go_chi_journal.py`

- [ ] reader 能按投影规则复算 `view_sha256`。
- [ ] 不一致拒绝；保留原证据。
- [ ] 测试：复算一致/不一致、锚点变化、占位符变化。

**Verify:** 定向 + 全量。

### Task 3：partial 冻结视图（P2）

**Files:** `scripts/go_chi_guard.py`、`scripts/go_chi_recovery.py`、`tests/test_recovery_view_binding.py`

- [ ] continuation 必须匹配 permit 的 `view_sha256`/`anchor_sha256`。
- [ ] 视图不一致拒绝，不静默换视图。
- [ ] 测试：A1–A3、C1。

**Verify:** 定向 + 全量。

### Task 4：regenerate 从 L0 重放（P2）

**Files:** `scripts/go_chi_guard.py`、`scripts/go_chi_recovery.py`、`tests/test_recovery_view_binding.py`

- [ ] 丢弃不完整输出；从 L0 重新派生视图。
- [ ] 记录新 view hash；不重放 mutation。
- [ ] 测试：B1–B3、D1–D2。

**Verify:** 定向 + 全量。

### Task 5：组合开关与拒绝路径（P2）

**Files:** `scripts/go_chi_entry.py`、`scripts/go_chi_journal.py`、`scripts/go_chi_guard.py`、`scripts/go_chi_diagnostics.py`

- [ ] 新增 `recovery_view_policy=canonical-v1`，默认关闭。
- [ ] 未显式启用时仍拒绝 v3 + recovery。
- [ ] 新错误码与 cause。
- [ ] 测试：F1–F3、G1–G3。

**Verify:** 定向 + 全量。

### Task 6：文档、身份与复审（P2）

**Files:** `docs/go-chi-entry-runbook.md`、`README.md`、`reviews/`、`openspec/changes/recovery-on-canonical-state/`

- [ ] 更新运行手册/README：默认关闭、如何启用、残余风险。
- [ ] 身份变化说明：permit/schema/脚本进入 bundle/runtime 哈希。
- [ ] 阶段报告与独立复审。
- [ ] 用户最终合并；不 auto-merge。

## 4. 顺序与停止条件

- 顺序：Task 1 → 2 → 3 → 4 → 5 → 6。
- P1（Task 1/2）不改变行为，可先合并；P2（Task 3/4/5）打开组合。
- 任一测试未解释失败、旧 permit 不可读、视图复算不一致 → 停止并报告。
- 需要真实模型才能验证的项，停止并另立授权。
