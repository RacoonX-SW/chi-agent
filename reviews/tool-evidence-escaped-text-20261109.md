# Tool evidence 保留非 JSON 反斜杠文本（2026-11-09）

范围：修复 t022 通过运行暴露的 `inspect_history` 失败。**只做离线代码/测试与文档；真实 t022 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-t022-rerun-002`（t022 payer，正常 16384）：

- **complete + claim**；
- 43 main settled，target `CASE-27EFB677`，drift/recovery/pending 0；
- 但 `inspect_history` 报 `chi_view_source_mismatch`。

逐轮重放定位到 round 11：两个 `local-fs-read` 结果（policy/PDF 文本）含 `\*`，被 tool evidence 写入器标为：

```text
redaction = unparseable_escaped_body
body_utf8 = null
```

`_replay_source_view` 需要原始结果正文，遇到 `body_utf8=null` 即失败。运行本身完成，但证据不可 audit。

## 2. 根因

`write_tool` 对非 JSON 文本执行：

```python
except Exception:
    if "\\" in result:
        doc["redaction"] = "unparseable_escaped_body"
```

任何含反斜杠的普通文本（policy 的 `\*`、PDF 文本）都会被清空正文。该启发式过宽。

## 3. 修复

非 JSON 文本仍先用原始字符串做 secret 扫描；安全时**逐字保存** `body_utf8`，不再因反斜杠清空。JSON 结果仍做解析后的 secret 扫描；`body_too_large` 与 `secret_detected` 保持原语义。

## 4. 测试

- 新增：含 `\*` 的 tool 结果保存 `body_utf8` 且 `redaction=null`；
- 新增：同一文本经 `_replay_source_view` 重放成功；
- 保留：`body_too_large` 的 redacted evidence 仍 fail-closed；
- 全量 `dev_verify.sh --allow-dirty`：**785 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`eedb73d814f281c48cffdffb7575a122f7652ca033575283b1ead160a590c2d5`；
- 新 identity：`25a3eab3d43a4c88a6eeacf90544efaadc38a154979613241d3d5a138ab5af78`；
- preflight：`identity_verified`。

## 5. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-006`/bundle `64a1c05d…`/`ce-c-t022-rerun-002` 对应修复前代码；
- 合并后需重建 bundle + 新 B，再重跑 t022，才能得到 inspect 通过的基线；
- 旧 pending 保留，不重试、不清。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 仍不保存 `body_too_large` 的 >8MB 工具正文；此类 run 的 replay 仍 fail-closed。
