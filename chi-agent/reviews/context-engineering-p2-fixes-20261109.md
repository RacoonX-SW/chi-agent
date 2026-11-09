# Context-engineering P2 修复报告（2026-11-09）

范围：`source-evidence-replay` 矩阵中冻结的 P2。**只做离线代码/测试与文档；未跑真实 C、judge/Trial/发布；`official_reward=null`。**

## 1. 修复项

| P2 | 处理 |
| --- | --- |
| source 存储治理 | 单 source 仍 8MB；新增 **总上限 64MB**（`MAX_SOURCE_TOTAL_BYTES`）；请求条目新增 `source_bytes`；总超限在写文件前 fail closed（`chi_source_too_large`）；source 写入后若 reserve 在提交前失败，best-effort 删除孤儿文件 |
| 测试缺口 | 新增 `returned_error` + mutation 的 v3 source 重放、redacted tool evidence fail-closed、source 总上限、孤儿清理、main 的 mode/rule 交叉校验测试 |
| 字段语义 | 删除 guard `_active_permit` 中未使用的 `parent_view_sha256`；`history_length` 明确为“视图消息数”，改名 `view_length` 因会破坏现有证据而延后（文档记录） |
| mode/rule 交叉校验 | `view_identity` 强制：main → v1、frozen=false、parent_round=null；continuation + frozen → v1；continuation + 非 frozen → regenerate；`_validate` 与 `_reserve` 一致 |
| 更广锚点兼容性 | C-002 的 t024 已接受 `messages[2]` 锚点；更广任务/模型仍是真实运行限制，离线只补测试/文档，不宣称全兼容 |

## 2. 代码触点

- `scripts/go_chi_journal.py`：
  - `MAX_SOURCE_TOTAL_BYTES = 64MB`；
  - source 写入前累计 `source_bytes` 并检查总上限；
  - reserve 失败时清理未提交的 source 文件；
  - `view_identity` 的 mode/rule/parent/frozen 交叉校验；
  - `source_bytes` 字段与校验。
- `scripts/go_chi_guard.py`：删除未使用的 `_active_permit["parent_view_sha256"]`。
- `tests/test_context_source_governance.py`（新增）。
- `tests/test_recovery_view_binding.py`（新增 replay 边界测试）。

## 3. 测试

- 全量 `unittest discover`：**761 tests / 23 skipped / 3 个既有 import error**。
- 定向：`test_context_source_governance` + `test_recovery_view_binding`：**16 passed**。
- recovery pytest：**48 passed**。
- 旧证据兼容：用新代码对 C-002 的 state 重跑 `inspect_history`，**status inspected**（旧条目无 `source_bytes`，按 legacy 读取）。

3 个既有 import error：

- `test_dev_patient_adapter`：缺 `anthropic`
- `test_dev_patient_network`：缺 `anthropic`
- `test_role_payer_projection`：缺 `docker.types`

## 4. 身份与 bundle

- 本轮代码改动会改变 bundle/runtime 身份；
- 现有 bundle `e177b452…` / identity `7e643a29…` 和 C-002 证据对应**改动前代码**；
- 未重建 bundle、未取得新 B；
- 若要用修复后代码做真实运行/最终提交包，需要新 bundle + 新 B。

## 5. 残余

1. `history_length` 改名 `view_length` 延后，避免破坏现有 v3/C-002 证据；当前文档明确其含义。
2. reader 仍不重放 source 投影的“任意 source”能力；本轮只保证已持久化 source + tool evidence 的重放。
3. 更广任务/模型的 `messages[2]` 锚点兼容性仍需真实运行证据。
4. P3、RAG/L1/L2、任务级 resume、reasoning 压缩、摘要+recovery 组合仍不在范围。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未重建 bundle、未取得新 B；未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表。
- 待独立复审与用户合并；不 auto-merge。
