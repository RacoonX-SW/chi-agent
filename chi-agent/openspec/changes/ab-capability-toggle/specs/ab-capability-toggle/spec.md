# 能力模式开关契约

## 需求：同一 bundle 支持受校验的能力模式

### 场景：对照组
配置 `capabilities="off"` 时，run 的 `launch.capabilities` 必须为 `null`，本地工具面不含 state/guidance/completion/search。

### 场景：实验组
未配置或 `capabilities="f0-f3-v1"` 时，行为与现状一致，`launch.capabilities="f0-f3-v1"`。

### 场景：非法值
`capabilities` 为其他值时必须拒绝配置，不得回退到默认。
