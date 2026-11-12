# Z1 执行清单

当前：caller-owned 供应检查器与 install no-op 测试已完成；真实 Harbor Trial/模型仍未运行。

## 供应契约

- [x] `chi-go-delivery-plan-v1` 严格字段/路径/角色/凭据校验。
- [x] bundle manifest/SHA、model/pdf 依赖、vendor 源码、instruction/handbook/tool refs。
- [x] MCP 角色/端口/路径；state/logs；local/external history。
- [x] 凭据只允许 OPENCODE_API_KEY；其他 provider/judge 凭据列 forbidden。
- [x] `check_plan()` 只读检查与 plan SHA；CLI `check`。

## Harness

- [x] `install()` 明确为无网络 no-op；测试断言不访问 environment。
- [x] run 前无 Key 预检仍是闸门；缺包/依赖在读取 Key 前失败。
- [x] 失败/取消/返回码路径沿用既有测试。
- [ ] 真实 Harbor 工厂/Trial、world 镜像供应、state/log 持久化（Z4/Z6）。

## 验证

- [x] 定向 16 tests OK（delivery + harness）。
- [x] 全量 Docker：446 tests，2 个既有环境错误（缺 `anthropic`），8 skipped。
- [x] 外部 Gemini 复审 `a9965e5`：通过（LGTM；限离线静态/契约/Docker 合成，无真实 Trial/模型/判分）。
- [ ] F7/PR35 合并后 rebase 本分支并重跑全量（预计 461），再创建 PR。
- [ ] 与 F7 合并后重跑（当前 main 尚未包含 F7）。

## 明确不做

- [x] 不自动下载/安装依赖、不构建 world、不读 Key 值。
- [x] 不运行真实模型/官方任务/判分。
- [x] 不改变 vendor、评分器、账目 schema 或既有 B/历史。
