# Z6 执行清单（离线发布包）

当前：release wrapper 构建/校验已实现并自测；真实干净环境/Harbor Trial 未运行。

## 发布包

- [x] 外层 `package/` + `release-manifest.json` + `SHA256SUMS` + supply plan 模板。
- [x] 顶层/包内 allowlist；禁止 data/vendor/tests/runs/.env/符号链接。
- [x] source commit、bundle manifest、entry config、依赖锁、文件 hash。
- [x] 确定性构建；目标存在拒绝；失败删除本次 target。
- [x] verify：bundle 身份、文件集合、SHA256SUMS、可选 supply plan。
- [x] CLI build/verify。

## 验证

- [x] 5 个合成测试：构建/plan、篡改/额外布局、缺 manifest/plan 不匹配、确定性/CLI、目标已存在。
- [x] 全量 Docker：466 tests，2 个既有环境错误（缺 `anthropic`），8 skipped。
- [x] 外部 Gemini 复审 `ccdf8f2`：通过（LGTM；限离线发布包/合成构建，无真实 Trial/模型/判分）。
- [ ] 真实干净依赖安装/空状态、Harbor Trial、真实模型、清理（Z6 真实部分）。

## 明确不做

- [x] 不启动模型/世界/Trial、不读取 Key/真实轨迹。
- [x] 不签名；SHA/manifest 只证明字节身份，不证明来源可信或执行许可。
- [x] 不替代 Z1 delivery check 或真实 Z6 启动。
