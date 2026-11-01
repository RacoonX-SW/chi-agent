# Z4 方案 C：能力包 bundle 级 A/B 开关

建立：2026-11-01，基于 `origin/main` `fc7d678`。本变更只让同一个 bundle 能以两种能力模式运行，用于 Z4 的 bundle 级对照；不改生产默认行为。

## 为什么需要

F1–F6 在实现上是一个整体开关（`CAPABILITIES = {None, "f0-f3-v1"}`，生产入口硬编码 `f0-f3-v1`），无法逐机制 off/on。方案 C 因此采用 bundle 级 A/B。

但当前入口写死 `f0-f3-v1`，没有合法方式运行 `capabilities=None` 的对照条件。若为此改 bundle，会同时改变 identity，A/B 会混入身份差异。最小改动是在**开发侧**（`role_operator`/`role_runner`，不进入参赛包）提供受校验的开关，使同一 bundle、同一 identity 能跑两种模式。

## 范围

- `role_operator` 配置可选字段 `capabilities`：`f0-f3-v1`（默认）或 `off`，非法值拒绝。
- operator 把值以 `CHI_DEV_CAPABILITIES` 传给 runner；`role_runner` 映射为运行时 flag（`off`→`None`）。
- run 的 `launch.capabilities` 仍记录实际值，证据可追溯。
- 新增 4 个测试（配置校验 2 个 + 映射 2 个）。

## 非范围

- 不改 `go_chi_entry`/`go_chi_runtime` 的生产默认值，不进入参赛包。
- 不改变 bundle identity、B 收据语义或账目。
- 不拆 F1–F6 为逐机制开关。
