# 执行计划：上下文工程与执行可靠性

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

来源：[`proposal.md`](proposal.md)、[`design.md`](design.md)、[`specs/context-engineering/spec.md`](specs/context-engineering/spec.md)、[`tasks.md`](tasks.md)。本计划只展开执行步骤；**不跑真实 B/C、不授权 judge/Trial/发布、不 auto-merge**。

## 0. 目标与边界

**Goal:** 把上下文从“整段历史直接塞给模型”改成“预算明确、分层装配、状态可锚定、完成有证据”的运行时流程。

**Architecture:** 五个独立但按依赖排序的能力：

1. 预算 v3：token/字节双轨、模型 profile、校准；
2. 装配：工具层截断 + reducer + 去重 + 占位符；
3. 状态：事实分层 + 意图锚点 + 漂移检测；
4. 完成门禁：强制 claim + 程序推导证据；
5. 检索 L0：结构化关键词检索。

**Tech stack:** Python 3.12、Docker `chi-agent-dev:latest`、`unittest`/`pytest`、现有 `go_chi_*` 模块。

**非目标：**

- 240s 读超时覆盖（另立小变更）；
- 向量 RAG / L1 / L2；
- 任务级 resume；
- LLM 摘要与 recovery 的组合；
- 真实运行与发布。

## 1. 施工前检查（Brainstorming 审图结果）

- [x] **Q1 投影位置**：read 占位符放在 guard 的 wire 投影，还是 contract？需确认 `validate_history` 的输入是源历史还是投影。
- [x] **Q2 锚点位置**：`messages[2]` 是否与 SDK/DeepSeek 兼容？先写离线回放验证。
- [x] **Q3 mutation 规范记录**：哪些字段是“程序可推导”的？列出每类 mutation 的 key_ids。
- [x] **Q4 完成证据 schema**：payer/provider/CM 各自的终态对象与必要步骤清单。
- [x] **Q5 max_results 单文件上限**：50 是否会破坏 context 预算？与 8K 截断如何叠加。
- [x] **Q6 身份变化**：哪些常量/schema 进入 bundle/runtime 身份；旧证据如何只读兼容。

结论与实施取舍见 [decisions.md](decisions.md)；阶段证据见 [报告](../../../reviews/context-engineering-review.md)。

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

定向测试按任务列出；全量 discover 记录既有 import error，不把它们算成本次回归。

## 3. 任务

### Task 1：预算模型 v3

**Files:** `scripts/go_chi_context.py`、`scripts/go_chi_policy.py`、`scripts/go_chi_entry.py`、`scripts/go_chi_journal.py`、`tests/test_summary_budget_v2.py`、新增 `tests/test_context_budget_v3.py`

- [ ] 新增 `chi-context-v3`：`total_bytes`、`estimated_tokens_upper`、`estimated_tokens_calibrated`、`bytes_per_token_actual`。
- [ ] 删除 `max_chars`；硬门禁 `U ≤ max_input_tokens` 且 `bytes ≤ max_context_bytes`。
- [ ] 触发线 `U ≥ 0.8 × max_input_tokens`。
- [ ] 模型 profile：`provider_context_tokens`、`window_safety_fraction`、`bytes_per_token_floor`、`bytes_per_token_observed`。
- [ ] 启动校验：运行时模型与 profile 不一致 → fail closed。
- [ ] 旧 v2 只读兼容。
- [ ] 测试：边界、单位、profile、旧证据、极端输入。

**Verify:** 新增测试 + `tests.test_summary_budget_v2` + 全量 discover。

### Task 2：工具层截断与 max_results

**Files:** `scripts/go_chi_tools.py`、`scripts/go_chi_search.py`、`tests/test_go_chi_tools.py`、新增 `tests/test_tool_truncation.py`

- [ ] 文本类结果 ≤ 8K 码点且 ≤ 32KB 字节；头 4096 + 尾 1024 + `truncated`/`next_offset`。
- [ ] 完整结果先写 evidence，再返回截断版。
- [ ] `max_results`：默认 10、上限 20、单文件 50；`total_matches`/`omitted`。
- [ ] 可操作错误；同类重复 2 次后 clamp 并记录 `requested`/`effective`/`capped`。
- [ ] 路径/ID/mutation 参数永不 clamp。
- [ ] 测试：截断边界、evidence 完整性、单文件/目录上限、重复违反。

