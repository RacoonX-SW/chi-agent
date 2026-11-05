# 最终候选冻结与新B/九题验证准入准备

日期：2026-11-05（Asia/Shanghai）。**结论：离线冻结和准入准备完成，真实执行未授权。** 本轮没有真实模型、摘要、续写、B/C、患者、world、Trial、judge 或发布调用；`official_reward=null`。机器候选、B 计划、九题预登记和审批草案分别见 [候选](validation-candidate-20261105.json)、[B 计划](coding-b-plan-20261105.json)、[九题预登记](nine-task-preregistration-20261105.json)、[G0 决策模板](admission-decision-template-20261105.json)及[OpenSpec 草案](../openspec/changes/final-validation-admission/proposal.md)。

## 1. 工作区与来源

- 实际 `origin/main=ec1a7064b5cd0a10bd8c397c9f7f61e1946d19cf`，PR59 已合并；从 main 新建 `deepseek/final-validation-admission`，未继续向已合并的 `score-readiness-hardening` 追加。
- 开工本 checkout 干净；其他 worktree `c2-input-output-recovery`、`context-recovery-plan` 保留未写；本轮只有本 checkout 写入。
- 已审包内实现：`36db613358ac9d01d792ee8f0bb4d39431c02b9e`。当前树相对它的包内差异为 **0**：42 个 `PACKAGE_FILES` 成员逐字节不变。新增的 `scripts/go_chi_readiness_inventory.py` 与测试来自 `8992af1`，已在前一轮独立复审，且不在 `PACKAGE_FILES`；本报告将其列为包外变化，不冒充内包变化。
- 当前源码固定为 `ec1a706…`；候选 JSON 同时记录源码、包内实现和包外新增，避免把文档/包外提交混成内包新字节。

## 2. 冻结身份与实际离线检查

全部 Python 在 Docker/Python 3.12；`--network none --read-only --tmpfs /tmp`，源码/依赖/vendor 只读，仅专属导出目录可写；无 Key/.env、无 Docker socket、无真实服务。

| 对象 | 实际身份 |
| --- | --- |
| Go bundle manifest | `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d`（42 成员） |
| Go runtime identity | `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc` |
| release manifest | `4553e703effef63cae69a9260c13b1a73973d5c51439213fa9337feef326d4e6` |
| release source_commit | `ec1a7064b5cd0a10bd8c397c9f7f61e1946d19cf` |
| release SHA256SUMS | `3f4d18825f12607dd91c0c8f0018a8798e6342869ccca4153c52c99b2dc463a7` |
| evaluation manifest | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，不变 |
| 候选 JSON SHA-256 | `500776855474d7f55caa267563f24f68e3c7919cbfb1cfe8df98c9db6b6f3f17` |

实际命令与结果：

| 检查 | 实际结果 |
| --- | --- |
| 从 `git archive ec1a706:chi-agent` 快照构建 Go/evaluation/release | exit 0；manifest/runtime/release 见上；`verify_release` valid |
| 隔离 Go 包无 Key 禁网 preflight（`/usr/local/bin/python -S`） | exit 0；`identity_verified`，runtime 匹配，upstream clean，`official_reward=null` |
| 隔离 release `package/` 再跑 preflight | exit 0；同一 runtime/manifest |
| 定向打包/release/delivery/harness/entry/inventory 测试 | exit 0；**42 passed、42 subtests** |
| 包外 inventory 工具单独 unittest | exit 0；**9 tests OK** |
| controller `test_role_operator_config` + `test_role_validation_wiring` + `test_go_chi_operator` | exit 0；**15 tests OK**（12 + operator 3） |
| 候选元数据/提示/包成员 hash | exit 0；43 个包文件（42 成员 + manifest），无凭据环境 |

证据（本地忽略目录 `runs/final-validation-20261105/evidence/`）：`build.log` `e273974f…`、`preflight.json`/`preflight-release.json` `93df013a…`、`targeted-tests.log` `b0c8c939…`、`controller.log` `375a4f4c…`、`inventory-tests.log`（见本地证据）、`metadata.json` `9f0a7ae1…`、`reviewed-package-diff.txt` `207c813f…`。

未重跑整套 A–D/历史全量；上轮已审的 951 passed/8 skipped/350 subtests、controller 12 + operator 3、两个 anthropic collection error 保持其原范围。本轮只新增/核对包外工具与当前候选，不把旧数量冒充本轮全量重跑。

## 3. 新 coding-B 草案（未执行）

- 计划文件 SHA-256：`19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`。
- 入口：release `package/scripts/go_chi_entry.py coding-b`；`evaluation=eval-final-20261105`、`state=runs/final-validation-20261105/state`、`run=final-b-001`、`attempt=attempt-1`、`task=synthetic-coding-b`、`history_mode=external`。
- 1 逻辑 B，最多 6 个 provider HTTP；main≤6，确认/summary/continuation/患者均 0；输出 1024；无摘要、恢复、患者、CHI、world、MCP、判分。
- 成功：`inspect_code`/`verify_patch` 原契约完成且 `verification:pass`；真实 usage/费用留证；pending/halted null；新 identity B receipt/run seal 有效；容器清理且 state/log 可读。
- 停止：异常响应、length、未知 token/结果、网络/取消/凭据/计费/持久化错误、6 次/时间上限、身份不符、清理不明；不重试、不第二次 B、不换账根。
- 旧 B 不适用；新 root 只是隔离 evaluation，**不结算、不清除、不假装旧 payer-010 unknown 为零**。

