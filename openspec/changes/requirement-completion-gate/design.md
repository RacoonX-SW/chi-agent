# chi-requirements-v1：公开要求清单、来源校验与 claim 门禁

建立：2026-11-06（Asia/Shanghai）。状态：**契约冻结候选，按本页实现；默认关闭，不进入当前九题候选。** 本页只定义离线实现与验收，不授权真实模型、B/C、摘要、续写、患者、world、Trial、judge 或发布。

## 1. 目标与非目标

目标：模型可以显式记录公开 instruction 中的要求，为 `done`/`waived` 附上本 run 已登记的真实观察来源；程序阻止未声明、空清单和仍有 open 项时接受 claim。

程序能验证：引文是否为权威 instruction 的逐字子串；来源是否为本次 run 的合法 observation；状态转换是否合法；清单项是否闭合。

程序不能证明：抽取覆盖了 instruction 的所有要求；某条观察在语义上完成了某项业务；`done`/`waived` 是临床正确或官方得分。`done` 仅表示“模型报告完成且引用了合法观察”；`waived` 仅表示“模型报告公开规则允许不做，且提供了观察及解释”。

## 2. 版本与默认关闭

- 策略版本：`chi-requirements-v1`。
- 开启时：task state `chi-task-state-v4`；completion `chi-completion-v4`；launch 记录 `requirements: "chi-requirements-v1"`。
- 关闭时：state/completion 仍走 v3；不新增 requirements 字段；local 工具 schema/description、guidance 内容及既有 digest 保持旧路径；不增加 claim 检查；不因提交中存在新代码而静默启用。
- 按实例选择 schema；不通过修改全局变量切换 v3/v4；同进程 v3/v4 实例不能互相污染。
- 历史 v1/v2/v3 证据保持原义，不迁移、不重写、不重新判定。
- 不把策略塞入 `capabilities`；`f0-f3-v1` 保持现有能力信封含义。
- 代码改动会改变 bundle 身份，即使默认关闭；不得声称默认关闭等于包内 hash 不变。

## 3. 权威 instruction 绑定

`TaskState` 新增可选构造参数 `requirements` 和 `instruction`。只有 `requirements == "chi-requirements-v1"` 时，才要求 `instruction` 为非空字符串；否则 instruction 不参与。

instruction 必须由 runtime 传入本 run 已校验的公开原文，不能由模型通过 `local-state-update` 上传或替换。程序计算原始 UTF-8 字节的 SHA-256，写入 `requirements_instruction_sha256`。

v4 state 新增：

- `requirements`: 数组，初始 `[]`；
- `requirements_declared`: 布尔，初始 `false`；
- `requirements_instruction_sha256`: 程序计算的 instruction SHA。

模型不能提交或修改 `requirements_declared`、instruction、instruction hash、schema 或程序生成的审计字段。不把整份 instruction 复制进 state；`MAX_STATE_BYTES=65536`、`MAX_TEXT=800` 不变。

## 4. requirements 数据契约

每项固定结构：

```json
{
  "id": "r1",
  "quote": "<公开 instruction 原文片段>",
  "status": "open",
  "evidence_call_id": null,
  "waiver_reason": null,
  "note": null
}
```

规则：

1. 最多 8 项；`id` 匹配 `^r[0-9]{1,2}$`，同 run 唯一。超限明确拒绝，不截断、丢弃或合并已有项。
2. `quote` 原始非空且原始长度不超过 `MAX_TEXT`；NFKC + 折叠空白 + case-fold 后长度为 16..400；原始 `quote` 必须是权威 instruction 的精确子串。归一化只用于长度/辅助查重，不能替代逐字来源校验。quote 不是模型重述，也不得从工具/隐藏答案推测。
3. `local-state-update.requirements` 采用**完整快照**语义：
   - 缺少该字段：清单及 declared 不变；
   - 明确提交：验证整份快照；
   - 新 id 只能追加到末尾，首次状态必须 `open`；
   - 已有 id 不得删除、重排、改 quote；
   - 已有 `done`/`waived` 项整个条目不可修改；
   - 重发完全相同条目允许，沿现有版本更新语义处理。
