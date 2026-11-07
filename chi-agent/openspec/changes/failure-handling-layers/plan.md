# 执行计划：故障处理三层（输出契约 / 业务前置 / 连接前重试）

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

来源设计：[`design.md`](design.md)、[`specs/failure-handling-layers/spec.md`](specs/failure-handling-layers/spec.md)、[`tasks.md`](tasks.md)。本计划只展开执行步骤；**不写代码、不跑真实 B/C、不授权 judge/Trial/发布**。

## 0. 目标与边界

**Goal:** 让模型输出/工具参数错误、CM 文件写前置条件、连接前失败三类问题各有固定的有界处理路径，而不是逐题打补丁。

**Architecture:** 三层互不越权：

1. 输出契约层：校验 response shape / tool name / call id / arguments JSON / schema；整批原子 REFUSED；有界重生成。
2. 业务/工具前置层：状态/业务拒绝、CM case root bootstrap、文件写失败；completion/claim 门禁不放宽。
3. 基础设施层：只对 connect 前失败有界重试；read 超时/429/5xx/工具写继续保守停止。

**Tech stack:** Python 3.12、Docker `chi-agent-dev:latest`、`unittest`/`pytest`、现有 `go_chi_contract`/`go_chi_guard`/`go_chi_runtime`/`go_chi_tools`/`go_chi_recovery`。

**非目标：**

- reasoning/输出预算（t022）；另见 [`../reasoning-output-budget/design.md`](../reasoning-output-budget/design.md)。
- 输入 context budget（1.5M 实验）。
- 真实模型/B/C/Trial/judge/发布。
- 自动 merge、auto-merge、自动重跑九题。

## 1. 施工前检查（Brainstorming 审图结果）

以下问题必须在对应任务里先解决，不能边写边猜：

- [ ] **Q1 JSON REFUSED 路径**：JSON 语法非法时，SDK/guard/contract/wrapper 如何拿到 REFUSED，而不在 wrapper 解析阶段先抛 `GoFailure`？
- [ ] **Q2 恢复上限**：每类 2 次、每 run 3 次是否合适？同错重复是否提前停止？
- [ ] **Q3 CM case root 条件**：允许创建 case root 的“已观察/已绑定”判定用 state observations、target，还是两者都要？
- [ ] **Q4 connect 重试语义**：用 httpx 透明 retry，还是 guard 层自定义？journal/usage/pending 如何记？
- [ ] **Q5 默认开关**：输出契约恢复默认开还是受控开？connect 重试默认关闭？
- [ ] **Q6 旧行为回归**：provider/payer 文件写、合法 tool batch、off 路径必须不变。

## 2. 标准测试命令

在 `chi-agent/` 下定义一次，后续任务复用：

```bash
docker run --rm --network none \
  -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts:/workspace/tests \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python -m unittest <MODULES>
```

全量：

```bash
docker run --rm --network none \
  -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python -m unittest discover -s tests
```

已知基线：全量 665 tests、20 skipped、3 个既有 import error（`anthropic` ×2、`docker.types` ×1）。新增失败必须单独解释。

## 3. 任务

### Task 1：允许 recovery shape 中的 `name`

**Files:**
- Modify: `scripts/go_chi_recovery.py`
- Test: `tests/test_go_chi_recovery_sdk.py` 或新建 `tests/test_go_chi_recovery_shape.py`

- [ ] 写失败测试：`finish_reason=length` 的 message 含 `name: null`、`content=""`、`tool_calls=null`，`mode_and_fragment` 不得抛 `ValueError`；应进入 recovery 形状判定。
- [ ] 运行测试，确认 **FAIL**（当前会因 `name` 不在允许集合而失败）。
- [ ] 最小实现：允许 `name` 为 `str` 或 `None`；其他未知 key 仍拒绝。
- [ ] 运行测试，确认 **PASS**；再跑既有 `tests.test_go_chi_recovery_sdk`。
- [ ] 提交：`fix: allow optional message name in recovery shape`

**验收：** `name:null` 不再导致 `chi_response_invalid`；真正非法 shape 仍拒绝。

### Task 2：JSON 语法错误的可恢复路径（先 spike，后实现）

