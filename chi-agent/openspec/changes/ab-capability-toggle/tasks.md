# 能力 A/B 开关执行清单

- [x] operator 配置新增可选 `capabilities`（默认 `f0-f3-v1`，允许 `off`）。
- [x] runner 映射与非法值拒绝。
- [x] 配置测试 2 个（默认/接受/拒绝）、映射测试 2 个。
- [x] Docker 全量：489 tests，2 个既有环境错误、13 skipped；controller 镜像下 operator 配置 5 tests OK。
- [ ] 外部 Gemini 复审。
- [ ] Z4 A/B：payer t011 两组（各 1 次 B + 1 次 C）。