4. 首次合法显式提交 requirements 后，程序将 `requirements_declared` 设为 `true`；普通 facts/plans 更新不自动声明。显式 `[]` 可保存为“声明了空清单”，但不能放行 claim。
5. `open` 项：`evidence_call_id`、`waiver_reason`、`note` 均为 `null`。
6. `open → done`：`evidence_call_id` 必须引用本 run 唯一、已登记的 `returned` 观察；不接受 `returned_error`/`refused`/`failed`；不能只引用 neutral 本地工具；来源 scope 必须通过第 5 节；`waiver_reason` 必须为 `null`；`note` 必须非空有界，说明该观察如何支持完成声明。程序只校验来源及文本结构，不将 note 解释为事实证明。
7. `open → waived`：`waiver_reason` 只允许 `not_applicable_public_rule`；`evidence_call_id` 必须引用本 run 唯一、只读、`returned` 观察；来源 scope 必须通过第 5 节；`note` 非空有界，解释适用公开规则及豁免原因。仅“读过一次资料”不构成程序已验证规则适用。
8. 不接受 `insufficient_evidence` 作为 `waiver_reason`。证据不足时该项保持 `open`，用现有 `gaps` 记录缺口；若公开规则允许挂起/拒绝，应完成并回读该合法分支。
9. `done`/`waived` 不回退。后续动作使业务状态陈旧时，现有 readback/unknown/file 保护继续起作用，不因清单闭合而放宽。

## 5. 来源与 case 绑定

- 目标 case 未绑定时，只允许 `shared_public` 观察用于关闭清单项；`unattributed`/`conflict` 均拒绝。
- case 绑定后，只允许该 case 或 `shared_public`。
- 后续锁定 case 时，重新验证已有 `done`/`waived` 项的来源，与现有 facts/gaps/status 来源复核一起执行。
- claim 与 completion 报告时，再核对关闭项引用的观察仍存在、event/effect/scope 合法。
- 不接受其他 run 的观察、模型伪造的观察对象或歧义 `call_id`。
- 不放宽现有 facts、unknown、患者绑定或业务回读保护。
- 这些规则只提供来源可信度，不提供自然语言要求与工具结果的语义等价证明；该局限写入设计、报告和 completion 说明。

## 6. 更新事务与错误边界

模型提交错误使用 `StateRefusal`，可恢复：

| 码 | 触发 |
| --- | --- |
| `chi_state_requirement_invalid` | 容器/字段类型/未知字段/状态枚举/计数/id 格式/数量/quote 字段结构等一般非法 |
| `chi_state_requirement_quote_invalid` | quote 空、原始超长、归一化长度越界、非 instruction 精确子串 |
| `chi_state_requirement_transition_invalid` | 删除/重排/改 quote、新项非 open、终态改写/回退、waiver_reason 非法、done/waived 字段组合非法 |
| `chi_state_requirement_evidence_invalid` | 来源未登记/重复/歧义、event 非 returned、done 引用 neutral、waived 非只读、scope 不符、其他 run 来源 |

优先级：先校验整体容器/数量/字段形状（invalid），再校验 quote（quote_invalid），再校验已有项顺序/终态（transition_invalid），最后校验来源（evidence_invalid）。同一更新中任何条目无效，整个更新拒绝；不先保存 facts/部分清单/declared 再报告后半段失败。验证/体量超限拒绝不改变已提交版本和持久化内容。

仅模型输入校验错误可恢复；instruction 来源/配置无效、持久化或审计损坏继续沿现有 fatal 语义，不吞错。不承诺 IO 失败能撤回已写出的历史字节。

## 7. claim 门禁与结束语义

