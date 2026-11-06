# 故障处理分层：输出契约、业务前置条件、连接前重试

建立：2026-11-07（Asia/Shanghai）。状态：**设计文档，未实现、未运行、未授权真实模型/B/C/Trial/judge/发布。** 本页只定义三类故障的处理边界、恢复上限、错误反馈和验收场景；reasoning/输出预算（t022）另立设计，不在本页处理。

## 1. 目标与非目标

目标：把“测一题修一题”改成按类处理：

1. **输出契约层**：模型 response shape、tool name、call id、arguments JSON 语法、arguments schema 的统一校验与有界重生成。
2. **业务/工具前置条件层**：状态/业务拒绝、文件写入的目录前置条件、可确定修正与业务失败的区分。
3. **基础设施层**：只对“连接建立前失败”做有界重试；读响应超时、429/5xx、未知副作用继续保守停止。

非目标：

- 不解决 reasoning 吃满 8192 output 的生成预算问题（t022）；另立设计。
- 不改变输入 context budget（`chi-context-budget-v2` / 1.5M 实验）。
- 不判断临床正确性、官方得分或语义完成；`official_reward=null`。
- 不自动重试业务写、工具调用或未知副作用的请求。
- 不把任何 unknown/pending 静默清成成功。

## 2. 统一故障分类

| 层 | 失败类 | 典型现象 | 是否可恢复 | 处理 |
| --- | --- | --- | --- | --- |
| 输出契约 | `response_shape` | assistant message 多/少字段、`name:null`、finish_reason 异常 | 条件可恢复 | 允许的 shape 归一化；真正非法则结构化反馈/有界重生成 |
| 输出契约 | `arguments_json` | tool arguments 不是合法 JSON | 可恢复（有界） | 整批原子 REFUSED，返回 `chi_tool_arguments_json_invalid`，不执行任何 call |
| 输出契约 | `tool_unknown` | 模型调用不存在的工具 | 可恢复（有界） | 返回工具名错误 + 可用工具提示；不执行 |
| 输出契约 | `call_shape`/`call_id` | call 结构非法、id 重复/非法 | 可恢复（有界） | 整批 REFUSED；不执行 |
| 输出契约 | `arguments_schema` | 缺必填字段、未知字段、类型错误 | 可恢复（有界） | 整批 REFUSED；返回字段/路径/允许字段；不执行 |
| 生成预算 | `output_length` | `finish_reason=length`、reasoning 吃满 output | 条件恢复 | 另立设计；本页只保证不被误判为 output contract |
| 业务前置 | `state_refusal` | `chi_state_*`、target/readback 不满足 | 可恢复（模型 replan） | 现有 REFUSED 工具结果；不自动重试；completion 继续门禁 |
| 业务前置 | `workspace_parent` | CM case 根目录不存在、路径越界 | 可确定修正 | 在 case 已观察/绑定且路径 allowlist 内时创建 case 根/角色目录；否则 REFUSED |
| 业务前置 | `file_write_failed` | 文件写失败/被拒 | 可恢复（模型修正路径/内容） | 返回可操作错误；completion 仍 blocked，直到修复或明确失败 |
| 基础设施 | `connect_before_send` | TCP/TLS 连接建立失败，请求未发出 | 可安全重试 | 有界重试；不产生 usage/pending；每次记录 attempt |
| 基础设施 | `read_timeout`/`unknown_response` | 请求已发出，读响应超时/断连 | **不可盲目重试** | 保留 pending/unknown；停止或显式对账 |
| 基础设施 | `429`/`5xx` | 服务端拒绝/暂时不可用 | 条件可重试 | 本页不自动重试；未来按预算/usage 对账另定 |
| 基础设施 | `tool_business_write_unknown` | 写工具超时/断连 | **不可重试** | 查状态/对账；不得重复写 |

## 3. 输出契约层

### 3.1 校验范围

在工具执行前校验：

- assistant message：`role`、`content`/`reasoning_content` 类型、`tool_calls` 形状、允许的可选字段（含 `name`）。
- `finish_reason`：`stop`/`tool_calls`/`length` 的边界；`length` 归生成预算层，不归本层。
- 每个 tool call：call id 格式/唯一性、tool name 存在、arguments 是合法 JSON、arguments 符合 schema。
- 整批原子性：任一 call 非法时，**整批不执行**，全部标记 REFUSED。

### 3.2 反馈格式

- 返回短、结构化、可操作的错误，例如：
  - `REFUSED: chi_tool_arguments_json_invalid: cm_care_plan__save_care_plan: invalid JSON at arguments`
  - `REFUSED: chi_tool_arguments_invalid: local-state-update: unknown field(s) put_plans at $`
  - `REFUSED: chi_tool_arguments_invalid: cm_outreach__send_message: missing required field(s) session_id at $`
- 不包含参数值、患者信息、完整 schema 或隐藏材料；只含工具名、字段名/路径、缺失字段、允许字段（短列表）。
- 失败原因写入 tool evidence/journal，供复审计数。

### 3.3 有界重生成

- 每个失败类最多 2 次；每 run 总恢复上限 3 次（建议值，待实现测试确认）。
- 同一 tool+字段/同一错误重复出现时，第二次后不再继续，直接安全停止，避免循环。
- 重生成只在同一 run 内；不自动重跑整题、不换 state、不换根。
- 每次 REFUSED 都记录 `schema_refusals`/`json_refusals` 等计数，run log 可观测。
- 达到上限后仍按现有 `chi_tool_batch_invalid`/`chi_response_invalid` 安全停止；不静默成功。

