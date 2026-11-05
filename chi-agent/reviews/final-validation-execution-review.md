# 新B执行与九题验证准备（执行者检查）

日期：2026-11-06（Asia/Shanghai）。**结论：PR60 已合并；九题公开资源已按冻结 revision 获取并冻结，9/9 资源 manifest 通过 preflight；真实 B/九题仍未获本 Prompt 授权，未执行任何模型、world、MCP、Trial 或 judge 请求。** 本轮自查属于“执行者检查”，不是新的独立审核；既有 GPT 独立结论保持原义。

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

## 5. 文档与审批引用

- `openspec/changes/final-validation-admission/proposal.md` 第3节残留的旧候选短 SHA `500776…` 已更正为当前 `0df12589…`；其他审批引用已核对。
- `REVIEW_STATE` 已更新 PR60 合并事实、执行分支、资源 9/9 冻结及“执行者检查”边界。
- `tasks.md` 已勾选资源获取/冻结，保留新B、九题执行、正式Harbor/患者/judge 的未授权项。
- 旧候选 JSON、旧审批文件、旧导出包和旧结论未覆盖；资源冻结写入新文件。

## 6. 未执行 / 未验证

- **新 B 未执行**：本 Prompt 未包含“用户另外明确批准、绑定候选和 B 计划原文”的真实调用许可；未创建真实 attempt/journal/state，未占用请求额度。
- **九题未执行**：资源已到齐，但真实九题仍需另行具体批准；未启动 world/MCP/患者/模型。
- 真实 world/MCP 检查必须放在将来获批运行启动后、首个模型请求前完成；本轮未做。
- 正式 Harbor 供应/CLI/state/患者/清理、官方 judge、官方分数、Writeup/报告/发布仍未验证。
- 开发 `role_operator` 路径只能标为开发验证，不是正式 Harbor。
- payer-010 旧 unknown 处置仍需用户二选一；新隔离 root 不解决旧历史。

## 7. 下一项可直接批准的文本

### 7.1 一次新 coding-B（仍待用户明确批准）

> 我确认保留 `real-ext-payer-010` round1 的结果/token 未知及不完整费用，不修改旧 pending、不认定零发送或已结算；该决定只关联候选清单 SHA `0df12589c851b38423e6212997e7f4b9214912c25b7c84d7614f30e0c5f493d0`、B 计划 SHA `19ea22a3ab362af78c13c285b964b7fb95c6b22a45a34f557f9e5bb18c588672`、`eval-final-20261105` 及新隔离 state。允许执行 `final-b-001` 一次 coding-B，最多 6 个 provider HTTP，参数、用途、记录、停止和清理按该计划。暂不授权摘要/恢复、任何 CHI C、患者、world、Trial、判分或发布；旧 unknown 和旧 B 许可仍不结算、不复用。

### 7.2 九题开发验证（资源已就绪，仍待另行批准）

完整审批包：`reviews/nine-task-approval-draft-20261106.md`（草案，未授权）。

> 九题资源已按预登记 SHA `bb9d7930…` 和冻结 revision 获取并生成 9 份 manifest；待新 identity B 成功且收据适用、payer-010 处置明确后，允许按预登记执行 9 次开发 `role_operator` C：provider/UM/CM 各 3 题、每题一次、新 world，使用候选 SHA `0df12589…` 与预登记 SHA `bb9d7930…`。provider/payer 每 run 主+确认≤50 HTTP，CM 另加开发患者辅助≤10；确认≤2；不启用摘要/恢复/Y。任一 unknown、pending/halt、越界写、清理不明即停止；不按结果换题、不自动重跑。该批准不包含正式 Harbor、官方患者、judge、发布或额外已见题回归。

## 8. 交接

- 分支：`deepseek/final-validation-execution`；实现/文档提交 `c5501fc…`，已 push 到 origin。
- PR：[PR61](https://github.com/xsw932187210-cell/chi-agent/pull/61) 已创建，base=main；未 merge/auto-merge。
- 详细资源冻结：`reviews/nine-task-resource-freeze-20261106.json`；候选/预登记/B 计划原字节未改。
- 本报告是执行者检查，不替代 GPT 独立复审；GPT 暂无额度不阻塞本轮离线准备，但真实 B/九题仍须用户另行明确批准。