`local-claim_done`、`local-completion-check` 和 `completion_report` 共用同一个 `_completion` 判定，不复制实现。保留现有 `claim_violation`、open unknown、未解决文件写失败等检查的优先级；requirements 检查置于业务 readback 判断之前：

- 未声明：`completion_requirements_undeclared`
- 已声明但空清单：`completion_requirements_empty`
- 有 open 项：`completion_requirements_open:<id>`，多项按清单顺序返回第一个
- 全部 done/waived：仅表示清单机械闭合，然后继续所有原有 readback 检查，不能直接批准 claim。

首版不修改 `optional_final_text`：模型仍可不调用 claim 直接结束；此时也保存完整 completion 与 requirements 状态，未声明/空清单/open 不能被日志写成 requirements 已通过。不自动再启动模型循环、自动续写、自动补写或伪造 claim。

## 8. completion-v4

v4 保留既有 completion 字段，并增加：

```json
{
  "policy": "chi-requirements-v1",
  "instruction_sha256": "<sha256>",
  "declared": false,
  "status": "undeclared",
  "count": 0,
  "done": 0,
  "waived": 0,
  "open": 0,
  "open_ids": [],
  "verification": "provenance_only",
  "semantic_completion_verified": false
}
```

status 闭集：`undeclared` / `empty_unverified` / `open` / `closed_reported` / `closed_with_waivers`。

- 数量是“记录的清单项数”，不代表 instruction 真实要求总数。
- `count == done + waived + open`；`open_ids` 与 open 数量、实际条目一致。
- 所有计数必须是非负整数，拒绝 bool。
- 计数、状态、id、hash、嵌套键严格校验。
- requirements 全部闭合也不能升级原有 `business_effect` 或 clinical/official 验证结论。
- off 时不新增该对象，旧 completion 逐字段保持原路径。

## 9. 接线与兼容范围

1. **state**：按实例 v3/v4、instruction 绑定、更新校验、共享门禁、summary 与 completion 视图。
2. **tools**：仅开启时增加 requirements 工具 schema 及描述；现有追加/更新语义不变。
3. **guidance**：仅开启时添加角色中立的公开要求自检约束；不写 task id、期望状态、特定 letter 类型或固定业务阶段。off 返回原有内容和原有 digest；on 版本/digest 可区分实际新增内容。
4. **entry/runtime**：参数→launch→TaskState 真实接线；未知版本/非法组合在凭据读取和模型派发前拒绝；缺 instruction 不能绕过校验。
5. **journal**：核对策略版本、launch 留证、审计/历史读取兼容；仅在必要处扩展，不改旧账、请求计数或停止语义。
6. **entry 日志 reader 与包外 readiness inventory**：精确支持 completion-v4 及新 reason；畸形 v4 走既有明确 fallback；不掩盖首个运行错误或接受任意嵌套字段。
7. **开发 operator/runner**：完成配置透传、精确版本校验及缺省不传；不增加未登记环境变量启用后门。正式 Harbor 路径继续默认 off。

首版与 input-summary、output-recovery、Y shadow 互斥。组合必须在真实可观察接缝、任何模型派发前拒绝；拒绝原因固定、安全、可测试。argv 检测覆盖分离、等号及 parser 实际允许的缩写形式。首版不要求摘要模块接受 v4 protected snapshot，但必须证明不支持的组合会早拒。

## 10. 验收与边界

测试至少覆盖 A 来源和结构、B 转换与事务、C 来源范围、D 门禁及报告、E 接线与回归。测试不要求“任意合法引用能证明该业务完成”；应有用例说明它只能证明来源与模型声明。

明确：

- 不增加专门的抽取模型请求；不能承诺 main 轮次、token、耗时不增加。
- 默认关闭且不进入当前九题候选；使用隔离分支、导出和测试资源，不覆盖当前运行包。
- 新包身份意味着旧 B 收据不适用。
- 不执行已见题回归或任何真实调用。
- 真实收益、误拦率、额外 token/轮次及静态 guidance 对照，等九题证据固定后再另行设计并获批。
