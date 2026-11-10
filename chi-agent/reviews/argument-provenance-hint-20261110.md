# 缺失必填参数的来源提示（2026-11-10）

范围：把 asthma 暴露的“模型漏传必填标识符”抽象为通用 contract 反馈机制。**只做离线代码/测试与文档；真实 asthma 重跑在合并后另行执行；`official_reward=null`。**

## 1. 问题

CM asthma 的 `cm_outreach.send_message` 连续三次漏传 `session_id`：

```text
chi_tool_arguments_invalid: cm_outreach.send_message:
missing required field(s) session_id at $
```

模型已经在前一条 `cm_outreach.start_outreach_call` 结果里看到 `session_id=SES-6046D5EC`，但拒绝信息只给字段名，没有指出值在哪里。第三次触发 schema refusal 上限，run 失败。

## 2. 通用机制

不针对 `cm_outreach` 或 `session_id` 写死，而是在 contract 的 schema 拒绝里增加**参数来源提示**：

1. 某个必填字段缺失时，倒序扫描本 run 之前的成功工具结果；
2. 如果结果 JSON 对象里有同名字段，且值是标量（字符串/数字/布尔），把值和来源附在拒绝信息后；
3. 同一字段取最近一次结果；值最多 80 字符；
4. 不自动补全，不改变调用参数，只给模型可执行线索。

示例：

```text
chi_tool_arguments_invalid: cm_outreach.send_message:
missing required field(s) session_id at $;
observed session_id=SES-6046D5EC
from cm_outreach.start_outreach_call (call_00_...)
```

## 3. 代码触点

- `scripts/go_chi_contract.py`
  - `_schema_refusal`：缺失字段时追加 hint；
  - `_result_object`：把字符串或 text-block 结果解析为 JSON 对象；
  - `_missing_argument_hint`：倒序查找最近的成功结果，生成标量值/来源提示。
- `scripts/go_chi_guidance.py`
  - 新增 `_ARGUMENT_PROVENANCE_INVARIANT`，对所有角色交付：
    “后续工具需要前面工具返回的标识符时复用原值；被拒绝缺字段时先查前一条工具结果，不要猜。”

## 4. 边界

- 只读取模型已经看过的工具结果；不新增外发，也不把未出现过的值塞进上下文。
- 只处理 `required` 缺失字段；`enum`/`type`/`additionalProperties` 仍用原拒绝。
- 不保证模型一定修正；如果仍失败，再考虑自动补全（B 方案）或调整重试策略。
- 结果不是 JSON 或字段不是标量时不加 hint，行为与原来一致。

## 5. 测试

- `start` 返回 `session_id`，后续 `send` 缺失 → 拒绝包含值和来源；
- text-block 结果同样可解析；
- 没有历史值时只有原拒绝；
- 非 JSON 结果不崩、不产生 hint；
- 所有角色 guidance 都包含 provenance invariant；
- 全量 `dev_verify.sh --allow-dirty`：**794 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`16a6c82534c281141001d0e5c26803271d9662bb35373c75de31b90d114a5e78`；
- 新 identity：`35779d9e70030c7f0774ab071eab1a8a2cd99bd6cbe38a2253c5a4b666c69543`；
- preflight：`identity_verified`。

## 6. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-009`/bundle `ec8b3307…`/CM CKD 通过时对应修复前代码；
- 合并后需重建 bundle + 新 B，再手动重跑 asthma；
- 旧 pending 保留，不重试、不清。

## 7. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 未自动补全参数；模型仍需自己修正调用。
