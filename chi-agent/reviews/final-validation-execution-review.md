# 新B执行与九题验证准备（执行者检查）

日期：2026-11-06（Asia/Shanghai）。**结论：PR60 已合并；九题公开资源已按冻结 revision 获取并冻结，9/9 资源 manifest 通过 preflight。用户随后明确批准一次新 coding-B，已执行 `final-b-001` 成功（3 个 provider HTTP、全部 settled、receipt/seal 有效）。用户再批准九题开发 C 后，首题 `final-c-provider-t015` 的第 4 个 main 请求在 240.022s 传输超时，主账保留 `pending={本 run, round:4}`、`halted=null`；按批准文本“任一 unknown、pending/halt 即停止”，未执行其余 8 题，未重试、未换题、未换账根。九题未完成，`official_reward=null`。** 本轮自查属于“执行者检查”，不是新的独立审核；既有 GPT 独立结论保持原义。

## 1. 基线与 Git

- 实际 `origin/main=856e2f2eee44c591ee6d93ded19e4c48f0d08cf0`，PR60 已合并；交接事实中的分支 HEAD `898c3e7…` 与 merge 关系已核对。
- 从最新 main 新建 `deepseek/final-validation-execution`；未继续向已合并的 `final-validation-admission` 追加。
- 开工本 checkout 干净；其他 worktree `c2-input-output-recovery`、`context-recovery-plan` 保留未写；本轮只有本 checkout 写入。
- 已独立通过的包外修复 `bfc1d8f73495a9dd8d79d07e3ce69f39a39afb54` 保留；`36c2c79` 有条件通过、`83749ac` 未通过的历史结论不改写。

## 2. 固定候选与未改写身份

| 项目 | 实际值 |
| --- | --- |
| 候选 JSON SHA-256 | `0df12589c851b38423e6212997e7f4b9214912c25b7c84d7614f30e0c5f493d0`，未重写 |
| B 计划 SHA-256 | `19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`，未重写 |
| 九题预登记 SHA-256 | `bb9d79308951e89939767697f82e3525b9e0f9d166e937c4158188de4edfb209`，未重写 |
| Go manifest | `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d` |
| runtime | `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc` |
| release manifest | `4553e703effef63cae69a9260c13b1a73973d5c51439213fa9337feef326d4e6` |
| release source_commit | `ec1a7064b5cd0a10bd8c397c9f7f61e1946d19cf` |
| 42 包成员 | 与已审 `36db613` 逐字节一致 |

PR60 合并不改变 release source_commit；本轮使用已冻结 release，不重建、不把最新 main 冒充原冻结源码。候选 JSON、B 计划和预登记 JSON 原始字节未改；资源冻结写入新文件，避免授权身份漂移。

## 3. 九题公开资源获取与冻结

- 冻结 revision：`5ce88104df2a91e057619eb70fb51f56fc5949eb`；只从该 revision 的公开路径获取，未跟随远端 main，未遍历整个数据集。
- 仅获取预登记 9 题的 instruction/task.toml/tool_reference（适用角色）、`fixtures/manifest.json`、opaque `fixtures/expectations.json`、payer request PDF，以及共享 PA/CM world 和 CM shared tool_reference；未下载 judge/solution/tests。
- 下载 59 个文件；实际 size 与缓存树全部匹配，LFS hash 全部匹配，无 missing/extra。
- `expectations.json` 仅作为 world_only opaque 字节保存并计算 hash，未解析内容；未人工或模型审读隐藏材料。
- 9 份 role manifest 由已审 `make_role_manifest.py` 生成，`role_resource_preflight.validate` 全部通过。
- t022 保留 **5** 个 request PDF；t023/t024 各 **4** 个；未删除、漏供、重命名或换题。
- 冻结结果：`reviews/nine-task-resource-freeze-20261106.json`，SHA-256 `074fd38e98b7078de1f815cdf78114d64aee03d505999e1e41aa29b1d08de762`。

