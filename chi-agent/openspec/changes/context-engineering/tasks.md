# 任务清单：上下文工程与执行可靠性

状态：**设计已定，未实现。** 本清单只用于离线实现与测试；真实 B/C、judge、Trial、发布不在本变更内。

## P0 预算模型 v3

- [ ] `go_chi_context.py`：新增 `chi-context-v3`，输出 `total_bytes`、`estimated_tokens_upper`、`estimated_tokens_calibrated`、`bytes_per_token_actual`。
- [ ] 删除 `max_chars`；硬门禁改为 `U ≤ max_input_tokens` 且 `bytes ≤ max_context_bytes`。
- [ ] 触发线改为 `U ≥ 0.8 × max_input_tokens`。
- [ ] `go_chi_policy.py`：预算常量与模型 profile（`provider_context_tokens`、`window_safety_fraction`、`bytes_per_token_floor`、`bytes_per_token_observed`）。
- [ ] 启动校验：运行时模型与 profile 一致，否则 fail closed。
- [ ] `run_log`/journal 新字段；旧 v2 证据只读兼容。
- [ ] 测试：单位、边界、模型 profile、旧证据兼容、极端输入（纯中文/JSON/emoji）。

## P1 上下文装配

- [ ] `go_chi_tools.py`：文本类工具层 8K 码点 / 32KB 字节截断；头 4096 + 尾 1024 + `truncated`/`next_offset`。
- [ ] 完整结果先写 evidence，再返回截断版。
- [ ] `max_results`：默认 10、上限 20、单文件 50；`total_matches`/`omitted`；可操作错误；重复违反后 clamp 并记录 `requested`/`effective`。
- [ ] reducer：列表/详情/数组/未知工具四类规则。
- [ ] 去重：`result_sha256` 相同只留一份。
- [ ] wire 投影：read 占位符；mutation 规范记录；refused/failed 规范记录。
- [ ] 投影 hash 写入 journal；确定性校验。
- [ ] reasoning 不裁剪（本阶段）；保留开关与 TODO。
- [ ] 测试：截断边界、evidence 完整性、reducer 合法性、占位符可回读、mutation 不被替换、投影确定性。

## P2 状态与意图锚点

- [ ] `go_chi_state.py`：事实分层与来源标记；`local-state-update` 只能写 L2。
- [ ] 锚点生成：目标/对象/非目标/当前步骤/验收/禁止；`anchor_sha256`。
- [ ] 锚点注入 `messages[2]`；阶段切换时更新。
- [ ] `go_chi_contract.py`：`validate_history` 允许恰好一条锚点。
- [ ] 漂移检查：硬违规、软漂移；复用 `refuse_tool`；计数与上限。
- [ ] journal：漂移事件、锚点 hash。
- [ ] 测试：锚点缺失/重复/hash 不符、事实越权、硬/软漂移、警告上限、阶段推进。

## P3 完成门禁

- [ ] `mandatory_claim`：无 claim 的最终文本判 `incomplete`。
- [ ] 程序推导证据：journal + TaskState + requirements。
- [ ] 执行/验证分离：终态 mutation 必须回读。
- [ ] 负证据：必要步骤缺失即 block。
- [ ] 终态对象：payer/provider/CM/拒绝类各定义。
- [ ] `go_chi_entry.py` 完成输出与 run_log 字段。
- [ ] 测试：无 claim、假 claim、缺回读、缺步骤、无动作结局、正常路径回归。

## P4 检索 L0

- [ ] 目录/标题/章节索引（handbook 1,279 md + 11 pdf）。
- [ ] 元数据过滤：role、category、年份、服务、文档类型。
- [ ] 命中返回 path/行/章节/hash；引用前回读。
- [ ] 修 `max_results` 规则与错误信息。
- [ ] （可选，有证据再做）BM25 排序。
- [ ] 测试：索引一致性、过滤、回读、无效参数、单文件上限。

## P5 兼容、测试与文档

- [ ] 全量 `unittest discover` + 定向测试；记录既有 import error。
- [ ] 旧 v2 证据 inspect 回归。
- [ ] bundle/runtime 身份变化说明；重建步骤。
- [ ] 文档：README/运行手册/学习账本。
- [ ] 阶段报告与独立复审；0 Blocker 后再谈真实运行。
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
