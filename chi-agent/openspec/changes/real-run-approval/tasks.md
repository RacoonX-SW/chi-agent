# 真实运行审批清单（待用户批准）

当前：0 次真实调用；本清单未生效。

- [x] 用户确认批次 A：1 coding-B + 3 C。
- [x] payer/CM 公开资源已在本地数据集找到；运行前只选公开文件并冻结 hash。
- [x] 用户确认 history mode = external。
- [x] 用户确认同时批准 Y 4 C；允许清单内新 attempt。
- [x] Z0 Kaggle Rules 已读：75 公开题、公开结果可选、三材料、11/15 截止、模拟数据；Go 隐私按用户决定不再确认。
- [x] 生成 external 操作者配置（provider t032 / payer t011 / CM afib），状态根 `runs/real-external/state`。
- [x] 用户创建 `runs/real-external/auth/go.env`（仅 OPENCODE_API_KEY，0600）。
- [x] B `real-ext-b-002` 成功；release bundle 修复为 `ee004c…`，identity `e41ae1…`。
- [x] provider t032 一次 C 已尝试：`real-ext-provider-001` 17请求后 `chi_timeout`，round17 pending/usage unknown；清理确认，业务部分检查。
- [x] round17 Console 记录已提供并精确匹配；正式 `state-v2` 已执行一次对账：pending=null、event `e96cbb…`、seal不变、request仍pending。
- [x] payer t011 `real-ext-payer-001` 尝试：在发请求前 `chi_history_invalid`（旧 release-v2 journal 不识别 `reconciliations`）；0请求/费用；world_quiescence unproven。
- [x] 新 release-v3（bundle `6f6e71d8…`、identity `b936b7…`）+ 新 B3 `real-ext-b-003` 成功；state-v3。
- [x] payer 002 `real-ext-payer-002`：`chi_tool_batch_invalid`，18请求/68工具，全settled、无pending、清理确认，业务部分。
- [x] CM 002 `real-ext-cm-002`：`chi_timeout`，round8 pending/usage unknown，7 settled、清理确认；Y未运行。
- [x] CM round8 Console记录已提供并精确匹配（200/105771入/4623出/90.8s）；`state-v3` 已执行同款对账：pending=null、event `5be3fa…`、seal不变、request仍pending。
- [x] payer 002 失败定位：最后工具调用 `determination__get_summary` 在 intake 阶段不被工具面接受 → `chi_tool_batch_invalid`；无 pending、无未知用量。
- [ ] 批次A收口：B成功2次、provider/payer/CM 各1次失败（超时已对账）、Y未运行；不再继续真实 C 直到离线修复候选复审。
- [ ] bundle 清单修复 `81a3b15`、external operator `0fd2029`、reconcile工具 `2493cd3` 待PR合并。
- [x] 新 release 的 coding-B 成功收据（`real-ext-b-003`）；不伪造/复用旧 B。
- [x] 逐次保留请求/工具/用量/费用/终态/清理；未知即停，零自动重试。

## 明确不做

- 不自动开始真实运行。
- 不重试未知请求、不换模型/账根、不删除旧 pending。
- 不做官方判分、Claude/付费临床评审、对外发布。
