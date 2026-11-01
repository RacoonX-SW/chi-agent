# F7 执行清单

当前：离线实现候选 `fd617c3` 已完成，待外部 Gemini 复审；未运行真实实验。

## Manifest

- [x] `chi-experiment-campaign-v1` 严格字段校验，未知字段拒绝。
- [x] F1–F6 mechanism、off/on/na 模式、off/on 同任务/同 limits、na reason。
- [x] 任务/角色/attempt/资源 hash/世界镜像/检查/上限/停止条件固定。
- [x] 规范化 JSON + SHA-256 freeze。
- [x] CLI validate/freeze。

## Record 与 Summary

- [x] `chi-experiment-record-v1` 严格字段、candidate 一致、计划内/唯一记录。
- [x] 全分母：planned/attempted/completed/failed/skipped/blocked/not_run/missing_evidence。
- [x] checks pass/fail/na/not_run；NA/跳过/缺日志不补 pass。
- [x] usage known sum + missing count；official reward 只保留/缺失计数。
- [x] failure code 计数、by_role 计划/未运行分母。
- [x] off/on 只并列，不计算因果/success rate。
- [x] CLI summarize，支持 JSON/JSONL。

## 验证

- [x] 15 个合成测试通过：manifest 字段/配对/比较、全分母、跳过/阻断、缺日志、缺用量、候选不一致、重复/计划外、official、by_role、CLI。
- [x] 全量 Docker：451 tests，2 个既有环境错误（缺 `anthropic`），8 skipped。
- [ ] 外部 Gemini 复审 `fd617c3`。
- [ ] Z4/Z5 用真实 manifest/record 填充；需用户批准任务/次数/资源。

## 明确不做

- [x] 不执行真实实验、不读取真实轨迹/隐藏材料。
- [x] 不生成 success rate、official reward 或临床 verdict。
- [x] 不引入数据库/可视化平台。