| 任务 | role | request PDF | manifest SHA-256 |
| --- | --- | ---: | --- |
| `pa_t015_t015_o002_p01_new_referral_provider` | provider | 0 | `5cd655f63b6e…` |
| `pa_t016_t016_o001_p01_new_referral_provider` | provider | 0 | `fde037d0b733…` |
| `pa_t021_t021_o003_p01_new_referral_provider` | provider | 0 | `aa227b695699…` |
| `pa_t022_t022_o001_p01_nurse_review_payer` | payer | 5 | `1c10857de9f2…` |
| `pa_t023_t023_o003_p01_triage_payer` | payer | 4 | `ab2f0362d335…` |
| `pa_t024_t024_o001_p01_nurse_review_payer` | payer | 4 | `f6b448c7adc2…` |
| `cm_anorexia_hard_refuses_001` | cm | 0 | `fc2c9d4badf5…` |
| `cm_asthma_low_coop_001` | cm | 0 | `7508e7ac84cd…` |
| `cm_ckd_moderate_anxious_001` | cm | 0 | `08bf58537813…` |

资源路径：`runs/final-validation-20261105/resources/dataset`、`.../manifests`。原始资源留本地忽略目录，不上传。

## 4. 实际 Docker 命令与结果

全部 Python/下载在 Docker/Python 3.12；资源下载容器仅公开网络，不挂凭据；后续验证容器 `--network none --read-only --tmpfs /tmp`，源码/依赖只读。

| 检查 | 实际结果 |
| --- | --- |
| 公开资源下载（第一次） | exit 35：14 个文件后 `SSL_ERROR_SYSCALL`；原失败保留，未计为资源成功 |
| 公开资源下载（重跑） | exit 0：59/59 文件 |
| size/LFS 核对 | exit 0：`all_size_ok=true`、`all_lfs_ok=true`、missing/extra 空 |
| 9 份 role manifest 生成 + preflight | exit 0：9/9 `written`；t022 12 文件、t023/t024 11、provider 7、CM 6 |
| 9 份 manifest 独立只读复核 | exit 0：9/9 `valid` |
| 旧账只读 hash | 三份均匹配；旧 S pending/halted null、vprep-s failed/`chi_summary_invalid`、20 settled；payer-010 pending 保留 |

证据：`runs/final-validation-20261105/evidence/{download.log,download-verify.log,manifests.log,manifest-recheck.log}`。

本轮未重跑 951/8/350、24/14/29 或 release/evaluation 重建；这些保持前一轮 GPT 独立检查的原范围，不冒充本轮重跑。本轮没有真实模型/world/Trial/judge 调用。

## 4a. 新 coding-B 实际执行（已获用户明确批准）

用户 2026-11-06 的批准原文绑定候选 SHA `0df12589…`、B 计划 SHA `19ea22a3…`、`eval-final-20261105` 和新隔离 state；批准一次 coding-B、最多 6 个 provider HTTP，保留 payer-010 旧 unknown，不授权摘要/恢复/C/患者/world/Trial/judge/发布。

| 项目 | 实际结果 |
| --- | --- |
| 入口/身份 | 冻结 release `package/scripts/go_chi_entry.py coding-b`；Go `c5f569e8…`、runtime `2a9a3271…`、release `4553e703…` |
| run/attempt | `final-b-001` / `attempt-1`，evaluation `eval-final-20261105`，state `runs/final-validation-20261105/state` |
| 结果 | exit 0；`status=complete`、`safe_error_code=null` |
| 物理 HTTP | **3** 个 main；确认/summary/continuation/患者均 0；全部 settled |
| 工具 | `inspect_code`/`verify_patch` started+returned；`verification:pass` |
| usage | input 1387、output 124；`billing_complete=true`、warnings 0、unsettled [] |
| USD | charged `0`、list `0.00016955`、allowance `0.00010173`，三项均 known/complete |
| B receipt | `state/b-receipts/final-b-001.json`，SHA `ac6499ca…`；run digest 匹配 |
| run seal | `state/run-seals/final-b-001.json`，SHA `6e229d76…`；run digest 匹配 |
| pending/halted | `null` / `null`；state identity 匹配 runtime |
| 清理 | `docker run --rm` 后无 `final-b-001` 容器；无 world/network/患者资源；state/log 可读 |
| official_reward | `null` |

证据：`runs/final-validation-20261105/evidence/b-execution.log`；`b-logs/final-b-001/{run_log.txt,run_result.json,run_output.txt}`；`state/chi-accounting.json`（SHA `51d21aed…`）。机器记录：`reviews/final-validation-b-execution-20261106.json`（SHA `d94c523b…`）。

