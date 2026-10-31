# F0–F3 能力实现与离线证据

更新：2026-11-01（Asia/Shanghai）。本报告记录 F0–F3 的实现候选、实际命令和限制；状态与权限只查 [REVIEW_STATE](REVIEW_STATE.md)。**尚未经过外部 Gemini 独立复验，也没有真实模型/任务/官方评分。**

## 1. 身份

| 项目 | 值 |
| --- | --- |
| 基线 | `443257c`（PR31 合并后的 `origin/main`） |
| 实现候选 | `a6aac1c80401ccbb815763b13bc46a9fbbf6d57f` |
| 契约候选 | `d7b9f0a`（F0–F3 契约与矩阵） |
| 分支 | `codex/f0-f3-agent-capabilities`（PR32，用户创建，未见合并） |
| 环境 | Docker `chi-agent-dev:latest`，Python 3.12.15，固定 `chi-h-root-model-deps-20261027-v1` / `chi-k-pdf-deps-20261027-v1` 卷 |

## 2. 实现范围

| 能力 | 交付 | 关键文件 |
| --- | --- | --- |
| F0 | 公开索引/工具目录的 provider/payer/CM 家族矩阵、支持状态、缺口 | `openspec/changes/agent-capabilities-f0-f3/f0-task-family-matrix.md` |
| F1 | `chi-task-state-v1`：程序观察、模型事实/计划/缺口、未知写、版本快照、原子持久化、目标/来源校验 | `scripts/go_chi_state.py` |
| F1 工具 | `local-task-state`、`local-state-update`；provider patient 绑定锁定；错 case/旧来源/冲突来源拒绝 | `scripts/go_chi_tools.py` |
| F1 接线 | MCP/本地工具观察登记；状态目录 `logs/task-state/`；不写 `chi-accounting.json` | `scripts/go_chi_mcp.py`、`scripts/go_chi_runtime.py` |
| F2 | `chi-role-guidance-v1` 三角色阶段、合法分支、停止条件；`local-role-guidance` | `scripts/go_chi_guidance.py` |
| F3 | 有界非索引检索；路径/文件/字节/结果/片段限制；隐藏/符号链接拒绝；PDF 走既有 reader | `scripts/go_chi_search.py`、`scripts/go_chi_tools.py` |
| F5 最小前移 | claim 门禁：open unknown、写后未回读、同批后续工具待处理 | `scripts/go_chi_tools.py` |

## 3. 行为要点

- 状态只从本次 run 实际发生的工具调用登记 observation；事实/最新业务状态必须引用已登记且 `event=returned` 的 call_id，程序填写 `source_seq`。
- 较旧来源不能覆盖较新 `latest_business_status`；provider 的 patient 必须已绑定且不可改绑；目标 case 必须与已观察 scope 一致。
- 写类工具 dispatch 失败登记 open unknown；只能在同目标、更晚的只读观察后 resolve；claim 不能清除。
- 写类工具成功返回后，claim 要求更晚的只读回读并更新状态；同批中 claim 之后仍有待执行工具时拒绝 claim。
- `capabilities=None` 不创建状态、不增加四个新工具、claim 保持旧行为；`go_chi_entry` 显式传 `capabilities="f0-f3-v1"`。
- 状态文件上限 64 KiB；observation 256、facts 64、plans 16、gaps 32、unknowns 16、next 8；超限/持久化失败停止或拒绝，不静默丢弃旧版本。

## 4. 实际命令与结果

全量离线套件：

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

- 候选：`Ran 414 tests`，`FAILED (errors=2, skipped=8)`。
- 基线（`443257c`，同样命令）：`Ran 382 tests`，同样 2 errors、8 skipped。
- 2 个错误均为环境缺 `anthropic`：`test_dev_patient_adapter`、`test_dev_patient_network`；不是本次代码引入。
- 新增 32 个测试：`test_go_chi_state`（12）、`test_go_chi_guidance`（5）、`test_go_chi_search`（10）、`test_go_chi_capabilities_runtime`（5）。
- 合成运行时测试实际走真实 SDK 循环、`ChiGuard`、`ToolContract`、journal 和 `httpx.MockTransport`，覆盖：指导/检索/状态读取与更新/claim 闭环、写后未回读拒绝、同批后续写拒绝、未知写登记、`capabilities=None` 旧工具集。

过程中的真实失败已修正：

1. unknown 记录缺少 `seq` 导致 resolve 时 `KeyError`；补字段后通过。
2. 新工具追加位置改变了 payer shadow 工具尾部断言；调整顺序，保留既有 shadow 行为。
3. 状态 target 断言误写为不含 `patient_id=None`；修正测试期望，不放宽实现。

## 5. 未验证项

