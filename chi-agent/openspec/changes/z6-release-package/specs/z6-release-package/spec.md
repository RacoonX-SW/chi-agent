# Z6 发布包行为契约

本契约覆盖离线 release 构建/校验；不授予真实 Trial、模型或官方判分。

## 需求：发布包只含允许内容

### 场景：构建

给定源码根、目标不存在、合法 source commit，build 生成 `package/`、`release-manifest.json`、`SHA256SUMS`、`supply-plan.example.json`。顶层只允许这四项；`package/` 只允许 bundle 文件 + manifest。失败删除本次 target，不覆盖已有目录。

### 场景：确定性

相同源码和 source commit 的两次构建产生相同 release manifest 和 SHA256SUMS；不写时间戳/宿主路径/凭据。

### 场景：禁止内容

`.env`、data、vendor、tests、runs、reviews、openspec、docs 或符号链接不得出现在 release 顶层；包内额外文件、额外顶层文件、缺失 manifest 均拒绝。

## 需求：字节身份可复核

### 场景：bundle 与依赖锁

verify 调用内层 `validate_bundle()`；manifest 的 bundle/entry config/file hashes 与内层一致；model/PDF 锁 hash 与包内文件一致。

### 场景：篡改

构建后修改包内文件、删 manifest、改 SHA256SUMS 或增加额外文件，verify 必须失败并给稳定 code；不能把篡改包当有效发布。

## 需求：可选 supply plan 不得掩盖环境缺失

### 场景：plan 匹配

提供 plan 时，`check_plan()` 必须通过，且 plan 的 bundle root 解析到 `<release>/package`；否则拒绝。release verify 通过只证明包字节，不证明依赖实际可导入、world/MCP 可用或模型可调用。

### 场景：真实干净环境

真实 Z6 仍需空依赖安装、空状态目录、world/公开输入/MCP、真实模型、日志/trajectory、状态回收和 owned 资源清理；离线 verify 不得写成真实启动通过。
