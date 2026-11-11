# Auxiliary v3 预算修复（2026-11-10）

范围：修复 CM anorexia 重跑暴露的 patient simulator 预算误判。**只做离线代码/测试与文档；真实 CM 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-cm-anorexia-rerun-001`（CM，正常 16384）在 18 个 main 请求后失败：

```text
chi_context_budget_invalid
```

context.jsonl 显示最后请求 raw 253 KB、estimated upper 84k tokens，远低于 1.5 MB / 500k 限制，不是实际超限。

## 2. 根因

`AuxiliaryTransport.handle_async_request`：

```python
metric = measure_request(body, raw)
blocked = check_budget(metric, self.context_limit)
```

`measure_request` 未传 budget，返回 **legacy v2 metric**；而 `self.context_limit` 是 v3 budget。`check_budget` 发现 metric/budget schema 不匹配，返回 `chi_context_budget_invalid`。payer/provider 任务不使用 patient simulator，所以此前未触发；CM 的 `cm_outreach` 请求首次暴露。

## 3. 修复

```python
metric = measure_request(body, raw, self.context_limit)
```

辅助请求与主请求使用同一 v3 metric 语义；预算不足仍返回 `chi_context_budget_exceeded`，其余校验不变。

## 4. 测试

- 新增：`AuxiliaryTransport` 使用 `budget_from_bytes(1500000, DEFAULT_BUDGET_V3)` 时请求成功；
- 原有 v2 预算超限测试保持通过；
- 定向 `tests/test_go_chi_auxiliary.py`：**16 passed**；
- 全量 `dev_verify.sh --allow-dirty`：**785 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`20b4dd75fd22c62819cf0d1aa095f4835c57cee2989f073d615adb7f811dff1b`；
- 新 identity：`75e572b653afd1bca44ad5624b6616342d7b2d7b14e75b01cfcc60d626b5db26`；
- preflight：`identity_verified`。

## 5. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-007`/bundle `eedb73d8…`/`ce-c-cm-anorexia-rerun-001` 对应修复前代码；
- 合并后需重建 bundle + 新 B，再按顺序重跑 CM anorexia/asthma/ckd；
- 旧 pending 保留，不重试、不清。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 只修预算 metric 传递；不改变 auxiliary 的模型、工具或业务语义。
