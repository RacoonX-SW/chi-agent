# 设计：上下文工程与执行可靠性

建立：2026-11-08。来源：[proposal](proposal.md)。本文件只写设计与取舍；执行步骤见 [plan](plan.md)，验收场景见 [spec](specs/context-engineering/spec.md)。

## 1. 预算模型 v3

### 1.1 问题

- `max_estimated_tokens` 存的是 UTF-8 字节，字段名误导；
- `max_chars` 永远晚于字节上限触发（字符数 ≤ 字节数），是死参数；
- 触发线与硬门禁混用同一单位；
- 没有 token 侧报告字段，无法事后校准。

### 1.2 变量

| 变量 | 取值 | 含义 |
| --- | ---: | --- |
| `provider_context_tokens` | 按 Agent 模型 profile（DeepSeek = 1,000,000） | 模型窗口，事实值 |
| `window_safety_fraction` | 0.6 | 窗口安全系数 |
| `max_input_tokens` | 500,000（DeepSeek） | 输入预算 |
| `output_reserve_tokens` | 16,384 | 输出预留 = `main_max_tokens` |
| `bytes_per_token_floor` | 3.0 | 英文/JSON 保守下限 |
| `bytes_per_token_observed` | ~3.9（本路由） | 典型值，仅报告/校准 |
| `max_context_bytes` | 1,500,000 | 字节硬上限 |
| `max_chars` | 删除 | 死参数 |

### 1.3 推导

```text
window_cap = provider_context_tokens × window_safety_fraction − output_reserve_tokens
byte_cap   = max_context_bytes ÷ bytes_per_token_floor
max_input_tokens = min(window_cap, byte_cap)

U = ceil(bytes / bytes_per_token_floor)
硬门禁：U ≤ max_input_tokens 且 bytes ≤ max_context_bytes
触发线：U ≥ 0.8 × max_input_tokens
报告：C = round(bytes / bytes_per_token_observed)
```

DeepSeek 代入：`max_input_tokens = 500,000`；触发线 400,000 上界 = 1,200,000 字节；硬上限 1,500,000 字节。**行为与现状一致，只改语义与命名。**

### 1.4 证据

t022-rerun5 前 14 轮 `bytes / prompt_tokens`：3.68–4.08，均值 3.89。3.0 比实测最低值留约 18% 余量，覆盖英文里的重音字符、符号和密集 JSON。

### 1.5 模型无关

- 主 Agent 模型属于提交配置；私有任务用冻结配置；
- judge 与患者模拟器是 Claude，独立进程，不共享主 Agent 预算；
- 换 Agent 模型必须换 profile、重建 bundle、新 B；
- 启动时校验运行时模型与 profile 一致，否则 fail closed。

### 1.6 校准与安全阀

- 每次响应记录 `prompt_tokens_observed`、`bytes_per_token_actual`；
- 实际比例低于 floor 时记 warning；连续出现则在下次重建 bundle 时上调 floor；
- 校准常量固定在 bundle profile，不在运行时滑动。

## 2. 上下文装配

### 2.1 两层接缝

| 层 | 职责 | 说明 |
| --- | --- | --- |
| 工具层 | 单次结果上限、分页、防单次爆炸 | 完整结果先写 evidence，再返回截断版 |
| wire 投影层 | 历史累积压缩（reducer、去重、占位符） | SDK 历史保留完整；只投影发给模型的视图 |

只做工具层：22 次 8K 仍会累积到 ~176KB。只做投影层：单次 104KB 仍先进入内存和历史。两层都要。

### 2.2 分层顺序

```text
L0 输出预留（已有）
L1 工具层截断（新结果，始终启用）
L2 按工具 reducer（新结果）
L3 去重（相同 result_sha256）
L4 旧结果占位符 / 规范记录（wire 投影）
L5 reasoning 裁剪（暂缓）
L6 LLM 摘要（最后手段）
```

