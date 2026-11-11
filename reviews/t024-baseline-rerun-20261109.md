# t024 正常 16384 基线通过（2026-11-09）

范围：在 t022 已通过的 bundle/identity 上重跑 t024 payer 正常 16384。**未跑 judge/Trial/发布；`official_reward=null`。**

## 1. 结果

| 项 | 值 |
| --- | --- |
| 代码 | main `1476923` |
| bundle | `eedb73d814f281c48cffdffb7575a122f7652ca033575283b1ead160a590c2d5` |
| identity | `25a3eab3d43a4c88a6eeacf90544efaadc38a154979613241d3d5a138ab5af78` |
| B | `ce-b-007`（复用，同一 state/identity） |
| C | `ce-c-t024-rerun-001`，t024 payer，正常 16384 |
| C 结果 | **complete + claim**，`final_output_claimed=true` |
| target | `CASE-27EFB677` |
| 请求 | 39 main，全部 settled |
| recovery / drift / pending | 0 / 0 / null |
| 用时 | runner 989,980 ms；operator 1,003,980 ms |
| 用量 | input 7,718,903 / output 95,537 |
| 计费 | list 1.21216587 / allowance 0.72729948 / charged 0 |
| 清理 | network/runner/world removed，quiescence confirmed |
| `inspect_history` | **inspected** |
| official_reward | null |

最终状态：

```text
CASE-27EFB677 is approved (DET-e7f74d69): workflow determination/finalized,
outcome approved; MD decision MCD-ffc77053 approve/signed;
approval letter LET-0d189147 delivered via api 2026-03-15T09:00:00;
authorization AUTH-CASE-27EFB677-4E6750.
```

## 2. 验证到的行为

- 失败 `local-fs-list`（`CASE-7C158C7A`、`CASE-27EFB677` 的早期失败）不绑定 target；
- seq 28 成功读取 `CASE-27EFB677` 后绑定；
- 39 轮内完成并 claim，无 recovery、无 drift、无 pending；
- tool evidence replay 通过，`inspect_history` inspected。

## 3. 身份与后续

- 与 t022 使用同一 bundle/identity/B，无需新建 B；
- 旧 pending（C-002 round 8、旧 t022/t024 429/timeout）保留，不重试、不清。

## 4. 边界

- 未跑 judge、Trial、发布；`official_reward=null`。
- 未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、共享 50 次契约。
- 仅 t024 一题通过；CM 失败题、provider/CM 正常任务、更广模型/锚点兼容性未验证。