**Files:**
- Spike: `docs/` 或本计划下追加决策记录（不写生产代码）
- Modify: `scripts/go_chi_contract.py`、`scripts/go_chi_guard.py`、`scripts/go_chi_runtime.py`、`scripts/go_chi_tools.py`、`scripts/go_chi_mcp.py`
- Test: `tests/test_go_chi_contract.py`、`tests/test_go_chi_capabilities_runtime.py`

- [ ] **Spike**：在 `accept_batch(recover_schema=True)` 中比较两种方案：
  - A. 解析失败时用 sentinel `arguments={"__chi_refused__": reason}` 入 records，wrapper 先命中 refusal 再执行；
  - B. 修改 local/MCP wrapper，在解析前按 call id 检查 `contract.refusals`。
  - 记录选择、对 `validate_history`/`batches`/`records` 的影响；不写生产代码。
- [ ] 写失败测试：arguments 为 `{invalid` 的 batch → 整批 REFUSED，返回 `chi_tool_arguments_json_invalid`，无 call 执行；模型用新 call 纠正后成功。
- [ ] 运行测试，确认 **FAIL**。
- [ ] 实现 spike 选定方案；保持 `arguments_json` 在非恢复路径仍 fatal。
- [ ] 运行测试，确认 **PASS**；跑 `tests.test_go_chi_contract tests.test_go_chi_capabilities_runtime`。
- [ ] 提交：`fix: make malformed tool arguments recoverable`

**验收：** cm-ckd 类 malformed JSON 有界纠正；无半批执行；重复错误仍停止。

### Task 3：统一恢复计数与上限

**Files:**
- Modify: `scripts/go_chi_contract.py`、`scripts/go_chi_guard.py`、run log 生成处
- Test: `tests/test_go_chi_contract.py`、`tests/test_go_chi_capabilities_runtime.py`

- [ ] 写失败测试：2 次 schema + 1 次 JSON = 总 3 次；第 4 次停止；同一错误重复第二次后提前停止。
- [ ] 运行测试，确认 **FAIL**。
- [ ] 实现每类/每 run 计数；run log 暴露 `schema_refusals`/`json_refusals`/总恢复数。当前 `schema_refusals` 是 per-run 2，需迁移为 per-class + 总上限，并保留既有 2 次测试语义。
- [ ] 运行测试，确认 **PASS**。
- [ ] 提交：`fix: bound output-contract recovery per class and run`

**验收：** 不无限循环；计数可审计；达到上限安全停止。

### Task 4：反馈安全与字段提示

**Files:**
- Modify: `scripts/go_chi_contract.py`（`_schema_refusal`）
- Test: `tests/test_go_chi_contract.py`

- [ ] 写失败测试：arguments 含长文本/患者信息/未知字段；REFUSED 不含参数值/PHI/完整 schema，只含工具名、字段/路径、缺失字段/允许字段。
- [ ] 运行测试，确认 **FAIL**。
- [ ] 最小实现：只从 error.validator/path/required/additionalProperties 生成短原因；不回显 instance 值。
- [ ] 运行测试，确认 **PASS**。
- [ ] 提交：`fix: keep tool-argument feedback safe and actionable`

### Task 5：输出契约集成测试

**Files:**
- Test: `tests/test_go_chi_capabilities_runtime.py`、`tests/test_go_chi_contract.py`

- [ ] 加合成 runtime 场景：invalid JSON → REFUSED → 模型纠正 → run 继续；`name:null` length → recovery；超过总恢复上限（第 4 次）→ 安全停止。
- [ ] 运行测试，确认 **PASS**。
- [ ] 提交：`test: cover output-contract recovery end to end`

### Task 6：CM case root bootstrap

**Files:**
- Modify: `scripts/go_chi_tools.py`（`write_file`）、可能 `scripts/go_chi_resources.py`
- Test: `tests/test_go_chi_tools.py`

