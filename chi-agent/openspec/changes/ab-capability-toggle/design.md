# 设计：同一 bundle 的两种能力模式

## 传输路径

`role_operator` 读取配置 → `runner_env['CHI_DEV_CAPABILITIES']` → `role_runner.development()` 覆盖 `kwargs['capabilities']` → `run_chi()`。

`role_runner.capability_mode()` 是唯一映射点：

| 输入 | 运行时 flag |
| --- | --- |
| 缺省 / `f0-f3-v1` | `f0-f3-v1` |
| `off` | `None` |
| 其他 | `RuntimeError('capabilities_invalid')` |

## 为什么放在开发侧

`role_runner.py`/`role_operator.py` 是开发操作者，不进入参赛包；bundle 身份不受影响。因此 A/B 两组可以共享同一个 release 与 identity，只需各自的 state 根和 B 收据，差异只来自能力 flag。

## 证据

- 每组 run 的 `launch.capabilities` 记录实际模式；
- 配置 SHA 固定，operator 记录 config hash；
- 对照组与实验组使用相同 bundle、模型、任务、资源和 operator 超时。

## 风险

- 若 A/B 两组复用同一 state 根，会因 attempt/run 冲突被拒；两组必须不同 state。
- 该开关只影响本地工具面（state/guidance/completion/search），不影响 MCP 工具或业务规则。
