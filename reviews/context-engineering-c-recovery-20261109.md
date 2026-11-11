# Context-engineering C 恢复验证报告（2026-11-09）

范围：P1 预检修复后的新 bundle、新 B、一次有界真实 C。**未跑 judge/Trial/发布；`official_reward=null`。** 本次 C 在 8 次 provider 请求上限处主动停止，留下一个 pending；恢复链（regenerate + partial）已验证，任务本身未完成。

## 1. P1 修复

有界 C 第一次尝试 `ce-c-recovery-001` 在 preflight 阶段失败：

- `chi_context_budget_invalid`，**0 次 provider 请求**；
- 根因：`go_chi_runtime.py` 的空请求预检调用 `measure_request` 时没有传 `context_budget`，v3 budget 收到 v2 metric；
- 修复：传入 `budget=context_budget`；新增 `run_chi` + `DEFAULT_BUDGET_V3` + `main_max_tokens=1024` 回归测试；
- PR #83 合并 `9f01308`；
- 全量 **755 tests / 23 skipped / 3 个既有 import error**；recovery pytest **48 passed**。

## 2. Bundle / B

| 项 | 值 |
| --- | --- |
| source | main `9f01308566f8eac0022c9d766df8ab577ef0f634` |
| release root | `runs/context-engineering-20261109/exports/ce-20261109-9f01308` |
| bundle root | `.../ce-20261109-9f01308/package` |
| bundle manifest | `e177b4526a30c8513b0e2e3d9c584654a4bf490fc3100d2df17f292421b48490` |
| entry config | `feb1ce30d43d088830404f3b1589d1d6af5ad64cb31f7aa396800b8bbb8595a7` |
| 文件数 | 45 |
| `validate_bundle` | 通过 |
| preflight identity | `7e643a292fa48ffacaa827afc66f6f2a4db073fc42cd77f949d02b3e5b7e46f4` |
| upstream | `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，clean=true |
| `official_reward` | null |

说明：`go_chi_release.py build` 的目标是 release root，bundle 在 `package/` 下；B/C 均使用 package 路径。

### 2.1 B `ce-b-002`

| 项 | 值 |
| --- | --- |
| evaluation / task / attempt / run | `eval-ce-20261109` / `synthetic-coding-b` / `attempt-1` / `ce-b-002` |
| 结果 | complete，3 main settled，0 失败/未知/重试 |
| usage | input 1348 / output 95 |
| 计费 | list 0.00029260 / allowance 0.00017556 / charged 0 |
| receipt 文件 SHA | `cb8c05a88e5556a1c96475908f73b60da242af8ac5674ebd56db47dbec81c2fc` |
| seal 文件 SHA | `b5dfc6394c598fb8f3cd3b62471001ce0ea09959e74e916098a6922ae9522a41` |
| receipt/seal `run_sha256` | `ed420915bc48b9b80d57fb6599e441c39bbd59c989a64914312ca179f6c603e9` |
| `_run_digest` | 与 receipt/seal 一致 |
| pending / halted | null / null |

## 3. C `ce-c-recovery-002`

| 项 | 值 |
| --- | --- |
| evaluation / task / attempt / run | `eval-ce-20261109` / `pa_t024_t024_o001_p01_nurse_review_payer` / `attempt-1` / `ce-c-recovery-002` |
| config SHA | `72c9957d434e6fe74598a09c35a06be456f5b27589a8a501d842f3aaa0b06297` |
| 故障注入 | `main_max_tokens=1024`（per-run；默认仍 8192） |
| 策略 | `chi-output-recovery-v1` + `recovery_view_policy=canonical-v1` |
| 上限 | 6 main + 2 continuation = 8 provider 请求 |
| 结果 | failed / `chi_entry_failed`（由 8 次上限主动停止） |
| 请求 | 6 main（rounds 1/2/3/5/7/8）+ 2 continuation（4/6） |
| pending | `{run: ce-c-recovery-002, round: 8}` |
| halted | null |
| 清理 | client closed、network/runner/world removed、quiescence confirmed |
| `official_reward` | null |

### 3.1 恢复链

| 轮次 | 证据 |
| --- | --- |
| round 3 main | `finish_reason=length`；completion 1024 / reasoning 876 |
| round 4 continuation | **regenerate**；permit `53a48154825f24d0c22cba919f0cc8cffbb1dcd443a182abf7486bd08a3c2a41` |
|  | `pressure=true`、`frozen_view=false`、rule `chi-context-projection-regenerate-v1` |
|  | parent view `2e991f5b1dcf7873af888a7d6fbca649af87e9d2d9cd4d1166ec006c7f30c7c1` |
|  | new view `ac9ca8386a626033587e5b6cf816ed1afe74a335ba7fd1006383938254d8deda` |
|  | source `0857589d97d7594b7feb6c70039d63e9885f90d9b2408b8e482b98261ceb58b2` |
|  | anchor `a2a1e7b17e3ecf80b252bd3f5283e264962a829e28cd0c5ff3251fdf118a5148` |
| round 5 main | `finish_reason=length`；completion 1024 / reasoning 1024 |
| round 6 continuation | **partial**；permit `3a321c3956330435c8f41639fa9443eab891f3ffa48b217705069628ac9f8db4` |
|  | `pressure=false`、`frozen_view=true`、rule `chi-context-projection-v1` |
|  | parent == view `494b9dfa20c35ea20ced06231cdf02dfe04da746d60c435f2a15a0d866dab435` |
|  | source `05e06c976d6ae954a8f3783849b63dc5c2a6e232524db8f0b72011b03473b39b` |

- `inspect_history`：**status inspected**（即使 round 8 pending）。
- source evidence 写入 main 轮（1/2/3/5/7/8）；reader 重放通过，无 `chi_view_source_mismatch`。
- 两个 continuation 的 view/anchor/history 与 permit 匹配。

### 3.2 停止与 pending

- supervisor 在 `main=6 cont=2`（总计 8）时停止 runner；
- round 8 是一个 main 请求，在途时被停止，没有 response/usage；
- state 保留 `pending={round:8}`，`halted=null`；
- 未自动重试、未清 pending、未换题/换 state/换 bundle。

### 3.3 用量 / 计费

- 7 个 settled：input **167,996** / output **4,312**；
- round 8 pending：usage unknown，unsettled；
- list **0.05557320** / allowance **0.03334392** / charged **0**；
- 因为 pending，整体 `billing_complete=false`，不能写成已完全结算。

## 4. 结论

- **P1 修复通过**：C 已越过预检并发出真实请求。
- **恢复链验证通过**：同一次 C 覆盖 **regenerate** 与 **partial**；permit v2、view/source/anchor/history、source evidence、`inspect_history` 均通过。
- **任务未完成**：在 8 次上限处主动停止；round 8 pending 是预期结果，保留。
- 没有 judge/Trial/发布；`official_reward=null`。

## 5. 边界与后续

- 不跑第二次 C；本次已覆盖两种恢复模式。
- pending round 8 保持原样；若要继续任务，需要新 state/新 B 或显式对账，不能直接清。
- 上一轮失败 `ce-c-recovery-001`（0 请求、无 pending）保留在旧 state，作为 P1 证据。
- 矩阵中的 P2 仍冻结；本次未修。
- `messages[2]` 锚点已由真实 C 接受（至少本任务/本端点）；更广任务/模型兼容性仍需后续证据。
