# Provider timeout 对账行为契约

## 需求：只解除准入，不伪造结算

### 场景：provider 记录匹配

给定 failed attempt、chi_timeout 诊断、无 response evidence、pending round；provider 单请求记录必须 200/succeeded，session/body/time 与 dispatch 一致，output 不超过 max_tokens。通过时写 reconciliation 事件、清空 state.pending，request 仍 pending/unknown，seal/attempt 不变。

### 场景：不匹配

session/body/time/status/token 任一不一致，拒绝并保持原账字节；不能把 provider 记录当 response evidence。

### 场景：重复或篡改

重复对账、事件文件缺失/篡改、accounting/provider 副本 hash 不符、事务标记未清，历史校验拒绝。

## 需求：结果语义分明

### 场景：后续准入

成功返回 `execution_allowed=true`，仅表示该 pending 不再阻断新 attempt；`settled=false`，原请求仍 unknown，`usage_totals` 仍列 unsettled，billing 三项 incomplete。

### 场景：不重试

工具不发模型/HTTP 请求，不自动重发原 round，不换 candidate/账根，不生成 official reward。

## 需求：CLI 只读输入

### 场景：external 对账

`reconcile-provider` 仅接受 external state，要求 identity/accounting/target/request/provider SHA/reason；不读 Key、不联网、不发模型。

### 场景：真实副本验证

正式 state 不变；在副本上执行后 reopen 校验通过，seal 字节不变。