每层之后重新计量；够用就停。

### 2.3 工具层

- 文本类：单次 ≤ 8K 码点且 ≤ 32KB 字节；头 4096 + 尾 1024 + 中间标记；返回 `truncated`、`next_offset`。
- 完整结果先写 evidence，再返回截断版。
- `max_results`：默认 10、硬上限 20、单文件允许 50；返回 `total_matches`/`omitted`/`truncated`；错误信息带允许范围；安全数值参数重复违反 2 次后 clamp 并记录 `requested`/`effective`；路径/ID/mutation 永不 clamp。
- 中期加 BM25 排序，让“前 N 条”等于“最相关的 N 条”。

### 2.4 reducer

| 场景 | 保留 | 丢弃 |
| --- | --- | --- |
| 列表 | 选择/排序字段（id、case_id、status、urgency、日期） | 详情字段、重复回显 |
| 详情 | 当前步骤需要的字段 | 审计元数据、重复回显 |
| 数组过长 | 前 N 条 + `total` + `omitted` | 其余元素（可再查） |
| 未知工具 | 8K 上限，只截数组元素/超长字符串 | 不破坏 JSON 结构 |

示例：`list_intake_queue` 25 条 × 32 字段 = 60,959 字节 → 保留 8 字段 = 5,617 字节（降 90%）。

### 2.5 占位符

- read 类：旧结果替换为指针 `{call_id, tool, path, bytes, result_sha256, note}`；模型可按需重读。
- mutation 类：不换指针，保留程序生成的规范记录 `{call_id, tool, event, status, key_ids, result_sha256}`；防止重复执行。
- `refused`/`failed` 同样保留规范记录。
- 分类复用 `go_chi_recovery.py` 的 `READ`/`MUTATION` 集合。
- 禁止用模型写的摘要替代 mutation 记录。

### 2.6 reasoning

- 本阶段不做：只占约 10%，收益小；截断思维链可能误导，且可能影响 prefix cache。
- 若后续要做：保留最近 2 个完整批次，更早的整段丢弃，并单独做质量/成本对比。

### 2.7 触发与确定性

- 工具层与 reducer 始终启用；
- wire 投影只在超过预算阈值（如 50%）时启用；
- 投影必须确定性：相同历史 + 相同策略 → 相同 wire，并记录投影 hash。
- v3 的锚点每次请求都注入，但旧工具结果只在预算达到 50% 阈值时才投影；低压力时只增加锚点，不替换旧结果。
- `full_results` 单结果上限 8MB、总量上限 64MB；超限 fail closed（`chi_context_assembly_limit`），不得用截断结果冒充完整 evidence。

**v3 与 recovery/summary 的兼容边界（2026-11-08 复审）：** 本阶段不实现投影与 `output_recovery`/`input_summary` 的组合。entry、journal 和 guard 对 `context_policy=chi-context-v3` + 任一 recovery/summary 选项显式拒绝（`chi_context_policy_incompatible`），不得静默降级。现有带 recovery 的 config 必须先移除 recovery，或等组合实现后再运行。

### 2.8 预期收益

| 层 | 预期节省 |
| --- | ---: |
| 工具层 8K 上限 | ~170KB |
| MCP reducer | ~60KB |
| 旧 read 结果占位符 | ~150KB |
| 去重 | 视情况 |
| reasoning（暂缓） | ~55KB |

粗估：652KB → 150–250KB；prefill 从约 40s 降到 10–15s。

## 3. 多轮状态与意图锚点

### 3.1 状态分层

| 层 | 内容 | 谁能写 | 能否改 |
| --- | --- | --- | --- |
| L1 程序事实 | 工具事件、业务回读、文件 hash、绑定关系 | 只有程序 | 不可改 |
| L2 模型陈述 | 计划、判断、不确定性、下一步候选 | 模型 | 可改，标 `unverified` |
| L3 派生摘要 | 给模型看的压缩视图 | 程序 | 可重建 |

