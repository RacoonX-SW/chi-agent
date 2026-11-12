# Z6：最终候选发布包与干净环境复现（离线）

建立：2026-11-01。基于已合并 F0–F7 + Z1 的 main `6e7643c`。本变更只做发布包构建/校验，不启动真实 Harbor Trial、真实模型或官方任务。

## 为什么需要

`go_chi_bundle.py` 已经能导出内层包，但最终交付还需要一个可复核的外层：

- 绑定源码提交、内层 bundle manifest、依赖锁；
- 固定允许分发的文件清单，防止 `.env`/data/vendor/tests/runs/轨迹混入；
- 提供 SHA256SUMS，能发现构建后篡改；
- 在干净目录中校验包、依赖、资源、state/logs 和 supply plan。

Z6 的这个离线部分让“最终包是什么、由哪些字节组成、如何验证”可检查；真实干净环境启动、Harbor Trial 和模型运行仍在后续阶段。

## 范围

- `scripts/go_chi_release.py`：`build` 生成外层 release，`verify` 只读校验。
- 外层：`package/`（现有 bundle）+ `release-manifest.json` + `SHA256SUMS` + `supply-plan.example.json`。
- 校验：源码 commit、bundle manifest/文件 hash、依赖锁、顶层 allowlist、包内文件集合、SHA256SUMS、可选 supply plan。
- 测试：构建/复现、篡改、额外顶层文件、缺 manifest、plan 不匹配、已有目标拒绝、CLI。
- 不执行模型、世界、Trial；不读取真实 Key/轨迹。

## 非范围

- 不做真实 Harbor 工厂/Trial、world 镜像启动、模型请求、官方判分。
- 不签名、不做 keyless 证明；manifest/SHA 只证明字节身份，不证明来源可信或执行许可。
- 不替代 Z1 的 caller-owned supply 检查；两者互补：release 证明包字节，delivery 证明运行环境供应。
- 不把离线 `verify` 通过写成“真实干净环境启动通过”。