- 未用真实 DeepSeek / 真实 CHI 任务运行；所有结果来自合成 HTTP/MCP。
- 未在真实 handbook/PDF 上验证 F3 命中质量、否定/例外条款、超大资料和提取失败路径。
- 未验证模型在真实任务中会主动使用 `local-role-guidance` / `local-task-state`；只证明工具存在且契约正确。
- claim 门禁对 payer/CM 合法结束路径的误伤率未知；若真实运行频繁被拒，需要按证据调整（例如只对 provider 强制或放宽无状态回读）。
- F0 矩阵尚未逐题抽样公开 instruction 核对；`partial` 只继承历史报告范围。
- F4–F7、Z1–Z8、真实实验、未见集、干净包和材料均未开始。
- 外部 Gemini 尚未审阅；PR32 未合并。

## 6. 下一步

1. 外部 Gemini 审查契约与实现候选，记录其是否能读 repo/diff、是否实际运行 Docker。
2. 按审查意见返工，再固定新候选。
3. 继续 F4–F6（上下文预算、完整完成证据、停滞/未知处理），再进入 Z1/Z4 的离线准备。
4. 任何真实运行仍需用户另行确认任务、候选、资源、用途、次数和停止条件。

## 7. 外部 Gemini 返工（2026-11-01）

外部 Gemini 对候选 `a6aac1c` / 文档 HEAD `7cb9cdb` 做了 Docker 离线独立复验，结论为“需修改（返工后复审）”：基线 414 tests 一致，F1 持久化/快照、F2 中立指导、兼容开关与 B 契约通过；反例攻击发现 3 项阻断与 3 项建议。

### 7.1 阻断修复

1. **claim 后跨轮写绕过**
   - `TaskState.observe()` 现在对任何 mutation 清除已记录 claim（防御层）；`block_mutation()` 在写调度前拒绝并设置 `claim_violation`。
   - `MCPBridge` 与本地工具调度层对 claim 后的写返回 `REFUSED: task_already_claimed_mutation_forbidden`，不执行服务器写。
   - `run_chi()` 在 `claim_violation` 时以 `chi_claim_violation` 结束为 incomplete；若其他路径观察到 mutation 使 state claim 清空，也会因 journal claim 与 state 不一致拒绝完成（`chi_claim_invalidated`）。
   - 有意**不**回写 `journal.run["claim_done"]`：journal 是单调证据，F1 契约要求不因新状态重写旧 claim；因此采用“拒绝写 + 标记违规 + run 失败”而不是把历史 claim 改成 false。
   - 新增测试：跨轮 claim→mutation 返回拒绝且 run 为 `incomplete/chi_claim_violation`，mutation 未到达服务器；state claim 仍在但 `claim_violation=true`；直接 mutation observation 会清 claim；`block_mutation` 单测。
2. **`local-fs-search` 其他 case 越权**
   - workspace 内路径现在必须匹配 `state.target.case_id`；target 未设定时拒绝对具体 case 目录搜索；返回 `REFUSED: search_path_outside_allowlist`。
   - 新增测试：target CASE-A 搜索 CASE-B 被拒；无 target 搜索 workspace case 被拒。
3. **单文件损坏被伪装成无匹配**
   - `search()` 增加 `single_file` 语义：单文件 stat/读取/PDF 提取失败抛 `search_unreadable`，工具层返回 `ERROR: search_unreadable`。
   - 目录不可读同样报错；目录内个别文件失败计入 `unreadable_files` 与 `skipped_files`，不静默。
   - 原 `test_unreadable_loader_is_reported_as_skipped` 改为严格断言单文件错误；新增目录计数测试、损坏 UTF-8 文件运行时测试、损坏 PDF 运行时测试。

### 7.2 非阻断改进

1. **target 未设定时的 case scope**：`_check_source_scope()` 对 case scope 来源返回 `chi_state_target_required`，避免多 case 事实混入无目标状态；新增单测。
2. **写失败 scope**：`classify_source` 扩展到 `local-fs-write/edit`；失败 observation 也解析 path 得到 `case:<ID>`；新增 `test_failed_local_write_keeps_case_scope`。
3. **状态终态 SHA-256**：`run_log.txt` 增加 `task_state_sha256`，并增加 `task_state_claim_violation`；运行时测试断言 digest 格式。

### 7.3 返工后验证

- 返工候选：`5c1fa51bdea3038d824da4e57603e39c0fddae97`。
- 定向套件：`38 tests ... OK`（state/search/tools/capabilities runtime）。
- 全量：`Ran 424 tests`，`FAILED (errors=2, skipped=8)`；2 个错误仍是既有环境缺 `anthropic`，无新增回归。
- 新测试从 32 增至 42（+10）：claim 后写、跨 case 搜索、无 target 搜索、损坏 UTF-8、损坏 PDF、target-required、写失败 scope、SHA 字段等。
- 仍未验证：真实模型是否遵守“claim 后不再写”、真实任务中检索/状态使用率、payer/CM 结束路径误伤、真实 handbook/PDF 命中质量、F0 payer/CM 逐题抽样、外部 Gemini 复审。
