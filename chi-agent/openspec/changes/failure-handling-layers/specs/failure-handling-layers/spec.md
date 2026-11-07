# 故障处理分层验收场景

本文件冻结三类故障的离线验收场景；实现必须逐项覆盖。真实模型/B/C/Trial/judge/发布不在本契约内；reasoning/输出预算另立设计。

## A. 输出契约层

### A1 `name` 与 length 响应
- Given 主请求返回 `finish_reason=length`，assistant message 含 `name:null`、`content` 为空、`tool_calls` 为空；
- When 开启 output recovery；
- Then 允许进入 recovery 形状判定，不得直接 `chi_response_invalid`；recovery 仍受既有上限约束。

### A2 arguments JSON 非法
- Given 模型 tool call 的 arguments 不是合法 JSON；
- When 开启输出契约恢复；
- Then 整批原子 REFUSED，返回 `chi_tool_arguments_json_invalid`；不执行任何 call；模型可用新 call 重试一次。

### A3 schema 非法
- Given arguments 是合法 JSON 但缺必填字段/含未知字段/类型错误；
- When 开启输出契约恢复；
- Then 整批原子 REFUSED，原因包含工具名、字段/路径、缺失字段或允许字段短列表；不执行任何 call。

### A4 有界与重复
- Given 同一 run 内同类错误重复；
- When 达到每类 2 次或每 run 3 次恢复上限；
- Then 安全停止为 `chi_tool_batch_invalid`/`chi_response_invalid`；不无限循环；run log 记录恢复计数。

### A5 反馈安全
- Given 任意 arguments 含患者信息/长文本/敏感值；
- When 返回 REFUSED；
- Then 反馈不含参数值、PHI、完整 schema 或隐藏材料；只含工具名、字段/路径、缺失字段/允许字段。

### A6 off/合法路径回归
- Given 不开启输出契约恢复，或批次完全合法；
- Then 既有 `accept_batch` 默认行为、工具 schema/description、guidance digest 不变；合法 call 正常执行。

## B. 业务/工具前置条件层

### B1 CM case root 缺失
- Given case 已在 state observations/target 中观察或绑定；
- And 路径符合 `<case_id>/<role|shared>/...` allowlist；
- And case 根目录不存在；
- When 调用 `local-fs-write`；
- Then 创建缺失的 case 根/角色目录（0700）并写入成功；completion 可继续。

### B2 越界/未观察 case
- Given case 未观察/未绑定，或路径越界、跨 case、symlink、fixture/hidden/verifier；
- When 调用 `local-fs-write`；
- Then 拒绝，不创建目录；错误信息可操作；不写文件。

### B3 文件写失败仍 blocked
- Given 文件写失败/被拒；
- When completion/claim 评估；
- Then 仍 `completion_file_write_failed`，不得 claim；后续同路径成功写可修复；无关路径/未解决 unknown 仍阻断。

### B4 provider/payer 回归
- Given provider/payer 既有 case 根目录和写入路径；
- Then 行为不变；不因 CM bootstrap 改动放宽 provider binding 或 payer 路径。

## C. 基础设施层

### C1 connect 前失败
- Given 请求在 connect 阶段失败，尚未发送；
- When 启用连接前重试；
- Then 在预算内最多重试 N 次；不产生 provider usage、不创建 pending；每次 attempt 可审计；成功则继续。

### C2 read 超时/未知响应
- Given 请求已发出，read 阶段超时/断连；
- When 评估重试；
- Then 不自动重试；保留 pending/unknown；停止或显式对账。

### C3 429/5xx
- Given 服务端返回 429/5xx；
- When 本设计生效；
- Then 不自动重试；按既有 `chi_http_error`/pending 停止；未来另立预算/对账设计。

### C4 工具/业务写
- Given 工具调用或业务写超时/断连；
- Then 基础设施层不重试；查状态/对账；不得重复写。

## D. 跨层

### D1 不得静默成功
- Given 任一层出现 unknown/pending；
- Then 不得转为成功/claim；completion 仍按原门禁。

### D2 旧状态/旧证据
- Given 旧 pending、旧 state、旧证据；
- Then 保持原义；新代码不回写旧结论。

### D3 有界与可观测
- Given 恢复/重试；
- Then 每次都有上限、计数和停止条件；不自动换题/换根/整题重跑。

## E. 明确不证明

- 不证明模型语义决策正确；
- 不证明临床正确、官方得分或真实模型收益；
- 不证明 1.5M context/8192 output 足够；
- 不增加 reasoning/输出预算策略；该部分另立设计。
