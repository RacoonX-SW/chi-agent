# 恢复基于规范状态：验收场景

本文件冻结 v3 + recovery 组合的离线验收场景；实现必须逐项覆盖。真实模型/B/C/Trial/judge/发布不在本契约内。

## A. partial 冻结视图

### A1 同视图继续
- Given 一次 main 请求 `finish_reason=length`，permit 记录 `mode=partial`、`view_sha256=A`、`anchor_sha256=H`；
- When 发送 continuation；
- Then continuation 的 `view_sha256` 必须等于 `A`，锚点必须等于 `H`；通过后正常追加。

### A2 视图变化拒绝
- Given permit 记录 `view_sha256=A`；
- When continuation 的视图变成 `B`（占位符、锚点或压力判断变化）；
- Then 拒绝 `partial`，不得静默换视图；只能 `regenerate` 或停止。

### A3 锚点变化拒绝
- Given permit 记录 `anchor_sha256=H1`；
- When continuation 的锚点是 `H2`；
- Then 拒绝；锚点在 attempt 开始时冻结。

## B. regenerate 从规范状态重放

### B1 新视图记录
- Given `mode=regenerate`、`source_sha256=S`；
- When 从 L0 重新派生视图；
- Then 允许 `view_sha256` 变化，但必须记录新的 `view_sha256` 与投影规则。

### B2 不完整输出丢弃
- Given 上一次响应是 length、content 为空或 tool batch 未执行；
- When regenerate；
- Then 不把不完整片段当已完成动作；只从 L0 已接受历史重放。

### B3 上限
- Given 同一链已用 1 次、run 已用 2 次；
- When 再次触发 length；
- Then 按既有 `per_chain=1` / `per_run=2` 停止，不无限恢复。

## C. 压缩只在轮次边界

### C1 length 后不投影
- Given length 响应已返回；
- When 准备 continuation；
- Then 不得重新运行投影/reducer；视图保持冻结。

### C2 新轮次才可压缩
- Given continuation 已完成或已停止；
- When 开始新的 main 轮次；
- Then 允许按 50% 阈值重新派生视图，并记录新的 view hash。

## D. mutation 不重放

### D1 已执行 mutation
- Given 某 mutation 已在 L0 中 `returned`；
- When regenerate 或 partial；
- Then 不得重放该 mutation；只能引用已接受事实。

### D2 未执行批次
- Given 一个 tool batch 因 length 未执行；
- When regenerate；
- Then 可以重新生成该批次；不得把未执行调用当成功。

## E. 审计与 hash

### E1 每 attempt 记录
- Given 任意 main/continuation；
- When 写入 journal；
- Then 记录 `source_sha256`、`view_sha256`、`anchor_sha256`、`history_length`、`recovery_mode`。

### E2 reader 复算
- Given 旧请求证据；
- When reader 校验；
- Then 能按投影规则复算 `view_sha256` 并比对；不一致即拒绝。

### E3 旧 permit 兼容
- Given 旧 v1 permit（无 view/anchor 字段）；
- When 读取；
- Then 按旧语义只读，不迁移、不改写。

## F. 兼容

### F1 v2 不变
- Given 旧 `context_policy` 缺失或 v2；
- Then recovery 行为、schema、错误码不变。

### F2 v3 无 recovery 不变
- Given v3 且未启用 recovery；
- Then 现有投影/锚点/完成门禁行为不变。

### F3 组合需显式启用
- Given v3 + recovery；
- When 未显式启用组合策略；
- Then 仍拒绝 `chi_context_policy_incompatible`，不得默认打开。

## G. 失败关闭

### G1 缺 hash
- Given permit 缺少 `source_sha256`/`view_sha256`；
- When 校验；
- Then 拒绝，不猜测。

### G2 视图不一致
- Given partial 的视图与 permit 不一致；
- Then 拒绝并保留原证据；不自动改为 regenerate，除非显式策略允许。

### G3 证据持久化失败
- Given journal 写入失败；
- Then 停止；不得继续发送或恢复。
