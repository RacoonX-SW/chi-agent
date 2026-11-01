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
- [ ] payer/CM/Y 未完成；需 **新 release（含 reconcile 源码）+ 新 coding-B + 新 external state-v3**，待用户批准。
- [ ] bundle 清单修复 `81a3b15`、external operator `0fd2029`、reconcile工具 `2493cd3` 待PR合并。
- [ ] 新 release 的 coding-B 成功收据；不伪造/复用旧 B。
- [ ] 逐次保留请求/工具/用量/费用/终态/清理；未知即停，零自动重试。

## 明确不做

- 不自动开始真实运行。
- 不重试未知请求、不换模型/账根、不删除旧 pending。
- 不做官方判分、Claude/付费临床评审、对外发布。
