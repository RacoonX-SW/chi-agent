# go-main-request-timing Specification

## Purpose
为 Go 模型主请求定义可复现的读取窗口和端到端传输上限，使等待慢响应与保留超时的账目证据都可以通过配置和离线测试复验。

## Requirements

### Requirement: Go 主请求使用固定读取与总传输预算

Go 主请求的读取超时 SHALL 为 300 秒，整次 I/O 上限 SHALL 为 360 秒。运行源码与 Go 导出配置 SHALL 对两项参数给出相同的值。

#### Scenario: 普通主模型请求发出

- **WHEN** 守卫发出主模型请求。
- **THEN** HTTP 客户端使用 300 秒读取窗口，连接、发送与完整响应读取受 360 秒整次 I/O 上限约束。

#### Scenario: 导出包校验配置

- **WHEN** 新导出包执行身份校验。
- **THEN** 包内 profile 的时间策略与运行常量匹配，验证结果绑定该包及运行身份。

#### Scenario: 主请求超时

- **WHEN** 主请求达到适用的超时上限，且客户端未收到可结算响应。
- **THEN** 当前运行记录 `chi_timeout` 并保留待结算请求和诊断证据。该请求的自动重试次数为零。
