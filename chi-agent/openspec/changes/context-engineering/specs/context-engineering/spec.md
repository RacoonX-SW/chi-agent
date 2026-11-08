# 上下文工程验收场景

本文件冻结五项能力的离线验收场景；实现必须逐项覆盖。真实模型/B/C/Trial/judge/发布不在本契约内。

## A. 预算模型 v3

### A1 单位与命名
- Given 一个请求体；
- When 计量；
- Then 输出 `total_bytes`、`estimated_tokens_upper`、`estimated_tokens_calibrated`，且 `upper >= calibrated`；字段名不再用 `max_estimated_tokens` 表示字节。

### A2 硬门禁
- Given `U = ceil(bytes / 3.0)`、`output_reserve=16384`；
- When `U > max_input_tokens` 或 `bytes > max_context_bytes`；
- Then 拒绝发送，错误为 `chi_context_budget_exceeded`；`calibrated` 不影响拒绝。

### A3 触发线
- Given `max_input_tokens=500000`；
- When `U >= 400000`；
- Then 标记可压缩；差 1 token 时不标记。

### A4 模型 profile
- Given 运行时模型与 profile 不一致；
- When 启动；
- Then fail closed（`chi_config_invalid` 或等价），不按旧预算继续。

### A5 校准
- Given 一次响应返回 `prompt_tokens`；
- When 记录；
- Then 写 `prompt_tokens_observed` 与 `bytes_per_token_actual`；实际比例低于 floor 时记 warning，不运行时改阈值。

### A6 旧证据兼容
- Given 旧 v2 预算/证据；
- When 读取；
- Then 仍可 inspect；不迁移、不改写、不重算。

## B. 上下文装配

### B1 工具层截断
- Given 单次文本结果超过 8K 码点或 32KB 字节；
- When 返回给模型；
- Then 返回头 4096 + 尾 1024 + 中间标记，带 `truncated: true` 与 `next_offset`。

### B2 evidence 先写
- Given 一个工具结果；
- When 记录；
- Then 完整原文先写 evidence，再返回截断版；`result_sha256` 对应完整原文。

### B3 reducer
- Given 列表类 MCP 结果；
- When 投影；
- Then 只保留选择/排序字段，返回 `total`/`omitted`；输出仍是合法 JSON。

### B4 去重
- Given 两条结果 `result_sha256` 相同；
- When 投影；
- Then 只保留一份，另一份换成引用。

### B5 read 占位符
- Given 旧 read 结果；
- When 投影；
- Then 换成 `{call_id, tool, path, bytes, result_sha256, note}`；原文仍可从 evidence/重读获得。

### B6 mutation 规范记录
- Given 旧 mutation 结果；
- When 投影；
- Then 保留程序生成的 `{call_id, tool, event, status, key_ids, result_sha256}`；不得用模型摘要替代；不得换成指针。

### B7 reasoning
- Given 本阶段配置；
- When 投影；
- Then 不裁剪 reasoning；若未来启用，保留最近 2 个完整批次，更早的整段丢弃。

### B8 重计量与确定性
- Given 任一层执行后；
- When 重新计量；
- Then 够用即停；相同历史 + 相同策略产生相同 wire 与投影 hash。

## C. 多轮状态与意图锚点

### C1 事实分层
- Given 模型通过 `local-state-update` 写 facts/target；
- When 门禁校验；
- Then 拒绝；facts/target/binding 只能由程序写。

### C2 意图锚点
- Given 一个 run；
- When 构造请求；
- Then `messages[2]` 是程序生成的锚点 user 消息，含目标/对象/非目标/当前步骤/验收/禁止；`anchor_sha256` 写入 journal。

### C3 锚点与 history
- Given 锚点存在；
- When `validate_history` 校验；
- Then 允许恰好一条锚点，批次从其后开始；缺失、重复或 hash 不符即拒绝。

### C4 漂移硬违规
- Given 跨患者、目标不符、禁用工具、未读先写或危险 mutation；
- When 校验；
- Then 立即拒绝/停止，不执行该批。

### C5 漂移软处理
- Given 重复同工具同参数、多余刷新或非破坏性步骤倒退；
- When 校验；
- Then 拒绝该次调用并返回原因；同类最多 2 次、run 内最多 3 次，超过升级为硬停止。

### C6 恢复
- Given 本阶段配置；
- When run 中断；
- Then 不做任务级 resume；pending 仅作审计，不自动重放。

## D. 完成门禁

### D1 强制 claim
- Given 模型只输出最终文本、未调用 `local-claim_done`；
- When 结束；
- Then 状态为 `incomplete`，不得判为成功。

### D2 程序推导证据
- Given 模型调用 `claim_done`；
- When 门禁核对；
- Then 证据全部由 journal/TaskState/requirements 推导；模型提供的引用不作为证据。

### D3 执行与验证
- Given 终态 mutation；
- When 门禁核对；
- Then 必须有同对象回读且状态一致；只有执行记录不足以通过。

### D4 负证据
- Given role guidance 要求的必要步骤；
- When 没有任何对应工具事件；
- Then 直接 block。

### D5 无动作结局
- Given 任务正确结果是拒绝/停止/转交；
- When 门禁核对；
- Then 以终态业务对象（denied/stopped 等）判定，而不是要求必须有写。

## E. 检索

### E1 结构化事实走工具
- Given 诊断、用药、case 状态或表单要求；
- When 需要取值；
- Then 使用 MCP 工具；不得用文档检索猜。

### E2 L0 检索
- Given 政策/手册查询；
- When 搜索；
- Then 支持目录/标题/章节索引与元数据过滤（role、category、年份、服务、文档类型）；命中返回 path/行/章节/hash。

### E3 指针与回读
- Given 搜索命中；
- When 引用；
- Then 必须回读原文；命中本身不作为来源权威。

### E4 `max_results`
- Given 目录搜索；
- When `max_results` 缺省；
- Then 默认 10、上限 20；单文件允许 50；返回 `total_matches`/`omitted`。
- Given `max_results=30`；
- When 校验；
- Then 第一次返回可操作错误（允许范围 + 实际值）；同类重复 2 次后 clamp 并记录 `requested`/`effective`/`capped`。
- Given 路径/ID/mutation 参数非法；
- When 校验；
- Then 永不 clamp，严格拒绝。

### E5 L1/L2 门槛
- Given L0 没有可复现的漏召回；
- When 规划；
- Then 不引入语义/向量检索；引入 L1/L2 必须附失败案例、索引版本与回读规则。
