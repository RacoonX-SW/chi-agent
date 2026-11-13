# 保留 Provider 患者确认证据

## Why

同一冻结候选的 Provider 开发评测中，八轮进入工具流程后都卡在患者确认。MCP 返回的完整候选名单有 65 人，通用结果裁剪只交付 10 人。回放显示，恢复名单后还需要补齐相似候选的病历。已记录的 86 个病历页中，53 个在分页后被再次裁剪。

## What Changes

- Provider 身份确认使用包含全部候选的精简名单。名单过大时，从同一已观察版本读取有界页面。
- Provider 病历分页按实际序列化大小决定页长，返回可接续的偏移。名单页和病历页的内容与覆盖范围可用本轮工具回执复核。
- 复验完整观察、缺页、过期版本与错误患者。用已保存的八条失败轨迹核对证据边界，再以同一 DeepSeek 模型做一次 Provider 开发复验。

## Capabilities

### New Capabilities

- `provider-observation-pagination` 规定身份确认依赖的候选名单和病历如何有界交付并核验覆盖。

### Modified Capabilities

## Impact

影响 Provider Go 入口的工具结果处理、候选与病历证据分页、工具说明及回归测试。沿用 `patient-binding` 和 `context-engineering` 的规格约定。业务写入仍由已绑定患者、订单与案件的归属校验约束。

## 审批记录

用户回复「ok，先写一下执行文档，然后修改这个，改完后再测一下Provider的」，授权实施此前给出的完整候选名单、按大小分页、缺页拒绝及单题复验范围。
