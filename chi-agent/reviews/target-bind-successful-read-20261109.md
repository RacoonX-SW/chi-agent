# Target 只从成功 workspace 读取绑定（2026-11-09）

范围：修复 t022 重跑暴露的 target 绑定缺口。**只做离线代码/测试与文档；真实 t022 重跑在合并后另行执行；`official_reward=null`。**

## 1. 现象

`ce-c-t022-rerun-001`（t022 payer，正常 16384）32 main 全部 settled，但在第 32 轮被 `HARD:target_mismatch` 停止，未 claim。

task-state：

```text
target = CASE-E33A4F82
```

但任务实际 case 是 `CASE-27EFB677`。模型从 seq 22 起一直在正确 case 上工作，seq 32 的 `review.save_criteria_evaluation(CASE-27EFB677)` 被硬拒绝。

## 2. 根因

target 绑定发生在 seq 9：

```text
local-fs-list returned_error case:CASE-E33A4F82
```

这是一次失败的 workspace 列目录（case 目录不存在）。上一版修复只要求 `kind == "local"` 且 `scope == case:<case>`，没有要求读取成功，所以失败观察也绑定了 target。之后正确的 `CASE-27EFB677` 成功读取不再覆盖。

## 3. 修复

`_bind_target_from_observation` 现在要求：

- `kind == "local"`；
- `effect == "read"`；
- `event == "returned"`；
- `scope == case:<case>`。

失败/拒绝的 list、read、write 都不再绑定 target。

## 4. 测试

- 新增：失败 `local-fs-list` 不绑定，随后成功 `local-fs-list` 绑定正确 case；
- 新增：成功 `local-fs-list` 可绑定；
- 定向 `test_go_chi_state` + `test_drift` + `test_completion_gate`：**55 passed**；
- 全量 `dev_verify.sh --allow-dirty`：**783 tests / 37 skipped / 0 errors**；
- controller `test_role_payer_projection`：14 passed；
- 新 bundle：`64a1c05d9f05c4c299cf50eb903c0db36539074fcbfbb1c93de48e2fa87a7560`；
- 新 identity：`f54e049ccf52e97c1f42898cc28bb60e10f94326178f8f4998b228166add24de`；
- preflight：`identity_verified`。

## 5. 身份与后续

- 本改动改变 bundle/runtime 身份；
- `ce-b-005`/bundle `9fbc329c…`/`ce-c-t022-rerun-001` 对应修复前代码；
- 合并后需重建 bundle + 新 B，再重跑 t022；
- 旧 pending 保留，不重试、不清。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 仅修复绑定来源；target 绑定后的跨 case mutation 门禁保持不变。
