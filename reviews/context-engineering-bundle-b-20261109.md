# Context-engineering bundle + B 阶段报告（2026-11-09）

范围：`source-evidence-replay` 合并后的 bundle 重建、只读 preflight、一次 coding-B 及收口核对。**未跑真实 C、未跑 judge/Trial/发布；`official_reward=null`。** P2 冻结，不改代码；真实 length + continuation/regenerate 验证另立一次有界授权。

## 1. 代码与合并

| 项 | 值 |
| --- | --- |
| main | `8a4757bd3e7cc6b8d1d74f7075791219903b9920` |
| 候选代码 | `7a585f8` |
| 审计文档 | `2b8d258` |
| 上一基线 | `14a7acd` |
| 工作区 | 干净 |

- `7a585f8` 与 `2b8d258` 均为 `8a4757b` 的祖先；合并后未再改代码。
- 无 PR：本机无 gh/token，经用户授权本地 merge 并推送 main。该流程偏差在本报告记录，后续文档走分支/PR。
- 收口矩阵：[`source-evidence-replay-matrix.md`](source-evidence-replay-matrix.md)。矩阵无 P1；剩余 P2 冻结。

### 1.1 测试基线

- 全量 `unittest discover`：**754 tests / 23 skipped / 3 个既有 import error**。
- 定向 `test_recovery_view_binding`、`test_context_projection_guard`、`test_go_chi_diagnostics`、`test_context_error_run_log`：**24 passed**。
- 既有 recovery pytest：**48 passed**。

3 个既有 import error（环境缺口，不在本轮范围）：

- `test_dev_patient_adapter`：缺 `anthropic`
- `test_dev_patient_network`：缺 `anthropic`
- `test_role_payer_projection`：缺 `docker.types`

### 1.2 独立复核

- refused/failed 的 v3 source 重放：用“旧 mutation refused”构造 source，修复后 `_replay_source_view` 与 wire 一致（`match True`）。
- P1 修复、`pressure` 语义、partial 重新派生、source policy 均按矩阵通过。

## 2. Bundle

| 项 | 值 |
| --- | --- |
| 目标 | `runs/context-engineering-20261108/exports/ce-20261108-8a4757b` |
| bundle_id | `go-chi-evaluation-record-only-v1` |
| manifest 内部 hash | `f0160b56d20eda78c7b65d1308716302d338912b900aba96b871c59a6814d4c6` |
| `bundle-manifest.json` 原始文件 SHA | `3d37ab6655e617f7a586ebe27fba071b9beb8034425fa5a5f538d45753e9865d` |
| entry config | `feb1ce30d43d088830404f3b1589d1d6af5ad64cb31f7aa396800b8bbb8595a7` |
| 文件数 | 45 |
| `validate_bundle` | 通过；bundle 内文件自校验一致 |
| 脚本与仓库 | 45 个文件中 `scripts/*` 与 main `8a4757b` 逐文件 hash 一致 |

说明：

- **manifest 身份使用内部 `manifest_sha256` `f0160b56…`**；原始 `bundle-manifest.json` 文件 SHA 是 `3d37ab…`，两者不同，不能混用。
- 目标是 **bundle**，不是 release root；`go_chi_release.py verify` 返回 `release_layout_invalid` 属预期，不能写成“release verify 通过”。本报告只声称 `validate_bundle` 通过。
- bundle manifest 不记录 `source_commit`；“源码身份 main @ `8a4757b`”由 bundle 内 scripts 与仓库逐文件 hash 一致、以及 preflight upstream 证据支持，不是 manifest 字段。

### 2.1 只读 preflight

- 禁网、无 Key；status = `identity_verified`
- **identity_sha256**：`5614fe22c4f687b7391558c83fcaa5b33c3bd4b5ffcd57add358724cabe7a76d`
- upstream commit：`4444a07fa68a4f1623f841a292a54e284fc8e7f7`，clean = true
- `official_reward` = null

证据：`runs/context-engineering-20261108/evidence/preflight-8a4757b.json`、`bundle-8a4757b.json`。

## 3. Coding-B（bundle 准入）

