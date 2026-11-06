# chi-requirements-v1 验收场景

本文件冻结离线验收场景；实现必须逐项覆盖。真实模型/业务收益/官方分数不在本契约内。

## A. 来源和结构

### A1 合法原文引文
- Given 开启 requirements，instruction 为公开原文；
- When 模型提交 1..8 项，quote 是 instruction 的逐字子串且归一化长度 16..400；
- Then 更新成功，`requirements_declared=true`，新项为 `open`。

### A2 伪造/重述/仅归一化匹配
- Given 开启 requirements；
- When quote 不在 instruction 原文中，或只有 NFKC/空白/case-fold 后相同但原文不是子串；
- Then 返回 `chi_state_requirement_quote_invalid`，整份更新不改变版本/落盘内容。

### A3 长度与数量边界
- Given 开启 requirements；
- When quote 归一化长度 15 或 401、原始长度超过 MAX_TEXT、提交 0/8/9 项；
- Then 0/8 合法，9 项或超长返回对应拒绝；已有项不截断、不合并。

### A4 结构非法
- Given 开启 requirements；
- When id 重复/格式错误、未知字段、bool 冒充计数、status/waiver_reason 非法枚举、容器类型错误；
- Then 受控 `chi_state_requirement_invalid`，不泄漏 TypeError/KeyError/任意异常文本。

### A5 instruction 绑定
- Given 开启 requirements 但 instruction 缺失/空，或 state 的 instruction hash 被模型提交/篡改；
- Then 配置/更新被拒绝；模型不能修改 declared/hash/schema。

## B. 转换与事务

### B1 追加与 open
- Given 已有 N 项；
- When 在末尾追加新 id，首次状态 open；
- Then 成功；新 id 不能插入中间、不能跳过/重排已有项。

### B2 终态不可改写/回退
- Given 已有 done/waived 项；
- When 删除、重排、改 quote、改 evidence/waiver/note，或 done/waived→open；
- Then `chi_state_requirement_transition_invalid`，整份更新不改变。

### B3 缺省与显式空
- Given 已有清单；
- When 更新不含 requirements 字段；
- Then 清单/declared 不变。
- When 显式提交 `[]`；
- Then 保存空清单并 declared=true；claim 返回 `completion_requirements_empty`。

### B4 原子事务
- Given 一个更新同时含合法 facts 和非法 requirements 项；
- When 提交；
- Then facts、requirements、declared、version 全部不改变；不先保存前半段。
- Given 状态体量超过 MAX_STATE_BYTES；
- Then 明确拒绝，原版本/落盘内容不变。

## C. 来源范围

### C1 done 来源
- Given open 项；
- When 引用未登记/其他 run/歧义 call_id、returned_error/refused/failed、neutral 本地工具；
- Then `chi_state_requirement_evidence_invalid`，项保持 open。

### C2 waived 来源
- Given open 项；
- When waiver_reason=`not_applicable_public_rule`，引用只读、returned、scope 合法观察并给出 note；
- Then 成功；mutation 观察不能作豁免证据。
- When waiver_reason=`insufficient_evidence`；
- Then 拒绝；项保持 open，可用 gaps 记录缺口。

### C3 case 绑定
- Given 目标 case 未绑定；
- When done/waived 引用 unattributed/conflict/case 观察；
- Then 拒绝；只有 shared_public 可关闭。
- Given 后续锁定 case；
- When 已有 done/waived 来源不属于该 case/shared_public；
- Then 更新被拒绝，已有项不复核通过。

### C4 claim/check/report 一致
- Given done/waived 引用的观察在 claim/check/report 时仍存在且 event/effect/scope 合法；
- Then 三处使用同一 `_completion` 判定；任一来源失效则拒绝/报告 blocked。

## D. 门禁及报告

### D1 未声明/空/open
- Given 开启 requirements；
- When declared=false；Then `completion_requirements_undeclared`。
- When declared=true 且 count=0；Then `completion_requirements_empty`。
- When 有 open 项；Then `completion_requirements_open:<第一个 id>`。

### D2 全闭合后继续原检查
- Given 全部 done/waived；
- When 存在未知写、失败文件、陈旧回读、claim 后写违规；
- Then 仍按原优先级 blocked，不能因清单闭合而批准。

### D3 不 claim 直接 final
- Given 模型不调用 claim 直接结束；
- Then 保存完整 completion/requirements；未声明/空/open 不写成 requirements 通过；不自动增加请求。

### D4 completion-v4 校验
- Given v4 completion；
- Then policy/instruction_sha256/declared/status/count/done/waived/open/open_ids/verification/semantic_completion_verified 严格校验；count=done+waived+open；bool 计数拒绝。
- Given 畸形 v4 日志；
- Then reader/inventory 走既有明确 fallback，不掩盖首个运行错误。

## E. 接线与回归

### E1 真实到达
- Given entry 参数 `--requirements chi-requirements-v1`；
- When 运行合成 MockTransport；
- Then launch 记录 policy，runtime 构造 v4 state，run_log 保存 v4 completion；不只断言配置对象。

### E2 早拒
- Given 未知版本，或 requirements 与 input-summary/output-recovery/Y shadow 组合；
- When 在凭据读取/模型派发前；
- Then 固定安全错误码拒绝；argv 分离、等号及 parser 缩写形式都覆盖。

### E3 off 回归
- Given 未开启 requirements；
- Then state/completion 仍 v3；工具 schema/description、guidance 内容/digest 不变；不增加 claim 检查；同进程 v3/v4 实例互不污染。

### E4 三角色与既有保护
- Given provider/payer/CM 各一条合成正例；
- Then 现有 facts/unknown/file 修复/readback/claim 保护回归通过；负例覆盖必要失败。

## F. 明确不证明

- 不证明抽取覆盖全部 instruction 要求；
- 不证明观察在语义上完成业务；
- 不证明临床正确、官方得分或真实模型收益；
- 不增加专门抽取请求，不承诺轮次/token/耗时不增加。
