# Provider 新转诊提交前门禁

## Why

Provider t016 的开发复验已完成患者绑定和建案。Agent 以开单门诊推断检查地点，又根据表单与提交包的完整性标记直接提交。原完成检查接受了成功提交和同案回查，确定性检查通过 6/11。

## What Changes

- Go Provider 新转诊在建案前核对实际服务地点的公开依据。
- Agent 在打包前记录有来源的证据判断和 Provider 决定。程序在 MCP 派发前按已确认分支检查打包及提交。
- 完成检查核对决定回执、同案结构化终态及相应提交产物。
- 用合成轨迹覆盖三个分支、地点缺据和就绪标记导致的错误提交。

## Capabilities

### New Capabilities

- `provider-pre-submission` 规定新转诊的地点证据、提交前决定、派发门禁和完成回查。

### Modified Capabilities

## Impact

涉及 Go Provider 的状态、意图锚点、现有本地状态更新、MCP 派发及完成检查。沿用患者绑定、公开资料和评测侧证据隔离约定。验证使用禁网 Docker 与合成回放，真实模型复测作为独立事项。

## 审批记录

用户在看到三分支、服务地点证据和离线回放方案后回复「可以的，按照这个来修复一下」。本 Change 将该方案落实到 Go Provider 新转诊。