### 3.4 与生成预算的边界

- `finish_reason=length` 不进入本层；由 output recovery/生成预算层处理。
- 本层允许 `name` 为 string/null；不因为 `name:null` 把 length 响应误判为 `chi_response_invalid`。
- 真正的 response shape 非法（例如缺少 role、tool_calls 类型错误）才走 `chi_response_invalid`。

## 4. 业务/工具前置条件层

### 4.1 状态/业务拒绝

- `chi_state_*` 继续作为工具结果返回；模型 replan，不自动重试。
- target/readback/completion 门禁不放宽；`completion_readback_required` 仍 blocked。
- 不把“业务前置不满足”误判为模型格式错误。

### 4.2 文件写入前置条件（CM case root）

- 现状：`local-fs-write` 只创建 case 下的子目录，不创建 case 根；CM 的 `CM-CASE-...` 根目录未被任何工具创建，导致 `ERROR: workspace parent unavailable`。
- 设计：
  - case 已在 state observations/target 中观察或绑定；
  - 路径符合 `<case_id>/<role|shared>/...` allowlist；
  - 角色/大小写/隐藏路径检查通过；
  - 才允许创建缺失的 case 根和角色目录（mode 0700），再写文件。
- 不允许：
  - 为未观察/未绑定的 case 创建目录；
  - 跨 case、越界、symlink、fixture/hidden/verifier 路径；
  - 用文件写入绕过业务写/状态门禁。
- 错误信息应可操作，例如 `ERROR: workspace_parent_missing: create or select the case workspace first`，而不是只有 `workspace parent unavailable`。
- completion 仍以文件写成功/失败为准；失败不得 claim。

### 4.3 明确执行失败

- 下游明确回滚/失败：降级、换工具或结束；不得重试同一写请求。
- 失败文件写可由后续同路径成功写修复；否则 blocked。

## 5. 基础设施层：只加“连接前”重试

### 5.1 请求阶段

1. **connect**：TCP/TLS/连接池建立；请求字节尚未发出。
2. **send**：请求已写入连接。
3. **read**：等待/读取响应。

### 5.2 策略

- 只有 **connect 阶段失败** 才允许有界重试：
  - 建议最多 2 次额外尝试，指数退避（例如 0.5s/1s），受总预算/1800s 约束。
  - 不产生 provider usage；不创建/保留 pending；每次 attempt 记录在 journal/run log。
  - 重试仍失败 -> 安全停止，错误码仍为 `chi_timeout`/`chi_http_error`。
- **send 后/read 阶段失败**：
  - 不自动重试；请求可能已执行/已计费；保留 pending/unknown，停止或显式对账。
- **429/5xx**：
  - 本设计不自动重试；未来若加，必须结合 usage 对账、预算和幂等性另立设计。
- **工具/业务写**：
  - 基础设施层不重试任何工具调用或业务写；写未知副作用走 pending/查状态。
- 不改变现有零自动重试的默认；连接前重试作为可配置/受控策略，默认关闭或单独开关。

## 6. 跨层不变量

- 任一层都不得把 unknown/pending 静默转为成功。
- 输出契约层的 REFUSED 不执行任何 call；业务层的 REFUSED 不伪造业务状态；基础设施层的重试不重复业务写。
- completion/claim 门禁仍是最终门禁；`official_reward=null`。
- 旧 pending/旧 state/旧证据保持原义；不因新代码回写旧结论。
- 所有恢复/重试都有界、可观测、可停止；不自动换题/换根/整题重跑。

## 7. 测试矩阵（离线）

### 输出契约

- `name:null` + `finish_reason=length`：允许进入 recovery，不再 `chi_response_invalid`。
- arguments JSON 非法：整批 REFUSED，无 call 执行；模型纠正后成功。
- 缺必填字段/未知字段：REFUSED 原因含字段/路径；整批原子。
- 第 3 次同类错误：安全停止，run log 有计数。
- 合法批次/off 路径：行为不变。
- 反馈不含参数值/PHI/完整 schema。

### 业务前置

- CM case root 缺失 + case 已观察/绑定 + allowlist：创建根目录并写入成功。
- 未观察 case/越界/跨 case/symlink：拒绝，不创建目录。
- 文件写失败：completion blocked，不 claim；后续同路径成功写可修复。
- provider/payer 既有路径行为不变。

### 基础设施

- connect 前失败：有界重试，无 usage/pending；成功或最终安全停止。
- read 超时/断连：不重试，pending/unknown 保留。
- 429/5xx：本设计下不自动重试。
- 工具/业务写：不重试。

## 8. 待讨论

1. 输出契约每类/每 run 的具体上限（2/3 是否合适）。
2. JSON 语法错误的 REFUSED 如何返回给 SDK（需要 guard/contract/wrapper 的调用链设计）。
3. CM case root 创建是否需要额外 state 绑定条件（observed/target）。
4. 连接前重试的开关、次数、退避和 journal 字段；是否只用于 C，不用于 B。
5. 429/5xx 是否另立预算/对账设计；本页不包含。
6. reasoning/output 预算（t022）另立设计，不与本页混合。