G0 仍需用户二选一：提供 payer-010 round1 可信结算/对账证据；或明确保留旧 unknown 并仅批准本隔离 B。决策模板 SHA `c292d6e1d6e826d5ed939ff2cf0467c2db9a2f41240166a8af70eb50c09fb335`；未填用户决定，未创建真实 journal/state。

## 4. 九题预登记（未执行）

预登记 SHA-256：`bb9d79308951e89939767697f82e3525b9e0f9d166e937c4158188de4edfb209`。

选择方法：只读公开 `data/tasks.jsonl` 的 family/task_id/path/title/kind/actor/timeout/公开 fixture 计数/URL；忽略 `expected_target_status`、`expected_payer_route`、`verifier_contract`，不读 expectations/solution/verifier。排除历史已见 base `008/011/012/013/014/017/018/019/027/030/031/032` 与 `cm_afib_moderate_anxious_001`；按 task_id 升序取前三，provider/UM base 不重叠。

| 角色 | 任务 | 本地资源 |
| --- | --- | --- |
| provider | `pa_t015_t015_o002_p01_new_referral_provider` | 缺失 |
| provider | `pa_t016_t016_o001_p01_new_referral_provider` | 缺失 |
| provider | `pa_t021_t021_o003_p01_new_referral_provider` | 缺失 |
| payer/UM | `pa_t022_t022_o001_p01_nurse_review_payer` | 缺失 |
| payer/UM | `pa_t023_t023_o003_p01_triage_payer` | 缺失 |
| payer/UM | `pa_t024_t024_o001_p01_nurse_review_payer` | 缺失 |
| CM | `cm_anorexia_hard_refuses_001` | 缺失 |
| CM | `cm_asthma_low_coop_001` | 缺失 |
| CM | `cm_ckd_moderate_anxious_001` | 缺失 |

- 9 题当前均不在本地离线树；需要另行获取/冻结公开 instruction、tool_reference、world/manifest hash。本轮不下载、不解析隐藏材料；获取失败不换题，按缺口停止。
- “未在选定仓库历史找到先前使用”不等于绝对保证未见；若后续发现污染，如实标注，不按结果换题。
- 实际路径推荐 **开发 `role_operator`**，标为“开发未见验证”，不是正式 Harbor。正式 Harbor 只有满足其供应/CLI/state/患者/授权条件时才能同次合并取证，不能把 mock/开发装配称为真实 Harbor 通过。
- 每题一次、同一候选、新 world；provider/payer 主+确认≤50 HTTP；CM 主+确认≤50 + 开发患者辅助≤10（一般≤60）；确认≤2；主输出 8192、确认 32768、患者 8192；B 单列，不藏进 16C。
- 停止：新 unknown、pending/halt、跨 case/patient 写、越界副作用、预算/时间、取消、持久化/清理失败；不按结果换题、不自动重跑。

九题审批草案只写在 proposal 第3节，明确“草案、未授权执行”；当前 0 次真实 C。

## 5. 历史与旧许可

只读核对，未 rebind/迁移/核销/清 pending：

| 对象 | 实际 hash/状态 |
| --- | --- |
| 旧 S 账 `runs/validation-live-20261104/state` | `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`；pending/halted null；vprep-b complete、vprep-s failed/`chi_summary_invalid`、20 settled |
| payer-010 旧 unknown `state-abl-on` | `1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef`；pending `real-ext-payer-010` round1；未知未结算 |
| 历史后继 `state-abl-on2` | `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9`；pending null，但不自动闭合 payer-010 特定授权 |
| 旧 B 收据 | 不可用于新 identity；新 B 必须另行批准 |

未改旧 accounting/pending/receipt/seal/wire/轨迹；未核销、重发、迁移或换账根。旧候选 JSON、旧审批文件、旧导出包和轨迹未覆盖；本轮新文件使用 `20261105` 名称。

## 6. 未完成项与边界

- 新 B 未执行；九题资源 0/9 本地、未获取；九题未执行。
- payer-010 处置/特定后继授权仍未决定；新隔离 root 不解决该历史。
- 正式 Harbor 供应/CLI/state/患者/清理、MCP 现场 schema、真实端点兼容、摘要/恢复、官方患者/judge 和官方分数均未验证。
- 摘要/输出恢复/Y 默认 off；不因能力存在而启用。
- 本报告、候选、B 计划和九题预登记均不构成真实运行授权；PR 合并也不构成。

## 7. GPT 复审入口

- 分支：`deepseek/final-validation-admission`；候选源码 `ec1a706…`；包内实现 `36db613…`。
- 候选：`reviews/validation-candidate-20261105.json`（SHA `50077685…`）。
- B 计划：`reviews/coding-b-plan-20261105.json`（SHA `19ea22a3…`）。
- 九题预登记：`reviews/nine-task-preregistration-20261105.json`（SHA `bb9d7930…`）。
- G0 模板：`reviews/admission-decision-template-20261105.json`（SHA `c292d6e1…`）。
- 草案：`openspec/changes/final-validation-admission/proposal.md`、`tasks.md`。
- 本地证据：`runs/final-validation-20261105/{evidence,exports}`；不上传原始轨迹/账本/任务载荷。
- 建议复核：重跑构建/preflight/定向测试；检查 42 成员与 `36db613` 逐字节一致；确认旧 S/payer-010 hash 未变；确认没有真实请求或 world/Trial。