- [ ] 写失败测试：CM state 有 target/observation，workspace 只有根目录，写 `CM-CASE-.../cm/note.md` → 成功并创建 case root/role 目录。
- [ ] 运行测试，确认 **FAIL**（当前 `workspace parent unavailable`）。
- [ ] 实现：case 已观察/绑定 + allowlist + 非 symlink/隐藏/fixture 时，创建 case root（0700）和父目录，再写。
- [ ] 运行测试，确认 **PASS**。
- [ ] 加负例：未观察 case、跨 case、越界、symlink → 拒绝且不创建目录。
- [ ] 提交：`fix: bootstrap CM case root for workspace writes`

**验收：** cm-anorexia/cm-asthma 类文件写不再因 case root 缺失失败；越界仍拒绝。

### Task 7：文件写失败/completion 回归

**Files:**
- Test: `tests/test_go_chi_tools.py`、`tests/test_go_chi_state.py` 或 runtime

- [ ] 加测试：文件写失败 → `completion_file_write_failed`；同路径成功写修复；无关路径/未解决 unknown 仍阻断；不得 claim。
- [ ] 运行测试，确认 **PASS**。
- [ ] 提交：`test: keep file-write failures blocking completion`

### Task 8：connect 前重试（先 spike）

**Files:**
- Spike: 本计划追加决策记录
- Modify: `scripts/go_chi_guard.py` 或新 transport wrapper；`scripts/go_chi_entry.py` 开关
- Test: `tests/test_go_chi_guard.py`、`tests/test_go_chi_runtime.py`

- [ ] **Spike**：比较 httpx 透明 `retries` vs 自定义 connect-retry wrapper；确认只捕获 connect 前异常，不重试 read timeout/429/5xx；记录 journal/usage/pending 方案。
- [ ] 写失败测试：lower transport 连续抛 `httpx.ConnectError` 两次后成功 → 有界重试成功；不产生 usage/pending。
- [ ] 运行测试，确认 **FAIL**。
- [ ] 实现选定方案；默认关闭/单独开关；最多 N 次、退避、受总预算约束。
- [ ] 加负例：read timeout/断连、429、工具/业务写 → 不重试；pending/unknown 保留。
- [ ] 运行测试，确认 **PASS**。
- [ ] 提交：`fix: add bounded connect-before-send retry`

**验收：** 只重试连接前失败；不重复业务写；不把 unknown 变成功。

### Task 9：定向与全量验证

- [ ] 运行定向：`tests.test_go_chi_contract tests.test_go_chi_tools tests.test_go_chi_guard tests.test_go_chi_runtime tests.test_go_chi_capabilities_runtime tests.test_go_chi_recovery_sdk`。
- [ ] 运行 `pytest tests/test_c4_policy_boundaries.py`（如涉及 policy/transport）。
- [ ] 运行全量 `unittest discover -s tests`；记录 3 个既有 import error。
- [ ] 不运行真实 B/C；不新增 pending；不改旧 state。
- [ ] 提交：`test: verify failure-handling layers in Docker`

### Task 10：文档与独立复审

- [ ] 更新 `reviews/REVIEW_STATE.md` 短状态与报告链接。
- [ ] 写阶段报告：实现范围、证据、失败、未验证项、复审重点。
- [ ] Gemini 独立复审；0 Blocker 后再决定是否合并。
- [ ] 用户最终合并；不 auto-merge。
- [ ] 合并后才重建 bundle；真实九题重跑需另行批准。

## 4. Verification-before-completion

完成前必须提供：

- [ ] 每个任务的 RED 输出（测试先失败）和 GREEN 输出（测试通过）。
- [ ] 定向测试命令 + 实际 passed/skipped/errors。
- [ ] 全量测试命令 + 3 个既有 import error 单列。
- [ ] `git diff --check`、分支、HEAD。
- [ ] 没有真实 B/C、没有新 pending、没有旧 state 改写。
- [ ] 失败/未验证项明确列出，不用“应该”“感觉”代替证据。

## 5. 复审重点

- 输出契约：整批原子性、JSON REFUSED 是否真的不执行、恢复上限、反馈安全。
- 业务前置：CM case root 创建是否只在已观察/绑定 + allowlist 内；provider/payer 是否回归。
- 基础设施：是否只重试 connect 前失败；read timeout/429/工具写是否绝不重试；usage/pending 是否正确。
- 文档：是否把设计写成已实现/已验证；是否越界到 reasoning/官方成绩。