**边界**：3 个 HTTP 是实际发送数，不是 6 次 B；`charged_usd=0` 是已记录的 Go 实扣，不等于模型价目价值或套餐消耗；本 B 只证明新身份 coding 工具往返/usage/receipt/seal，不证明 CHI 业务、摘要/恢复、患者、Harbor、judge 或官方分数。

## 4b. 九题开发 C 执行：首题 t015 超时后停止

用户 2026-11-06 明确批准按候选 SHA `0df12589…`、预登记 SHA `bb9d7930…`、资源冻结 SHA `074fd38e…` 执行 9 次开发 `role_operator` C。实际按顺序从 provider t015 开始，只执行了这一题。

| 项目 | 实际结果 |
| --- | --- |
| 入口 | `role_operator.py` → `role_runner.py` → 冻结 release `package/scripts/go_chi_entry.py live` |
| run/attempt | `final-c-provider-t015` / `attempt-1`；evaluation `eval-final-20261105`；共享 state `runs/final-validation-20261105/state` |
| world | 新 world，readiness 6.679s；初始 capture ready |
| 结果 | `failed` / `chi_timeout`；runner exit 1；operator exit 1 |
| 物理 HTTP | **4 个 main**（round 1–3 settled，round 4 pending）；确认/summary/continuation/患者均 0 |
| 第 4 请求 | 240.022s 后 `chi_timeout`，stage=transport；无响应、无 `response_sha256`、无可信 usage |
| tokens | 本 run known 输入 41,312 / 输出 401，但 `complete=false`；journal 42,699 / 525 含 B |
| USD | charged `0`、list `0.00630589`、allowance `0.00378353`，三项均 `complete=false`（含 B 的 known 值） |
| 工具 | 6 次工具调用（4 种工具）、12 个 started/returned 事件；无业务写工具；`claim_done=false`；`chart.search_patients` 为 observation |
| 业务资源 | provider 前后均 2,202 行且 SHA 相同；payer 前后均 0 行；工作区仅 `.workspace_materialized` |
| capture | initial `8aaffa50…`、final `a8ddb5e2…`，均 ready |
| 清理 | runner/world/network 均 removed，client closed；`capture_error=null`、`cleanup_error=null`；world quiescence confirmed |
| pending/halted | `{"run":"final-c-provider-t015","round":4}` / `null` |
| official_reward | `null` |

**停止决定**：批准文本规定“任一 unknown、pending/halt、越界写、清理不明即停止”。round 4 为新的 pending/unknown，因此未执行 t016、t021、payer t022/t023/t024 和 CM anorexia/asthma/ckd 共 8 题；没有重试、换题、改名、换账根或追加请求。8 题状态为 `not_run / prior_request_usage_unknown`，没有输出目录、attempt 或模型请求。pending 原样保留，未清空、未对账、未核销。

**可观察线索，不作根因归因**：world 日志显示 2026-11-05T18:13:06Z 一次 `CallToolRequest`，2026-11-05T18:17:06Z 会话终止；第 4 个请求前的 `chart.search_patients` 工具结果约 192,782 字符，context 估计 272,934 tokens（UTF-8 上界估计，不是 tokenizer 结果），请求证据 336,024 bytes。只能确认“传输超时且结果未知”，不能称为请求未送达、零费用或错误业务动作。

**机械检查**：13 项确定性检查中 1 true（`provider_pre_submission.packet_absent`）、11 false、1 not_applicable；这是 source/state 机械检查，不是临床或官方判定。第 4 请求超时前未形成目标业务状态。

证据：`runs/final-validation-20261105/c-runs/final-c-provider-t015/orchestration.json`（SHA `830752a9…`）；`state/chi-accounting.json`（SHA `14376076…`）；`state/run-seals/final-c-provider-t015.json`（SHA `96a614a8…`，run digest `984847ba…` 匹配）；机器记录 `reviews/final-validation-nine-task-execution-20261106.json`（SHA `2993130f…`）。

**边界**：这是开发 `role_operator` 路径，不是正式 Harbor；`official_reward=null`，不声称临床通过或官方分数。B receipt/seal 在新 attempt 追加后仍匹配；旧 payer-010 unknown、旧 S 失败和旧 B 许可未改写。

## 5. 文档与审批引用

