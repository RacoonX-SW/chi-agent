# 设计：恢复基于规范状态

建立：2026-11-08。来源：[proposal](proposal.md)。本文件只定义分层协议与验收边界；实现见 [plan](plan.md)，场景见 [spec](specs/recovery-on-canonical-state/spec.md)。

## 1. 四层模型

### L0 规范状态

- SDK 已接受的完整消息历史（含完整工具结果）；
- TaskState：程序事实、模型陈述、目标、未知；
- journal：请求、响应、工具证据、pending、seal；
- 这一层**永不因投影而改写**。

### L1 视图派生

- 纯函数：`(L0 历史, 策略, 锚点, 压力值) → wire body`；
- 只在轮次边界执行；
- 记录 `source_sha256`、`view_sha256`、`anchor_sha256`、投影规则版本、压力值；
- 相同输入必须产生相同 wire。

### L2 尝试

- 一次模型调用，字段：`round`、`purpose`、`source_sha256`、`view_sha256`、`anchor_sha256`、`history_length`；
- `main`、`continuation`、`summary`、`confirmation` 都记录自己的视图身份；
- continuation 必须引用它所继续的那次 attempt。

### L3 恢复

- 触发：`finish_reason=length`；
- 两种模式：
  - `partial`：冻结视图，追加 continuation 指令；要求 `view_sha256` 完全一致；
  - `regenerate`：从 L0 重新派生视图，丢弃不完整输出；记录新的 `view_sha256`；
- 受既有 `per_chain=1`、`per_run=2`、共享 50 次限制约束。

## 2. 五条时序规则

1. **压缩只在轮次边界**：length 响应后、continuation 前不得重新投影。
2. **partial 冻结视图**：锚点、占位符、预算、压力判断全部复用超时那次。
3. **regenerate 从 L0 重放**：允许视图变化，但必须记录新 view hash。
4. **视图变化禁止 partial**：`view_sha256` 不一致即拒绝，改为 regenerate 或停止。
5. **mutation 永不重放**：只重生成未执行的工具批次；已执行事实以 L0 为准。

## 3. 数据结构

### 3.1 recovery permit

```json
{
  "schema": "chi-recovery-permit-v2",
  "mode": "partial|regenerate",
  "source_sha256": "<64 hex>",
  "view_sha256": "<64 hex>",
  "parent_view_sha256": "<64 hex>",
  "anchor_sha256": "<64 hex|null>",
  "history_length": 42,
  "frozen_view": true,
  "projection_rule": "chi-context-projection-v1",
  "pressure": true
}
```

- `partial`：`frozen_view=true`，`parent_view_sha256 == view_sha256`，continuation 的 `view_sha256` 必须等于该值；
- `regenerate`：`frozen_view=false`，`parent_view_sha256` 是父 wire 的 hash，`view_sha256` 来自 `chi-context-projection-regenerate-v1`（`keep_recent_batches=1`、`project_results=True`），允许与父视图不同。

### 3.2 journal 请求条目

在现有 `projection` 字段之外，新增/复用：

- `source_sha256`、`view_sha256`、`parent_view_sha256`、`anchor_sha256`；
- `recovery_mode`、`parent_round`、`frozen_view`；
- reader 能按规则复算 `view_sha256`。

### 3.3 校验分层

| 层 | 校验 |
| --- | --- |
| L0 | `validate_history`（完整源历史、工具批次、budget feedback） |
| L1 | `validate_anchor` + 投影规则 + `view_sha256` 复算 |
| L2 | attempt 的 source/view/anchor hash 一致 |
| L3 | partial 的 view 冻结；regenerate 的新视图记录 |

## 4. 代码触点

| 模块 | 变更 |
| --- | --- |
| `go_chi_guard.py` | 投影与 recovery permit 接线；partial 校验冻结视图；regenerate 从 L0 重放 |
| `go_chi_recovery.py` | permit v2、mode 判定、视图绑定 |
| `go_chi_journal.py` | permit/请求字段、reader 复算、旧 v1 permit 兼容 |
| `go_chi_contract.py` | 源历史与视图分层校验 |
| `go_chi_entry.py` | 解除 v3 + recovery 的显式拒绝；新增策略开关 |
| `go_chi_diagnostics.py` | 新错误码与 cause |

## 5. 不变量

1. L0 不被投影改写；
2. L1 是纯函数，输入冻结后输出稳定；
3. `partial` 不改变视图；
4. `regenerate` 不重放 mutation；
5. 每次 attempt 都记录 source/view/anchor hash；
6. 视图不匹配时 fail closed，不静默换视图。

## 6. 分阶段

| 阶段 | 内容 | 行为变化 |
| --- | --- | --- |
| P1 | permit 记录 source/view/anchor hash；journal/reader 支持；不打开组合 | 无行为变化 |
| P2 | 允许 v3 + recovery：partial 冻结、regenerate 重放 | 打开组合 |
| P3 | 允许 LLM 摘要 + recovery（检查点带 hash） | 另行评估 |

## 7. 风险

| 风险 | 缓解 |
| --- | --- |
| 视图漂移 | 纯函数；锚点/压力在 attempt 开始时冻结；禁止时间/随机量 |
| 锚点兼容性 | P2 前做真实最小调用验证 `messages[2]` |
| prefix cache | partial 冻结视图，缓存友好；regenerate 允许 miss 并记录 |
| 审计复杂 | 每 attempt 记录 hash；reader 复算；失败时保留原证据 |
| mutation 重放 | 只重生成未执行批次；已执行事实以 L0 为准 |
| 旧证据 | permit v1 只读兼容，不迁移、不改写 |

## 8. 非目标

- LLM 摘要与 recovery 的组合；
- 任务级 resume；
- 向量 RAG；
- 真实 B/C、judge/Trial、发布。
