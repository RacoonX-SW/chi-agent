# 计分相关离线加固执行清单

本清单只勾工作完成；当前候选/许可只见[REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。实施以[proposal](proposal.md)及[design](design.md)为准，文档通过不代表生产实现或真实运行已获准。

## 0. 本轮规划交付

- [x] 合并后刷新主线，核对工作区及写入者，从最新main建GPT文档分支。
- [x] 写清P0–P5取舍、额外接缝、A–D改法/反例验收、16C/九题与真实授权边界；按用户最新决定移除E，摘要生成预算另行专项。
- [x] 提供DeepSeek启动Prompt及固定候选交GPT复审流程；解释摘要输入/输出和既有恢复边界。
- [x] 文档差异/本地链接/源码符号及现行参数静态检查；不做功能测试，不挂凭据/账本/任务数据。

本规划的提交/push及base=main PR以实际Git/PR记录为准；用户最终合并，不自动实施。

## 1. DeepSeek后续离线实施（已完成本地候选，待GPT复审）

- [x] 重新核实main/PR/分支/未提交改动/单写入者，建立`deepseek/score-readiness-hardening`及独占测试输出。
- [x] A：完成来源、业务/文件读写、共同诊断；先独立反例，保持未知/claim保护及旧版本含义，不加自动补发/最终硬门禁（`916ef48`）。
- [x] B：本地工具schema/描述/实现对照和实际接缝反例；既有index与MCP错误回归；P0未复现当前缺陷，交回不改证据（`fe50ffc`）。
- [x] C：隔离包实际身份、正式/开发off配置与角色/工具/资源/依赖/状态/日志供应检查；不启用能力、不启动真实world或Trial（`ea2e987`）。
- [x] D：安全诊断不被外层精简日志覆盖；现有plans/gaps指导；分候选/角色的只读余量盘点，不改参数或额度（`0e9d079`）。
- [x] 每卡固定提交/实际命令与结果；原始受限证据本地，详细结果集中一份实施报告，短状态仅REVIEW_STATE。
- [x] 必要SDK MockTransport集成及包/identity/profile/旧历史兼容核验；skip/环境缺项原样列出。
- [x] 固定最终SHA、完整diff/包身份、默认配置、未改/未验项交GPT定向只读复审；用户最终决定Git交付/合并。

## 1a. 初审不通过后的定向返工（已完成本地候选，待GPT复审）

- [x] R1：同文件资源合法修复后才解除交付失败；保留失败记录，无关路径/其他case/role、unknown 和后续失败仍阻断（`f2ecd84`）。
- [x] R2：runtime log 的 physical_requests/usage/completion/target/claim 等结构、嵌套键、类型和有限错误码严格校验；非法字段明确 fallback（`af08fe9`）。
- [x] R3：只读盘点改为同快照 SHA-256 绑定；缺失/损坏/截断/空文件与确认无事件分开，删除不可配对的估计准确率指标；旧 inventory-v1 保留，新 inventory-v2 在忽略目录。
- [x] R4：状态来源描述按 role/canonical 工具精确化；补独立接受/拒绝测试；更正 8 个 skip 的覆盖表述（operator 3 项另跑通过）（`e9c503a`/`e945504`）。
- [x] 返工后适用 pytest `948 passed/8 skipped/333 subtests`、controller `12 OK`、operator `3 OK`；anthropic 两模块 collection error 单列。
- [x] 重建 Go/evaluation/release 并做隔离 preflight；新 manifest/runtime/release 与 source_commit 见报告第10节；旧 B 不适用。
- [x] 旧 S 账严格只读验证保持原 hash/失败/20 settled；详细证据追加到同一报告，不覆盖初审不通过。

## 2. 明确不随本轮启动

- [ ] 新候选coding-B（必要性/具体次数/状态/身份另行批准，不算入16次C）。
- [ ] 同候选九题未见集及最多16C方案（预登记/污染/资源与每次上限另批，合并不是许可）。
- [ ] 摘要方案B选区上限、新义务清单硬门禁、提高患者额度或其他参数变更（不属本实施；另立方案）。
- [ ] 独立摘要预算专项的真实兼容/忠实度/净费用收益（不属于A–D实施；若先独立CHI探针须明改九题优先计划并计入16C）。
- [ ] 正式真实Harbor/官方患者/判分/发布及Z8最终发送（逐项供应/真实授权，不由本清单勾选自动恢复）。
