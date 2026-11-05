# 最终候选冻结与新B/九题验证准入准备（草案、未授权执行）

日期：2026-11-05（Asia/Shanghai）。**本文件、候选清单、PR及合并均不是真实调用授权。** 本轮只完成离线冻结、配置草案和审批准备；真实模型、摘要、续写、B/C、患者、world、Trial、judge、发布均为 0，`official_reward=null`。

## 1. 固定候选

| 项目 | 固定值 |
| --- | --- |
| 生产源码 | `ec1a7064b5cd0a10bd8c397c9f7f61e1946d19cf` |
| 已审包内实现 | `36db613358ac9d01d792ee8f0bb4d39431c02b9e` |
| 机器候选清单 | [validation-candidate-20261105.json](../../../reviews/validation-candidate-20261105.json)，SHA-256 `9ac7ba0ea90bf317eda3e074d9fed4f27a7022f0b9890441e7b9deed040fafc5` |
| Go bundle manifest | `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d` |
| Go runtime identity | `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc` |
| release manifest | `4553e703effef63cae69a9260c13b1a73973d5c51439213fa9337feef326d4e6`，source_commit `ec1a706…` |
| evaluation bundle | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc` |
| 模型/端点 | `deepseek-v4.1-flash` / `https://opencode.ai/inference/go/openai/v1/chat/completions` |
| 推理/重试 | thinking enabled、reasoning_effort high、自动重试 0 |
| 开关 | 摘要 off、输出恢复 off、Y shadow off；不因能力存在而启用 |
| 平台/依赖 | Linux arm64、Python 3.12.15；固定 model/PDF 卷与 vendor `4444a07…` |

当前树相对已审包内实现只新增包外 `scripts/go_chi_readiness_inventory.py` 及其测试（`8992af1`，已在本轮前独立复审）；`PACKAGE_FILES` 42 成员逐字节不变。release 的 `source_commit` 从 `36db613` 变为 `ec1a706`，但内包 manifest/runtime 不变；这是外层 source 绑定变化，不是内包字节变化。详细证据见[阶段报告](../../../reviews/final-validation-admission-review.md)。

包外开发 operator 另做 t022 兼容适配：公开 t022 有 5 个 `fixtures/request` PDF，而原 `_payer_projection` 固定 4 个；改为使用冻结 manifest 的 1–20 有界精确计数，保留缺/多/重复/scope/size/hash 拒绝。4 文件 legacy 路径不变，5 文件 t022 路径通过；不删文件、不换题、不读隐藏答案。`role_operator.py` 不在 `PACKAGE_FILES`，内包 manifest/runtime 不变。

## 2. 新 coding-B：草案

- 计划文件：[coding-b-plan-20261105.json](../../../reviews/coding-b-plan-20261105.json)，SHA-256 `19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`。
- 入口：release `package/scripts/go_chi_entry.py coding-b`；`evaluation=eval-final-20261105`、`state=runs/final-validation-20261105/state`、`run=final-b-001`、`attempt=attempt-1`、`task=synthetic-coding-b`、`history_mode=external`。
- 1 逻辑 B，最多 6 个 provider HTTP；main≤6，确认/summary/continuation/患者均为 0；输出 1024；无摘要、恢复、患者、CHI、world、MCP 或判分。
- 成功：`inspect_code`/`verify_patch` 原契约完成且 `verification:pass`；全部真实 usage/费用留证；pending/halted null；新 identity B receipt 与 run seal 有效；容器清理且 state/log 可读。
- 停止：异常响应、length、未知 token/结果、网络/取消/凭据/计费/持久化错误、6 次/时间上限、身份不符、清理不明；不重试、不第二次 B、不换账根。
- 旧 B 不适用；旧 payer-010 unknown/pending 不因新 root 变为已结算或零历史。新 root 只是隔离 evaluation，必须由用户明确决定风险范围。

草案 argv（**不在本轮执行**；容器内路径）：

```sh
python /package/scripts/go_chi_entry.py coding-b \
  --bundle-sha256 c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d \
  --evaluation-id eval-final-20261105 --task-id synthetic-coding-b \
  --attempt-id attempt-1 --run-id final-b-001 \
  --output-root /state --logs-dir /runner-logs/final-b-001 \
  --history-mode external
```

只供应 release `package/`、固定只读 vendor/依赖卷、获准的新 state 与独立 log 父目录；运行时只注入 `OPENCODE_API_KEY`，不挂 `.env` 或其他 provider/judge 凭据。

**可直接批准的文本（选项 2：保留旧 unknown，仅批准本次 B）：**

