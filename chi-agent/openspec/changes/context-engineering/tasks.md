# 任务清单：上下文工程与执行可靠性

状态：**离线实现完成，待独立复审与用户合并。** 本清单只记录实现与测试；真实 B/C、judge、Trial、发布不在本变更内。
施工决定（Q1–Q6）见 [decisions.md](decisions.md)。

## P0 预算模型 v3

- [x] `go_chi_context.py`：新增 `chi-context-v3`，输出 `total_bytes`、`estimated_tokens_upper`、`estimated_tokens_calibrated`、`bytes_per_token_actual`（校准函数）。
- [x] 删除 v3 的 `max_chars`；硬门禁改为 `U ≤ max_input_tokens` 且 `bytes ≤ max_context_bytes`；v1/v2 只读分支保留。
- [x] 触发线改为 `U ≥ 0.8 × max_input_tokens`；装配投影阈值使用 50%。
- [x] `go_chi_policy.py`：预算常量与模型 profile（`provider_context_tokens`、`window_safety_fraction`、`bytes_per_token_floor`、`bytes_per_token_observed`）。
- [x] 启动校验：运行时模型与 profile 一致，否则 fail closed。
- [x] `run_log`/journal 新字段；旧 v2 证据只读兼容。
- [x] 测试：单位、边界、模型 profile、旧证据兼容、极端输入（纯中文/JSON/emoji）。

## P1 上下文装配

- [x] `go_chi_tools.py`/`go_chi_mcp.py`：文本类工具层 8K 码点 / 32KB 字节截断；头 4096 + 尾 1024 + `truncated`/`next_offset`。
- [x] 完整结果先写 evidence，再返回截断版。
- [x] `max_results`：默认 10、上限 20、单文件 50；`total_matches`/`omitted`；可操作错误；重复违反后 clamp 并记录 `requested`/`effective`。
- [x] reducer：列表/详情/数组/未知工具四类规则（保守实现）。
- [x] 去重：`result_sha256` 相同只留引用。
- [x] wire 投影：read 占位符；mutation 规范记录；refused/failed 规范记录。
- [x] 投影 hash 写入 journal；确定性校验。
- [x] reasoning 不裁剪（本阶段）。
- [x] 测试：截断边界、evidence 完整性、reducer 合法性、占位符可回读、mutation 不被替换、投影确定性。

## P2 状态与意图锚点

- [x] `go_chi_state.py`：事实分层与来源标记；v3 下 `local-state-update` 只能写 L2。
- [x] 锚点生成：目标/对象/非目标/当前步骤/验收/禁止；`anchor_sha256`。
- [x] 锚点注入 `messages[2]`；阶段由程序从 observations 推导。
- [x] `go_chi_contract.py`：`validate_history` 允许恰好一条锚点。
- [x] 漂移检查：硬违规、软漂移；复用 `refuse_tool`；同类 2 次、run 内 3 次上限。
- [x] journal：`drift_events`、锚点 hash（在 projection 记录中）。
- [x] 测试：锚点缺失/重复/hash 不符、事实越权、硬/软漂移、警告上限、阶段推进。

## P3 完成门禁

- [x] `mandatory_claim`：无 claim 的最终文本判 `incomplete`（runtime `chi_claim_required`）。
- [x] 程序推导证据：journal/TaskState/observations，模型引用不作证据。
- [x] 执行/验证分离：终态 mutation 必须回读。
- [x] 负证据：role guidance 必要步骤缺失即 block。
- [x] 终态对象：payer/provider/CM/拒绝类各定义。
- [x] `go_chi_entry.py` 完成输出与 run_log 字段（v5）。
- [x] 测试：无 claim、假 claim、缺回读、缺步骤、无动作结局、正常路径回归。

## P4 检索 L0

- [x] 目录/标题/章节索引（内存构建；不写盘、不跟链接）。
- [x] 元数据过滤：role、category、year、service、doc_type。
- [x] 命中返回 path/行/章节/hash；引用前用 `read_hit` 回读并校验 hash。
- [x] 修 `max_results` 规则与错误信息。
- [x] 测试：索引一致性、过滤、回读、无效参数、单文件上限。

## P5 兼容、测试与文档

- [x] 定向测试 + 全量 `unittest discover`；记录既有 import error。
- [x] 旧 v2 证据 inspect 回归（v2/v1 分支与 unmodified evidence）。
- [x] bundle/runtime 身份变化说明；重建步骤写入阶段报告。
- [x] 文档：README/运行手册/学习账本/阶段报告。
- [x] 复审 P1-1：旧字节 flag 语义恢复；新增 `--context-max-input-tokens`；role_operator/entry 范围一致。
- [x] 复审 P1-2：v3 + recovery/summary 显式拒绝（`chi_context_policy_incompatible`）。
- [x] 复审 P1-3/P1-4：JSON 结构化截断；reducer 支持 `result/data/records/rows`。
- [x] 复审 P1-5/P1-6：终态只接受 `returned`；投影使用完整 evidence hash。
- [x] 复审 P1-7：新错误码注册到 diagnostics。
- [x] 复审 P2：锚点 wire 校验、role alias、索引缓存、next_offset 单位、50% 阈值、README/runbook 迁移说明。
- [ ] 独立复审；0 Blocker 后再谈真实运行。
- [ ] 用户最终合并；不 auto-merge。

## 不在本变更内

- 240s 读超时覆盖（另立小变更，建议先做）；
- 向量 RAG / L1 / L2；
- 任务级 resume；
- LLM 摘要与 recovery 的组合；
- 真实 B/C、judge、Trial、发布。

## 停止条件

- 任一离线测试出现未解释失败；
- 旧证据不可读或身份校验失败；
- 需要真实模型才能验证的项，停止并另立授权。