| 项 | 值 |
| --- | --- |
| evaluation / task / attempt / run | `eval-ce-20261108` / `synthetic-coding-b` / `attempt-1` / `ce-b-001` |
| state | `runs/context-engineering-20261108/state`（新空 state，仅此 B） |
| 结果 | exit 0，status=complete，safe_error_code=null |
| 物理请求 | 3 次 main（上限 6），全部 settled，0 失败/0 未知/0 重试 |
| 工具事件 | `inspect_code` → `verify_patch` |
| 最终输出 | `Verification passed. The function now correctly returns the sum of two integers.` |
| usage | input 399+473+554=1426；output 50+65+16=131 |
| 计费 | 全部 `billing_source=go`、`charged_usd=0`、`billing_complete=true`、`unsettled=[]` |
| 三项 USD | list 0.00017960 / allowance 0.00010776 / charged 0（不相加） |
| accounting SHA-256 | `0a404b681ab6cdde2eeb692357d24e62f8c3221b67cb6ce80619df532be917e7` |
| B receipt 文件 SHA | `b650582b2e8e5dca60454079d29fc4a19465f89eef6498feef3d95c1437490ef` |
| run seal 文件 SHA | `9e32b3e474478a025a49d69a18368a1a489f4f318a4757bdb53ac450ed9f4b14` |
| receipt/seal 内 `run_sha256` | `171b1e9fecde76380a2c8b0685897dbcab4f08ef756ec99e897a7125100316a0` |
| `_run_digest` 复核 | 与 receipt/seal 的 `run_sha256` 一致 |
| pending / halted | null / null |
| attempts | 1 |

说明：

- `b650…` 和 `9e32…` 是 **receipt/seal 文件 SHA**；真正的运行摘要是 `171b1e9f…`。报告与后续审计必须同时写两者。
- 独立只读 postflight 在禁网容器重跑，与 `postflight-8a4757b.json` 完全一致；每轮 request/response 文件 hash、`raw_sha256`、wire 实际字节三方一致。
- 凭据：仅 `runs/real-external/auth/go.env`（0600，单一 `OPENCODE_API_KEY`）；state/logs/evidence/bundle 扫描命中 Key 的文件数 **0**。

### 3.1 B 的证明边界

B 是 **coding-B 固定探针**，不进入 `output_recovery`，也没有 `context_policy=chi-context-v3`。因此：

- B 可作为本 bundle 的 **coding-B 准入收据**；
- B **不是** v3、`messages[2]` 锚点、partial/regenerate、source evidence 重放的证据；
- 上述能力仍需真实 CHI C 验证。

## 4. 剩余 P2（冻结）

1. source 存储治理：source 文件先写、entry 后写，失败可能留下孤儿文件；source 总存储未设上限。
2. 测试缺口：`returned_error` 的 v3 source 重放、redacted tool evidence fail-closed、v3 mutation replay 无独立用例。
3. 字段语义：`history_length` 实际是视图长度；`_active_permit["parent_view_sha256"]` 未使用。
4. mode/rule 交叉校验：`view_identity.projection_rule` 未按 `recovery_mode` 强制。
5. 真实运行限制：`messages[2]` 锚点兼容性、真实 source 重放收益未验证。
6. 范围外：P3、RAG/L1/L2、任务级 resume、reasoning 压缩。

**决定：冻结，不修。** 若真实 C 验证命中其中任一项，停止并单独开小变更；不在本轮顺手改代码。

## 5. 下一步：一次有界真实 C 验证（需另行执行）

任务：`pa_t024_t024_o001_p01_nurse_review_payer`（payer，nurse review）。  
目的：用受控低输出预算触发 `finish_reason=length`，验证 v3 + `recovery_view_policy=canonical-v1` 的 partial/regenerate、source evidence、reader 重放。

- 故障注入：`main_max_tokens=1024`（per-run；默认仍 8192）。这不是性能/质量结果。
- world/资源：复用 t024（world image `000ca5…`、manifest `payer-t024.json`、manifest SHA `f6b448…`、dataset `runs/final-validation-20261105/resources/dataset`）。
- state/B：复用 `runs/context-engineering-20261108/state` 与 B `ce-b-001`；evaluation 保持 `eval-ce-20261108`；新 run `ce-c-recovery-001`；不新建 B。
- bundle：复用 `f0160b56…` / identity `5614fe22…`；不重建。
- 调用上限：**6 main + 2 continuation = 8 provider 请求**，1 个 run；达到 8 即停止容器；保留 pending。
- 停止条件：pending/unknown/halt；`chi_timeout`；`chi_http_error`；`chi_recovery_view_mismatch`；`chi_view_source_mismatch`；`chi_source_evidence_missing`；`chi_context_policy_incompatible`；身份/config SHA 不一致；清理失败；凭据泄漏。
- 成功标准：至少一次 length；v2 permit；continuation view/anchor/history 匹配；`inspect_history` 通过；source evidence 存在；无 mismatch。
- 若 6 次 main 内未触发 length：停止并报告“未触发”，不擅自提高预算或换题。
- 若只覆盖 partial 或 regenerate 之一：报告并保留另一种为离线验证；不自动跑第二次。

## 6. 边界

- 未跑真实 C、judge、Trial、发布；`official_reward=null`。
- 未重建 bundle、未取得新 B；未改 240s、默认 `main_max_tokens=8192`、REQUIRED 表、partial 冻结语义、regenerate 策略。
- 未修 P2；未扩功能；未 auto-merge。
- `runs/` 证据未进仓库；本报告只含聚合数字与 hash。
