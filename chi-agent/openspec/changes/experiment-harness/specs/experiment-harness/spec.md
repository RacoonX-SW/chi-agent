# F7 实验工具行为契约

本契约覆盖离线 manifest/record/summary；不授予真实运行、官方判分或临床评审。

## 需求：运行前冻结实验条件

### 场景：单变量对照

同一 mechanism 的 off/on 两臂必须使用相同任务集合、角色、attempt 和 limits；否则拒绝 manifest。不同时比较多个变更，除非 manifest 明确登记为不同 mechanism 并分别给出 off/on。

### 场景：机制不可独立切换

无法独立 off/on 的机制使用 `mode=na` 并给出 reason；不能伪造 on 臂，也不能把多项一起改的结果分摊成单项收益。

### 场景：任务、资源与上限固定

manifest 记录任务 ID、角色、attempt、资源 manifest hash、世界镜像 ID、请求/输出上限和停止条件；未知字段、重复任务、重复 cell、缺少停止条件均拒绝。manifest 可规范化并生成 SHA-256，运行前固定。

## 需求：结果记录不能被补齐或覆盖

### 场景：缺失日志

record 标 `logs.present=false` 时必须给原因；汇总计入 `missing_evidence`，不能记 pass，也不能删除原 completed 状态。

### 场景：跳过、阻断、未运行

skipped/blocked 分别计数；manifest 中没有 record 的计划单元计 `not_run`；三者都不能进入 pass 分母的“通过”。

### 场景：缺失用量

input/output/cost 分别保留 known sum 与 missing count；缺失不补 0，不生成完整费用结论。

### 场景：官方分数

record 的 `official_reward` 只保留原值或 null；汇总只计 present/absent，不计算均值、成功率或自估 reward。

## 需求：候选与对照不能混算

### 场景：候选不一致

record 的 candidate（source/bundle/model/endpoint/simulator/capabilities）必须与 manifest 完全一致；否则拒绝汇总。

### 场景：重复或计划外记录

同一计划单元重复记录、计划外 task/cell、计划外 check 均拒绝；重试必须使用预登记的新 attempt，旧失败记录保留。

## 需求：检查适用性

### 场景：NA 与缺失

manifest 只对任务适用检查；record 返回 pass/fail/na。缺失检查计 `not_run`，不被补成 pass；NA 单独计数。

### 场景：汇总不推导因果

summary 按 cell/mechanism/role 给出计数和分母；off/on 只并列展示，不自动计算“机制有效”。是否采用由后续规格/用户决定。

## 需求：CLI 可复核

### 场景：验证与汇总

`experiment_manifest.py validate/freeze` 与 `experiment_summary.py summarize` 对有效输入返回 0，无效输入返回 1 和稳定错误码；record 支持 JSON 数组或 JSONL。工具不读取隐藏材料、不调用模型。
