# Schema/total 拒绝上限 3/4（2026-11-11）

范围：asthma rerun-006 仍在 `session_id` 上触发 schema 上限；增加一次带 provenance hint 的纠正机会。**只做离线代码/测试与文档；真实 asthma 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-cm-asthma-rerun-006`：

- 16 main + 3 patient_simulator；
- 两次 `send_message` 漏 `session_id`，拒绝信息已带：

```text
observed session_id=SES-293E72FF
from cm_outreach__start_outreach_call (chatcmpl-tool-9c76c86b3c75ef47)
```

- 模型第三次仍漏传，达到 `RECOVERABLE_SCHEMA_LIMIT=2` / `RECOVERABLE_TOTAL_LIMIT=3`，`chi_tool_batch_invalid`；
- target 正确，drift/recovery/pending 0，cleanup confirmed，未 claim。

## 2. 修复

`ToolContract`：

```python
RECOVERABLE_SCHEMA_LIMIT = 3   # was 2
RECOVERABLE_JSON_LIMIT = 2
RECOVERABLE_TOTAL_LIMIT = 4    # was 3
```

含义：

- 同一 schema 类错误最多 3 次带提示的拒绝；
- 所有可恢复错误合计最多 4 次；
- 超过后仍按原设计 fail-closed，不是无限重试。

这样模型在第二次漏传后还有一次带 `session_id=...` 的纠正机会。

## 3. 测试

- `test_schema_refusal_is_bounded` 随 schema limit 自适应；
- `test_total_recovery_limit_spans_schema_and_json` 改为 schema limit + 1 JSON = total limit，再下一次失败；
- 定向 `tests/test_go_chi_contract.py`：**18 passed**；
- 全量 `dev_verify.sh --allow-dirty`：**795 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`d0258448e1c2ed9035823fe6d8836531f0672c5f94ccb5c16df301219c34d0d9`；
- 新 identity：`1de8800c270dea8f5c07e52352947cc7e5d744bfcb20505f228141c41dfb5e36`；
- preflight：`identity_verified`。

## 4. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-011`/bundle `100a5001…`/asthma rerun-006 对应修复前代码；
- 合并后需重建 bundle + 新 B，再手动重跑 asthma；
- 旧 pending 保留，不重试、不清。

## 5. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 不自动补全参数；只是多一次带 provenance hint 的纠正机会。