- `openspec/changes/final-validation-admission/proposal.md` 第3节残留的旧候选短 SHA `500776…` 已更正为当前 `0df12589…`；其他审批引用已核对。
- `REVIEW_STATE` 已更新 PR60/61/62 合并事实、九题首题 t015 的 pending/停止、资源 9/9 冻结及“执行者检查”边界。
- `tasks.md` 已勾选资源获取/冻结、新B和九题启动；保留九题剩余8题、正式Harbor/患者/judge 的未执行项。
- 九题审批草案已标注“已批准；首题 pending 后停止”，保留批准原文；机器执行记录写入新文件。
- 旧候选 JSON、旧审批文件、旧导出包和旧结论未覆盖；资源冻结写入新文件。

## 6. 未执行 / 未验证

- **新 B 已执行并成功**：见第4a节；这是用户后续明确批准的一次 B，不是本 Prompt 初始自动授权。
- **九题已启动但停止在首题**：见第4b节；`final-c-provider-t015` 第 4 个 main 请求 pending/`chi_timeout`，按停止条件未执行其余 8 题。它们不是业务失败，也不是通过，状态为 `not_run / prior_request_usage_unknown`。
- **pending 未解除**：round 4 的结果与 token/费用未知；未重试、未对账、未清 pending。后续九题或任何同 state 运行需先有可信结算证据和单独受审的处置决定。
- t015 的初始/末态 capture、world 日志、资源前后快照和清理已核验；其余 8 题未启动 world/MCP/患者/模型。
- 正式 Harbor 供应/CLI/state/患者/清理、官方 judge、官方分数、Writeup/报告/发布仍未验证。
- 开发 `role_operator` 路径只能标为开发验证，不是正式 Harbor。
- payer-010 旧 unknown 处置仍需用户决定；新隔离 root 不解决旧历史。

## 7. 下一项可直接批准的文本

### 7.1 一次新 coding-B（已获批准并执行，保留原文）

> 我确认保留 `real-ext-payer-010` round1 的结果/token 未知及不完整费用，不修改旧 pending、不认定零发送或已结算；该决定只关联候选清单 SHA `0df12589c851b38423e6212997e7f4b9214912c25b7c84d7614f30e0c5f493d0`、B 计划 SHA `19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`、`eval-final-20261105` 及新隔离 state。允许执行 `final-b-001` 一次 coding-B，最多 6 个 provider HTTP，参数、用途、记录、停止和清理按该计划。暂不授权摘要/恢复、任何 CHI C、患者、world、Trial、判分或发布；旧 unknown 和旧 B 许可仍不结算、不复用。

### 7.2 九题开发验证（已获批准；首题 pending 后停止，保留原文）

完整审批包：`reviews/nine-task-approval-draft-20261106.md`。用户已按该文本批准；实际只执行 `final-c-provider-t015`，第 4 个 main 请求 pending/`chi_timeout` 后按停止条件中止，其余 8 题未运行。以下保留当时的批准文本，不改写成新的执行许可。

> 九题资源已按预登记 SHA `bb9d7930…` 和冻结 revision 获取并生成 9 份 manifest；待新 identity B 成功且收据适用、payer-010 处置明确后，允许按预登记执行 9 次开发 `role_operator` C：provider/UM/CM 各 3 题、每题一次、新 world，使用候选 SHA `0df12589…` 与预登记 SHA `bb9d7930…`。provider/payer 每 run 主+确认≤50 HTTP，CM 另加开发患者辅助≤10；确认≤2；不启用摘要/恢复/Y。任一 unknown、pending/halt、越界写、清理不明即停止；不按结果换题、不自动重跑。该批准不包含正式 Harbor、官方患者、judge、发布或额外已见题回归。

## 8. 交接

- 本轮从最新 `origin/main=dd438e9…`（PR62 已合并）新建 `deepseek/final-validation-nine-task-execution`；只追加九题执行记录/文档，不改生产代码、模型、参数或依赖。
- 执行分支提交与 PR 链接见 `REVIEW_STATE.md`；base=main，未 merge/auto-merge。
- 详细资源冻结：`reviews/nine-task-resource-freeze-20261106.json`；九题执行记录：`reviews/final-validation-nine-task-execution-20261106.json`；候选/预登记/B 计划原字节未改。
- 下一步不是自动重跑：round 4 pending 需要可信提供方结算证据或用户明确决定如何保留/处置；在解除前，其余 8 题保持 `not_run / prior_request_usage_unknown`。
- 本报告是执行者检查，不替代 GPT 独立复审；`official_reward=null`。