> 我确认保留 `real-ext-payer-010` round1 的结果/token 未知及不完整费用，不修改旧 pending、不认定零发送或已结算；该决定只关联候选清单 SHA `9ac7ba0ea90bf317eda3e074d9fed4f27a7022f0b9890441e7b9deed040fafc5`、B 计划 SHA `19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`、`eval-final-20261105` 及新隔离 state。允许执行 `final-b-001` 一次 coding-B，最多 6 个 provider HTTP，参数、用途、记录、停止和清理按该计划。暂不授权摘要/恢复、任何 CHI C、患者、world、Trial、判分或发布；旧 unknown 和旧 B 许可仍不结算、不复用。

若用户选择先补齐 payer-010 的可信结算/对账证据，则先走既有受审处置，不启动本 B。无答复、PR 合并或候选存在都不等于选项 2 同意。

## 3. 九题预登记：草案

- 清单：[nine-task-preregistration-20261105.json](../../../reviews/nine-task-preregistration-20261105.json)，SHA-256 `bb9d79308951e89939767697f82e3525b9e0f9d166e937c4158188de4edfb209`。
- 选择方法：只读公开 `data/tasks.jsonl` 的 family/task_id/path/title/kind/actor/timeout/公开 fixture 计数/URL；**不读取** expected_target_status、expected_payer_route、verifier_contract、expectations/solution/verifier 内容。排除历史已见 base 后按 task_id 升序取前三；provider/UM base 不重叠；CM 排除已见 afib 后取前三。
- 9 题：provider `t015/t016/t021`；UM `t022/t023/t024`；CM `cm_anorexia_hard_refuses_001`、`cm_asthma_low_coop_001`、`cm_ckd_moderate_anxious_001`。
- 污染：历史已见/已分析 base `008/011/012/013/014/017/018/019/027/030/031/032` 与 `cm_afib_moderate_anxious_001` 排除；所选 9 题在选定仓库历史中未找到先前使用，但这不是“保证未见”，若后续发现污染必须如实标注，不能按结果换题。
- 资源：9 题当前均不在本地离线树，需有权限的公开资源获取与逐题 instruction/tool_reference/world/manifest hash 冻结；本轮不下载、不解析隐藏材料。 t022 公开布局为 5 个 request PDF（t023/t024 为 4）；开发 operator 已改为有界 manifest 计数，4/5 文件正例及缺/多/重复/scope/symlink/hash 负例离线通过。
- 路径：**推荐开发 `role_operator` 路径**，明确标为“开发未见验证”，不是正式 Harbor。若同一次运行同时满足正式 Harbor 供应/CLI/state/患者/授权条件，可合并取证，但不得把 mock/开发装配称为真实 Harbor 通过。
- 每题一次、同一冻结候选、新 world；provider/payer 物理 HTTP 上界 50，CM 主/确认共享 50 加开发患者辅助≤10（一般≤60）；确认≤2；主输出 8192、确认 32768、患者 8192；B 单列，不藏进 16C。
- 停止：新 unknown、pending/halt、跨 case/patient 写、越界副作用、预算/时间、取消、持久化或清理失败；不按结果替换任务、不自动重跑、不改名冒充未见。

**九题分阶段审批草案（未授权执行）：**

> 待 9 题公开资源获取完成并逐题冻结 instruction/tool_reference/world/manifest hash、新 identity B 成功且收据适用、旧 unknown 处置明确后，建议另行批准 9 次开发 `role_operator` C：provider/UM/CM 各 3 题、每题一次、新 world，使用候选 SHA `500776…` 与预登记 SHA `bb9d79…`。provider/payer 每 run 主+确认≤50 HTTP，CM 另加开发患者辅助≤10；确认≤2；不启用摘要/恢复/Y。任一 unknown、pending/halt、越界写、清理不明即停止；不按结果换题、不自动重跑。该批准不包含正式 Harbor、官方患者、judge、发布或额外已见题回归；若走正式 Harbor 必须另满足其供应/授权条件并如实标注。本段是草案，当前未授权任何执行。

## 4. 16C 与正式路径边界

- 新 B 单列，不计入 16C；九题先跑；剩余最多 7 次不自动用满。
- 不先跑独立摘要/恢复 CHI 探针；摘要/恢复默认 off 且互斥，Y off。
- 九题后若改候选，旧九题成为旧候选开发集；剩余 7 次不足以重做完整九题未见验证，须明确较小分母或保持原候选，不能改名冒充未见。
- 正式 Harbor 与九题同次取证只在全部正式供应/授权条件满足时成立，且只计一次 C；开发 operator 证据不能冒充正式 Harbor。
- CM 正式患者路径与包外 Go 模拟器分列；官方 Anthropic 患者/judge 另需合法环境和授权。

## 5. 明确不做

- 不启动任何真实请求、world、Trial、judge 或发布。
- 不修改生产功能、参数、阈值、额度、依赖、提示或工具权限。
- 不 rebind/迁移/核销/清 pending，不另建账根假装历史为零。
- 不读取/上传 Key、.env、手册、数据、vendor、原始轨迹或受限载荷。
- 不把本草案、PR 合并或候选存在当作真实运行许可。
