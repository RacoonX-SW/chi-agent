# 故障处理三层实现阶段报告

日期：2026-11-07（Asia/Shanghai）。分支：`deepseek/failure-handling-impl`；PR75；base `origin/main=c88f6e5`；设计来源 PR74。**本报告是开发实现记录，不是独立复审，也不是官方分数。**

## 1. 范围

按 PR74 的三层计划实现：

- Task 1：recovery shape 允许 `name: string|null`。
- Task 2/3/4：JSON/schema 工具参数错误整批原子 REFUSED、按类/总量有界恢复、反馈安全。
- Task 5：local/MCP runtime 集成测试。
- Task 6：CM case root bootstrap。
- Task 7：文件写失败/completion 回归由既有测试覆盖，无新增生产代码。
- Task 8：connect 前重试仅完成 spike，**deferred**。
- Task 9：定向/全量 Docker 测试。
- Task 10：本报告 + REVIEW_STATE + Gemini 复审。

未包含：reasoning/输出预算（16384 实验）另见 `openspec/changes/reasoning-output-budget/`；未改生产 max_tokens。

## 2. 实际改动

### 2.1 输出契约

- `scripts/go_chi_recovery.py`：`mode_and_fragment` 允许 `name` 为 string/null；未知 key 仍拒绝。
- `scripts/go_chi_contract.py`：
  - `accept_batch(..., recover_schema=True)` 对 JSON 语法/schema 错误整批原子 REFUSED；
  - JSON 错误使用 sentinel `{"__chi_invalid_json__": True}` 仅写入 records，不执行；
  - `schema_refusals`/`json_refusals`/`total_refusals`：每类 2、总 3；第 4 次 fatal；
  - 非恢复路径保持原 `arguments_json`/`arguments_schema` fatal 行为；
  - REFUSED 原因只含工具名/字段/路径，不回显参数值。
- `scripts/go_chi_tools.py`、`scripts/go_chi_mcp.py`：wrapper 先按 `ToolContext.tool_call_id` 检查 refusal，再解析 payload；malformed JSON 不会先抛 `chi_local_arguments_invalid`/`chi_mcp_arguments_invalid`。
- 测试：`tests/test_go_chi_recovery_shape.py`、`tests/test_go_chi_contract.py`、`tests/test_go_chi_capabilities_runtime.py`。

### 2.2 CM case root bootstrap

- `scripts/go_chi_tools.py`：
  - `local-fs-write` 在 case root 缺失时，仅当 case 有 returned read 或 current target 才创建 case root/角色目录（0700）；
  - 未观察/越界/跨 case/symlink/fixture 仍拒绝；
  - provider binding / payer 路径行为不变。
- 测试：`tests/test_go_chi_tools.py` 的 CM bootstrap 正负例、既有 provider/payer 回归。

## 3. 测试证据

Docker 无网：

- 定向：`tests.test_go_chi_contract tests.test_go_chi_capabilities_runtime tests.test_go_chi_tools tests.test_go_chi_recovery_shape tests.test_go_chi_guard tests.test_go_chi_runtime` → **74 tests OK**。
- `pytest tests/test_go_chi_recovery_sdk.py` → **21 passed**。
- 全量 `unittest discover -s tests` → **675 tests、20 skipped、3 个既有 import error**（`anthropic` ×2、`docker.types` ×1），无新增回归。
- `git diff --check` 通过。

## 4. 残余风险

1. **有界恢复耗尽**：同一 run 第 4 次参数错误仍 fatal `ContractFailure`。这是有界设计，避免死循环/额度耗尽；不是静默成功。
2. **ToolContext.tool_call_id 耦合**：wrapper 拦截依赖 `_context.tool_call_id`。真实 Agent Runner 提供；若未来直接调用 wrapper 且不提供 context，malformed JSON 仍会在内部 `json.loads` 抛 `GoFailure`。已有 runtime 测试覆盖真实路径。
3. **connect 失败仍 pending**：Task 8 deferred；当前 guard 在 `journal.reserve` 之后连接，connect 超时/拒绝仍按 pending 保全账本，不自动核销。需要独立的 journal `not_sent`/零 usage 对账设计。

## 5. 未验证

- 未运行真实 B/C/Trial/judge/发布；未重建 bundle；未重跑九题。
- 未验证 reasoning/16384 实验；未验证 connect 重试。
- 旧 pending/旧 state/旧证据未改写。

## 6. 独立复审

Gemini 复审 PR75：**Pass / 0 Blocker**，建议先补本报告 + REVIEW_STATE 再合并；Task 8 必须继续 deferred，作为独立设计变更推进。

## 7. 下一步

1. 用户合并 PR75；合并后重建 bundle。
2. 九题重跑另行授权；旧 pending 不变。
3. Task 8（connect 重试）单独设计 `journal not_sent` 后再实现。
4. reasoning/16384 实验单独执行，不与本变更混合。