**Verify:** 定向 + 全量。

### Task 3：reducer、去重与 wire 投影

**Files:** `scripts/go_chi_guard.py`、`scripts/go_chi_tools.py`、`scripts/go_chi_journal.py`、新增 `scripts/go_chi_assembly.py`、新增 `tests/test_context_assembly.py`

- [ ] reducer：列表/详情/数组/未知工具。
- [ ] 去重：`result_sha256` 相同只留一份。
- [ ] read 占位符；mutation/refused/failed 规范记录。
- [ ] 分类复用 `go_chi_recovery.READ/MUTATION`。
- [ ] 投影 hash 写入 journal；确定性校验。
- [ ] 只在阈值以上启用投影。
- [ ] 测试：reducer 合法性、占位符可回读、mutation 不被替换、确定性、阈值。

**Verify:** 定向 + 全量。

### Task 4：事实分层与意图锚点

**Files:** `scripts/go_chi_state.py`、`scripts/go_chi_contract.py`、`scripts/go_chi_tools.py`、`scripts/go_chi_guard.py`、`tests/test_go_chi_state.py`、新增 `tests/test_intent_anchor.py`

- [ ] 状态项记录来源（program/model）；`local-state-update` 只能写 L2。
- [ ] 锚点生成与 `anchor_sha256`；`messages[2]` 注入；阶段切换更新。
- [ ] `validate_history` 允许恰好一条锚点。
- [ ] recovery/summary 保留锚点。
- [ ] 测试：缺失/重复/hash 不符、事实越权、阶段推进。

**Verify:** 定向 + 全量。

### Task 5：漂移检测

**Files:** `scripts/go_chi_guard.py`、`scripts/go_chi_tools.py`、`scripts/go_chi_journal.py`、新增 `tests/test_drift.py`

- [ ] 硬违规：跨患者、目标不符、禁用工具、未读先写、危险 mutation。
- [ ] 软漂移：重复同工具同参数、多余刷新、非破坏性步骤倒退；复用 `refuse_tool`。
- [ ] 同类 2 次、run 内 3 次上限；超过硬停止。
- [ ] journal 记录规则名、call_id、次数。
- [ ] 测试：硬/软分类、警告上限、正常路径回归。

**Verify:** 定向 + 全量。

### Task 6：完成门禁

**Files:** `scripts/go_chi_entry.py`、`scripts/go_chi_state.py`、`scripts/go_chi_contract.py`、新增 `scripts/go_chi_completion.py`、新增 `tests/test_completion_gate.py`

- [ ] `mandatory_claim`：无 claim 的最终文本 → `incomplete`。
- [ ] 证据由程序推导；模型引用不作证据。
- [ ] 执行/验证分离；终态 mutation 必须回读。
- [ ] 负证据：必要步骤缺失即 block。
- [ ] 终态对象：payer/provider/CM/拒绝类。
- [ ] 测试：无 claim、假 claim、缺回读、缺步骤、无动作结局、正常回归。

**Verify:** 定向 + 全量。

### Task 7：检索 L0

**Files:** `scripts/go_chi_search.py`、`scripts/go_chi_tools.py`、新增 `scripts/go_chi_index.py`、新增 `tests/test_retrieval_l0.py`

- [ ] 目录/标题/章节索引（1,279 md + 11 pdf）。
- [ ] 元数据过滤：role、category、年份、服务、文档类型。
- [ ] 命中返回 path/行/章节/hash；引用前回读。
- [ ] 测试：索引一致性、过滤、回读、无效参数。

**Verify:** 定向 + 全量。

### Task 8：兼容、文档与复审

**Files:** `docs/go-chi-entry-runbook.md`、`docs/learning-agreement.md`、`reviews/`、`README.md`

- [ ] 旧 v2 证据 inspect 回归。
- [ ] bundle/runtime 身份变化说明与重建步骤。
- [ ] 阶段报告：实现范围、证据、失败、未验证项。
- [ ] 独立复审；0 Blocker 后再谈真实运行。
- [ ] 用户最终合并；不 auto-merge。

## 4. 顺序与停止条件

- 顺序：Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8。
- Task 2/3 可并行评审但同一工作区只允许一个写入者。
- 任一任务出现未解释失败、旧证据不可读、身份校验失败 → 停止并报告。
- 需要真实模型才能验证的项，停止并另立授权。