- 冲突原则：L1 永远压过 L2。
- `local-state-update` 只能写 L2 类字段；facts、target、binding 由程序独占。
- 每条状态项记录来源（program/model）与时间。

### 3.2 意图锚点

- 内容：目标、目标对象（case/patient）、非目标、当前步骤、验收条件、禁止动作。
- 位置：单独一条 user 消息，固定在 instruction 之后（`messages[2]`），作为稳定前缀。
- 生成：程序生成，模型不可修改；内容只在阶段切换时变化。
- 注入：每次请求都在前缀中；阶段切换时更新。
- 哈希：`anchor_sha256` 写入 launch/journal。
- 步骤：使用 role guidance 的固定阶段；只有程序能推进“当前步骤”，模型可提议但需程序校验。

实现影响：

- `validate_history` 允许恰好一条锚点消息（固定 schema + hash），批次从其后开始；
- recovery 的 body/view hash 与 summary 的 source body 必须包含并保留锚点；
- 锚点变化只在阶段边界，prefix cache 影响可控。

### 3.3 漂移检测

| 类型 | 例子 | 处理 |
| --- | --- | --- |
| 硬违规 | 跨患者、目标不符、禁用工具、未读先写、危险 mutation | 立即拒绝/停止 |
| 软漂移 | 重复同工具同参数、多余刷新、非破坏性步骤倒退 | 拒绝该次调用 + 返回原因，模型自行纠正 |

- 软漂移复用 per-call refusal（`refuse_tool`），不是只写日志。
- 上限：同类软漂移最多警告 2 次，整个 run 最多 3 次；超过升级为硬停止。
- 漂移事件写入 journal，包含规则名、call_id、次数。

### 3.4 中断恢复

- 暂不做任务级 resume；
- 设计成可对账：读操作幂等、mutation 有唯一 call_id 与结果 hash、pending 不自动重放；
- journal 继续保留 pending/halted 作为审计状态，不用于自动恢复。

## 4. 完成门禁

### 4.1 强制 claim

- 正式运行改为 `mandatory_claim`：没有 `local-claim_done` 的最终文本 → 状态 `incomplete`。
- `optional_final_text` 只保留给 shadow/开发模式。
- 修复 `final_text_without_claim_not_blocked`。

### 4.2 证据由程序推导

- 模型调用 `claim_done` 只是信号，不提供证据；
- 门禁从 journal + TaskState + requirements 程序化推导证据并逐项核对；
- 防止模型引用错误 ID 或编造证据。

### 4.3 执行与验证分开

| 阶段 | 要求 |
| --- | --- |
| 执行 | 有 mutation 工具事件且状态 returned |
| 验证 | 同一对象有后续回读且状态一致 |
| 交付 | 文件/决定对象存在且 hash 匹配 |

终态 mutation 必须有回读；中间步骤可只要求执行。

### 4.4 负证据检查

- 从 role guidance 派生必要步骤清单；
- 必要步骤没有任何对应工具事件 → 直接 block。

### 4.5 无动作结局

- 每类任务定义终态业务对象；门禁检查“终态对象 + 回读”，而不是“有没有写”。
- payer：determination；provider：submission；CM：care_plan/assessment；拒绝类：明确的 denied/stopped 状态对象。

### 4.6 风险

- 过度拦截：证据 schema 按角色固定，先在开发集校准；
- 任务类型差异：用终态对象覆盖无 mutation 的任务；
- 模型乱调 claim：claim 只是信号，证据由程序推导。

## 5. 检索

### 5.1 官方现状

- payer agent profile 不暴露 `payer_policy_library.search`（仅 full profile）；
- search 只对 title/filename/category 做子串匹配；
- handbook 位于 `/workspace/skills/managed-care-operations-handbook`，1,279 md + 11 pdf，按 role 分目录。

