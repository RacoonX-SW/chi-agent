# Unattributed 业务 mutation 回读修复（2026-11-09）

范围：修复 `ce-c-baseline-002`（target 修复后 t023 正常 16384）暴露的完成门禁死锁。**只做离线代码/测试与文档；真实 C 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-baseline-002` 的 target 已正确绑定 `CASE-7D075BE2`，无 drift，业务已 finalize、发信并 portal delivered，但 `local-claim_done` 被拒：

```text
REFUSED: completion_readback_required:call_48aae7579fc647088e32d804
```

最后一次 business mutation 是 `payer_letter_center.deliver`，参数只有 `letter_id` + `channel`，observation scope 为 `unattributed`。而：

- `_completion` 要求回读 source scope 等于最后一次 mutation scope；
- target 已绑定后，`_check_source_scope` 不允许 `unattributed` 作为 `latest_business_status`。

因此 `deliver`/`reissue` 这类只有 `letter_id` 的 mutation 一旦成为最后一次业务写，就无法满足回读。模型反复 `deliver`，50 轮耗尽。

## 2. 修复

`scripts/go_chi_state.py` 的 `_completion`：

```python
if self._context_v3 and (
        source is None
        or (last.get("scope") != "unattributed"
            and source.get("scope") != last.get("scope"))):
```

- case-scoped mutation 仍要求同 case 回读；
- `unattributed` mutation 允许用 target 合法的 `business_status` 回读；
- 回读仍必须发生在 mutation 之后，且 `_apply_status` 已强制 target case/shared 范围。

用 `ce-c-baseline-002` 的真实 task-state 离线调用 `_completion()`：`(True, None, 'mechanical_pass', 'observed', None)`。

## 3. 测试

- 新增：unattributed `deliver` + 之后 case-scoped `payer_letter_center.list` → claim 通过；
- 新增：unattributed mutation 之后没有新回读 → 仍 `completion_readback_required`；
- 全量 `unittest discover`：**770 tests / 23 skipped / 3 个既有 import error**；
- 定向 `test_completion_gate` + `test_go_chi_state` + `test_drift`：**53 passed**；
- recovery pytest：**48 passed**。

3 个既有 import error 不变：`test_dev_patient_adapter`、`test_dev_patient_network`（缺 `anthropic`）、`test_role_payer_projection`（缺 `docker.types`）。

## 4. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-004`、bundle `108bf7d8…`、identity `e8f2c483…`、`ce-c-baseline-002` 都对应**修复前**代码；
- 合并后需重建 bundle + 新 B，再跑 t023 正常 16384；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 未改变 target 绑定和跨 case mutation 门禁。
- 待独立复审与用户合并；不 auto-merge。
