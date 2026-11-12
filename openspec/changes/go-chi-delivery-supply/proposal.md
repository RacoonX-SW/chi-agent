# Z1：Go CHI 正式配送的供应责任与离线准入

建立：2026-11-01。基于当前 `origin/main` `4ade699`（F7 尚未进入 main）。本变更只做正式配送的离线供应检查与文档；真实 Harbor Trial、真实模型和官方任务仍在 Z4/Z6，需要另行批准。

## 为什么需要

`GoChiHarness.install()` 原本是 no-op，包和依赖都由调用方预先供应；`run()` 会做无 Key 预检，但没有一个独立的“供应责任”检查器说明谁提供什么、缺失时在哪里失败。Z1 要把这件事从隐含约定变成可执行契约：

- 包、固定依赖、官方 vendor、公开资源、MCP、state/logs 由调用方/操作者供应；
- runner 只接收 `OPENCODE_API_KEY`，官方模拟器/judge 凭据不进入 runner；
- `install()` 不联网、不自动安装；缺包/缺依赖由 `run()` 的无 Key 预检失败；
- 新增 `go_chi_delivery.py`，在 Trial 启动前校验调用方供应和凭据分离。

## 范围

- `chi-go-delivery-plan-v1`：角色、bundle、model/PDF 依赖、vendor、公开资源、MCP、state/logs、history 模式、凭据名。
- `check_plan()`：bundle manifest/hash、依赖目录、vendor 源码、instruction/handbook/tool refs、MCP 角色/端口、logs 新目录、state 父目录、local/external history、凭据白名单。
- CLI `check --plan --plan-sha256`；只读、无网络、不读 Key。
- `install()` 明确为无网络 no-op；run 前预检仍是实际闸门；新增测试锁定。
- 失败路径：缺包/缺依赖/缺 vendor、错误 bundle SHA、错角色/端口、资源链接/隐藏目录、logs 已存在、state 父目录缺失、history 不匹配、凭据名错误。

## 非范围

- 不运行真实 Harbor Trial、真实模型或官方任务；历史 U 的合成 Trial 不能替代 Z1 真实配送。
- 不自动下载/安装依赖、不构建 world 镜像、不读取或保存 Key 值。
- 不改变 vendor、评分器、官方世界、账目 schema 或既有 B/账本。
- 不把 caller-owned 供应写成“stock agent 自动识别”。