### 5.2 原则

- 结构化事实走 MCP 工具（诊断、用药、case 状态、表单要求）；
- 只有非结构化文本才走检索；
- 命中只是指针，引用前必须回读原文并记录 path/章节/hash。

### 5.3 分级

| 级别 | 做法 | 触发条件 |
| --- | --- | --- |
| L0（现在） | 目录/标题/章节索引；grep/BM25 + 元数据过滤；命中后读完整章节；引用章节号/文件名 | 立即做 |
| L1（有证据后） | 关键词 + 语义召回；元数据硬过滤；按标题/服务/年份重排；数值条件专门抽取 | L0 出现可复现的漏召回 |
| L2（最后） | 向量检索；本地小模型 + 运行时建索引；记录索引版本/构建时间；不把受限内容外发 | 失败案例证明是“同义/改写导致漏召回” |

### 5.4 本次两个具体问题

- `local-fs-search` 的 3 次拒绝是 `max_results=30` 超限（上限 20），不是召回失败；改为可操作报错 + 重复后 clamp。
- 104KB 保单整读：应走“TOC → 章节 → 回读”，配合 8K 上限/分页。

### 5.5 暂不做

- 不做纯向量 RAG；
- 不引入外部 embedding 服务；
- 不把 PDF 全文直接塞进上下文（先文本提取 + 分段）。

## 6. 代码触点与身份

| 模块 | 变更 |
| --- | --- |
| `go_chi_context.py` | v3 预算、双轨计量、删除 max_chars、报告字段 |
| `go_chi_policy.py` | 预算常量、模型 profile |
| `go_chi_guard.py` | 门禁/触发改用新字段；投影层；漂移检查；完成门禁 |
| `go_chi_tools.py` | 工具层截断、reducer、max_results 规则、锚点注入 |
| `go_chi_search.py` | total_matches/omitted、排序（L0 后续） |
| `go_chi_journal.py` | 新字段、requested/effective、anchor hash、投影 hash、漂移事件 |
| `go_chi_state.py` | 事实分层、来源标记、锚点步骤 |
| `go_chi_contract.py` | validate_history 允许锚点；完成门禁接口 |
| `go_chi_entry.py` | 新参数/校验、profile 绑定 |

预算常量、工具 schema、锚点格式变化都会改 bundle/runtime 身份：需重建 bundle + 新 B。

## 7. 兼容与迁移

- 新 schema：`chi-context-v3`、`chi-context-budget-v3`；
- 旧 v2 证据继续可读，不迁移、不改写；
- `run_log` 保留旧字段（标 legacy），新增 `estimated_tokens_upper`、`estimated_tokens_calibrated`、`prompt_tokens_observed`、`bytes_per_token_actual`；
- 旧 run 的 launch 无新字段时按旧语义解释。

## 8. 风险

| 风险 | 缓解 |
| --- | --- |
| 投影改变 prefix，影响缓存 | 只在阈值以上启用；确定性投影 |
| reducer 丢字段导致模型误判 | 保留选择/排序字段；`total`/`omitted`；可再查 |
| 锚点破坏 history 校验 | 固定 schema + hash；先写离线回归 |
| 完成门禁过度拦截 | 按角色固定证据 schema；开发集校准 |
| 检索索引与内容漂移 | 索引版本/hash；命中后回读原文 |
| 240s 读超时仍未解决 | 另立小变更；本变更验证前先处理 |

## 9. 证据

- t022-rerun5：15 轮、95 工具事件、652,663 字节、240,005ms 超时、0 次 length；
- t024-rerun6：6 轮、42 工具事件、228,995 输入、240,008ms 超时；
- `list_intake_queue` 60,959 字节 / 25 条 / 32 字段；
- `local-fs-read` 350,554 字节 / 22 次 / 最大 104,000；
- handbook 1,279 md + 11 pdf；payer agent profile 无 policy search。
