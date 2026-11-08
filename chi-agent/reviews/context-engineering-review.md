# context-engineering 阶段报告

日期：2026-11-08
分支：`deepseek/context-engineering-impl`
基线：`4595061125df7bb089a2cce739188faf25ad3d40`（PR78 合并）
范围：离线实现与测试；**未跑真实 B/C、judge、Trial、发布**。

## 结论

- 五项能力均有离线实现和定向测试：预算 v3、工具截断/reducer/投影、事实分层/锚点/漂移、完成门禁、检索 L0。
- 全量 `unittest discover`：**723 tests / 21 skipped / 3 个既有 import error**，无新增失败。
- 旧 v1/v2 预算与旧 journal 证据保留只读分支；新 v3 证据的 `inspect_history` 回归通过。
- bundle/runtime 身份已改变：新增 `go_chi_assembly.py`、`go_chi_completion.py`、`go_chi_index.py` 进入 `PACKAGE_FILES`；预算常量、工具 schema、锚点/完成 schema 也改变哈希。**未重建 bundle、未跑新 B。**

## 实际改动

| 模块 | 改动 |
| --- | --- |
| `scripts/go_chi_context.py` | v3 双轨预算；`DEFAULT_BUDGET` 保留 v2 只读默认，新增 `DEFAULT_BUDGET_V3`；校准函数 |
| `scripts/go_chi_policy.py` | `CONTEXT_PROFILES`（DeepSeek 1M 窗口、0.6 安全系数、3.0 floor、3.9 observed、1.5MB 上限、500k 输入预算） |
| `scripts/go_chi_entry.py` | 新 run 使用 v3；launch 写 `context_policy`；run_log 新增 upper/calibrated/observed/actual 字段；完成 v5 校验 |
| `scripts/go_chi_guard.py` | 源历史校验 + wire 投影；锚点注入；projection 元数据入 journal；summary 触发改用 `budget_pressure` |
| `scripts/go_chi_assembly.py` | 工具截断、规范 mutation 记录、列表 reducer、确定性 wire 投影 |
| `scripts/go_chi_tools.py` | 工具层截断/reducer；`max_results` clamp；`filters` L0 检索；v3 state schema |
| `scripts/go_chi_mcp.py` | MCP 结果截断/reducer；漂移检查 |
| `scripts/go_chi_search.py` | 默认 10、目录 20、单文件 50；`total_matches`/`omitted`；可操作错误 |
| `scripts/go_chi_index.py` | 内存 L0 索引、元数据过滤、hit/read-back hash 校验 |
| `scripts/go_chi_state.py` | v3 事实/目标程序独占；目标自动绑定；anchor；drift；完成证据 |
| `scripts/go_chi_contract.py` | `validate_history` 允许恰好一条 `messages[2]` 锚点 |
| `scripts/go_chi_completion.py` | payer/provider/CM 必要步骤与终态对象 |
| `scripts/go_chi_journal.py` | projection 元数据、`drift_events`、v3 run schema |
| `scripts/go_chi_runtime.py` | v3 预算、mandatory claim、anchor getter、run_log 新字段 |

## 定向测试

新增/更新：

- `tests/test_context_budget_v3.py`
- `tests/test_tool_truncation.py`
- `tests/test_context_assembly.py`
- `tests/test_context_projection_guard.py`
- `tests/test_intent_anchor.py`
- `tests/test_drift.py`
- `tests/test_completion_gate.py`
- `tests/test_retrieval_l0.py`
- `tests/test_go_chi_tools.py`（v3 schema case）

关键验证：

- v3 单位/触发线/硬门禁/旧 v2 只读；
- 8K/32KB 截断、mutation 规范记录、去重、投影确定性；
- 源历史校验不被 wire 投影改变；
- 锚点在 `messages[2]`，源历史保持不变；
- v3 模型不能写 facts/target；
- 漂移 soft/hard 与 journal `drift_events` inspect；
- 无终态对象/缺步骤/缺回读拒绝 claim；
- L0 索引过滤与 hit 回读 hash。

## 全量测试

命令：

```bash
docker run --rm --network none \
  -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts:/workspace/tests \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

结果：**Ran 723 tests, skipped 21, errors 3**。

3 个既有 import error：

- `test_dev_patient_adapter`：缺 `anthropic`
- `test_dev_patient_network`：缺 `anthropic`
- `test_role_payer_projection`：缺 `docker.types`

## 旧证据兼容

- `go_chi_context.check_budget` 保留 v1/v2 分支；旧 `chi-context-v2`/`chi-context-budget-v2` 不迁移、不重算。
- 旧 journal 没有 `projection`/`drift_events` 时按原 schema 读取；新 v3 evidence 的 `inspect_history` 已回归。
- `DEFAULT_BUDGET` 仍是 v2 legacy；新入口显式使用 `DEFAULT_BUDGET_V3`，避免旧离线调用被改写。

## 身份变化

- 新增文件进入 bundle：`scripts/go_chi_assembly.py`、`scripts/go_chi_completion.py`、`scripts/go_chi_index.py`。
- 新 schema/常量：`chi-context-v3`、`chi-context-budget-v3`、`chi-context-assembly-v1`、`chi-intent-anchor-v1`、`chi-completion-v5`、`chi-drift-event-v1`。
- 工具 schema、预算 profile、锚点/完成报告均改变 bundle/runtime 哈希。
- **必须重建 bundle 并重新取得 B 收据；本阶段没有执行。**

## 未完成 / 残余风险

- **未跑真实 B/C、judge、Trial、发布**；所有结论仅离线。
- `messages[2]` 锚点对真实 SDK/DeepSeek 的兼容性未验证；只做了离线契约/回放。
- 锚点与 `input_summary`/`output_recovery` 的组合未实现；两者默认关闭，组合场景未验证。
- wire 投影阈值使用 40%（设计文字举例 50%）；需要在开发集上用真实上下文校准。
- reducer 只保守处理 `items` 列表；详情/未知工具的字段级 reducer 未展开。
- 漂移硬规则目前覆盖未读先写（文件写/授权提交）；跨患者仍由 patient binding 负责，其他危险 mutation 未穷举。
- 完成门禁的必要步骤/终态对象按角色固定，可能过度拦截；需开发集校准。
- 240s 读超时未改；本变更不解决真实长请求超时。
- 全量测试仍有 3 个既有 import error，不属于本变更回归。

## 下一步

1. 独立复审本轮差异与测试证据。
2. 重建 bundle，生成新身份与 B；在真实运行前单独授权。
3. 先处理 240s 读超时小变更，再安排真实 C 验证。
4. 用户审核 PR 后决定合并；不 auto-merge。
