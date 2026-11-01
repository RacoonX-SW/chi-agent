# 工作区写入路径约定与父目录创建

建立：2026-11-01。基于 `codex/real-run-v4` `ae2c75f`。本变更只修本地工作区写工具；不改 MCP、角色业务规则或真实运行授权。

## 为什么需要

真实 CM 003（`real-ext-cm-003`）虽 `complete`，但 `local-fs-write` 三次被拒：

- 两次路径写成 `<case>/care-manager/...`，而允许的目录是 `<case>/cm|payer|provider|shared>/...`；
- 一次 `<case>/shared/...` 返回 `ERROR: workspace parent unavailable`，因为父目录不存在且工具不创建。

Agent 因此无法交付它承诺的书面材料，只能把这条列为未完成。这是“契约只在代码里、没写进工具说明”的典型缺口，不是模型不当行为。

## 范围

- `local-fs-write` 工具描述写明路径形式：`<workspace>/<case_id>/<role>/<file>` 或 `<case_id>/shared/<file>`，`<role>` 必须是 `provider|payer|cm`。
- 角色指导（`chi-role-guidance-v1` 的 invariants）对三角色各加一条同样的约定。
- 写入时创建缺失的父目录；创建后解析路径，必须仍在工作区根内，符号链接逃逸仍拒绝。
- 失败语义不变：越权路径仍 `REFUSED`，写入错误仍 `chi_local_write_failed`。

## 非范围

- 不扩大允许目录、不引入角色别名（如 `care-manager`）。
- 不改 provider 的 patient binding 检查（写入仍需 case 已绑定）。
- 不改变工具数量、账目、判分或真实运行次数。
