# F0–F3 接口与行为冻结（待外部 Gemini 契约审查）

状态：**已实现离线候选，待外部 Gemini 审查**。本页冻结最小接口、权限边界、失败语义和检查项；实现与自测证据见 [阶段报告](../../../reviews/f0-f3-agent-capabilities-review.md)，实现偏差见第 10 节。接口变更须回到本页并重新审查。

## 1. 基线、候选与不变项

- 基线：`origin/main`（本轮现场为 `39c59efec6e4c6353fec5d561b363104b8b94899`，PR30 合并点）。接手者必须重新核对。
- 本候选只增加自有 OpenSpec/实现/测试；不修改官方 vendor、官方提示、评分器、MCP 目录、账目 schema 或既有历史证据。
- 不改变 `run_chi()` 的请求契约：官方 `SYSTEM_PROMPT`、instruction、完整工具批次、`validate_history()`、预算反馈、零重试和账目门槛保持原样。
- 新能力默认作为 `capabilities="f0-f3-v1"` 提供给开发入口；`capabilities=None` 保留旧行为，供基线与回归比较。真实运行仍需按现行身份规则 rebind 并取得新 B。

## 2. F0：任务家族与支持矩阵

### 2.1 输入来源（只读公开字段）

1. `data/task_index.md`（公开任务索引；不读取 `fixtures/expectations.json`、`solution`、`verifier`、`tests`）。
2. `vendor/chi-bench/src/chi_bench/mcp/catalog.py` 的 provider/payer 允许清单与 `go_chi_mcp.CM_NAMES`。
3. 公开 `instruction.md` / `tool_reference.md` 的角色与阶段描述。
4. 已有阶段报告中的“已实测范围”，只引用结论，不把历史通过扩大为新家族通过。

### 2.2 状态词表

| 状态 | 含义 |
| --- | --- |
| `supported_offline` | 工具面、角色入口和离线契约已具备，有当前候选的合成/单元证据 |
| `partial` | 入口存在，但缺少该家族的正常或失败链证据，或历史只在限定条件通过 |
| `needs_implementation` | 公开工具存在，但自有 Agent 缺少该分支所需的通用能力 |
| `official_dependency` | 需要官方模拟器/judge/受限资源才能继续 |
| `unsupported` | 当前没有入口或明确不处理 |

状态必须绑定证据来源；没有证据的格子写 `unverified`，不得按角色名整体标“已支持”。

### 2.3 必须产出的矩阵

按角色 × 任务家族列出：家族 ID、公开触发条件、必要能力（F1–F6 映射）、使用工具、外部依赖、可观察完成证据、正常分支、失败/缺证分支、当前状态与证据。首版矩阵见 [f0-task-family-matrix.md](f0-task-family-matrix.md)。

### 2.4 完成判据

- 至少覆盖 provider 新转诊/补证/提交后跟进/多案会话；payer 五个阶段、determination/letter、多阶段会话；CM 入队/病历/外呼/评估/照护计划/结案。
- 每个 `supported_offline` 家族至少一条正常与一条失败/缺证分支证据；`unsupported`/`official_dependency` 明确写出缺口。
- 矩阵不包含期望答案、rubric 阈值或按题分支策略。

## 3. F1：`chi-task-state-v1` 业务状态

### 3.1 位置与持久化

- 本次 run 的日志目录下新建 `task-state/`：
  - `task-state.json`：当前版本（原子替换）。
  - `versions/NNNNNN.json`：每次成功更新保留的旧版本，只增不改。
- 单文件上限 64 KiB；列表上限：observations 256、facts 64、plans 16、gaps 32、unknowns 16、next_candidates 8；单条文本 800 字符。
- 状态写入失败（权限、磁盘、原子替换、fsync）立即 `GoFailure("chi_state_persistence_failed")`，不降级为仅内存。
- 不写入 `chi-accounting.json`，不改 journal schema、claim、费用或历史字节；状态是 run 证据，不是账目。

### 3.2 结构

```json
{
  "schema": "chi-task-state-v1",
  "run": "<run id>",
  "role": "provider|payer|cm",
  "version": 1,
  "target": {"case_id": null, "patient_id": null},
  "observations": [
    {"seq": 1, "call_id": "...", "tool": "...", "kind": "mcp|local",
     "effect": "read|mutation|neutral", "scope": "case:<ID>|shared_public|unattributed|conflict",
     "arguments_sha256": "...", "result_sha256": "...", "event": "returned|returned_error", "round": 0}
  ],
  "facts": [{"text": "...", "source_call_id": "...", "source_seq": 1}],
  "plans": [{"text": "...", "created_version": 1}],
  "gaps": [{"text": "...", "status": "open|resolved", "source_call_id": null}],
  "unknowns": [{"id": "u1", "call_id": "...", "tool": "...", "scope": "...",
                "status": "open|resolved", "resolution_call_id": null, "note": null}],
  "latest_business_status": {"text": "...", "source_call_id": "...", "source_seq": 1},
  "next_candidates": [{"text": "..."}],
  "claim": null,
  "updated_at_utc_ms": 0
}
```

### 3.3 权威边界

- **程序登记**：只从本次 run 实际发生的工具调用登记 observation（call_id、工具、参数/结果 hash、事件、scope、请求轮次）。不登记模型自述、隐藏资料或未发生的调用。
- **模型提交**：facts、plans、gaps、target、latest_business_status、next_candidates。facts/status 必须引用已存在的 observation `call_id`；不引用原文，只引用本次 run 的观察身份。
- **模型不得**：修改 observations/unknowns/version/run/role；把推断写成无来源事实；把 open unknown 直接标成成功/失败；改变已绑定的 patient/case；用旧观察覆盖较新 business status。
- `source_seq` 由程序按登记顺序填写，模型不能提供。
- provider 的 `target.patient_id` 必须在患者绑定完成后提出，且此后不可更改；payer/CM 的 `case_id` 必须与已观察 scope 一致。

### 3.4 工具

`local-task-state`（空参数）返回当前状态摘要：version、target、facts、plans、gaps、open unknowns、latest status、next candidates、observation 计数与最近若干 observation 元数据（不含原始结果）。

`local-state-update` 参数：

```json
{
  "facts": [{"text": "...", "source_call_id": "..."}],
  "plans": ["..."],
  "gaps": [{"text": "...", "status": "open|resolved", "source_call_id": null}],
  "target": {"case_id": "...", "patient_id": "..."},
  "latest_business_status": {"text": "...", "source_call_id": "..."},
  "next_candidates": ["..."],
  "resolve_unknown": [{"unknown_id": "u1", "source_call_id": "...", "note": "..."}]
}
```

- 至少一个字段；未知字段、超限、无效类型 → `REFUSED: chi_state_update_invalid|chi_state_limit`。
- 引用未登记/call_id 不存在 → `REFUSED: chi_state_source_unobserved`。
- 旧状态来源 → `REFUSED: chi_state_stale`。
- case/patient 不符或试图改绑 → `REFUSED: chi_state_case_mismatch|chi_state_target_locked|chi_state_patient_unbound`。
- 成功 → 新版本、`versions/NNNNNN.json` 保留、返回 `{"status":"updated","version":N}`。
- 可纠正错误返回工具结果让模型修正，不直接终止 run；持久化失败才终止。

### 3.5 未知写效果

- 程序把“写类工具已 dispatch 但结果不可确认”（异常/中断/无结果）登记为 open unknown；读类工具的业务 `isError`/`returned_error` 不算 unknown。
- 模型只能提交 `resolve_unknown`，并引用**同一 run、同一目标、时间更晚的只读 observation**；程序校验 scope 与 seq。看不到旧状态不自动证明未执行；模型 note 标 `model_report`。
- open unknown 不自动清除，不因 claim 或最终回复消失。

### 3.6 写/读分类

- MCP 工具按公开名称的动词分类：`get/list/read/search/check/calculate/audit/validate` 为 read，其余为 mutation。
- 本地工具显式表：`local-fs-read|local-fs-list|local-fs-search|local-task-state|local-role-guidance|local-read-patient-observation` 为 read；`local-fs-write|local-fs-edit` 为 mutation；`local-confirm-patient|local-claim_done|local-state-update|evidence-*` 为 neutral。
- 未列出的新工具默认 mutation（保守），并由测试锁定行为；不静默按“读”放行。

## 4. F5 前移：claim 门禁（本变更只做最小部分）

`local-claim_done` 在 capabilities 启用时：

1. 存在 open unknown → `REFUSED: completion_blocked_unknown:<id>`。
2. 最近一次 mutation observation 晚于 `latest_business_status.source_seq` → `REFUSED: completion_readback_required:<call_id>`；模型须在剩余预算内做合法只读回读并更新状态。
3. 否则记录 claim（state.claim 含 version、target、已核实来源），再调用 `journal.record_claim()`。

语义：claim 仍是模型声明；门禁只拦截“已知未知”和“写后未回读”，不声称业务成功。没有 mutation 时保持原 claim 行为。完整 F5 的证据分级与最终输出一致性在后续包实现。

## 5. F2：`chi-role-guidance-v1`

### 5.1 形态

- 独立模块 `go_chi_guidance.py`，版本常量与内容 hash 进入 run journal 的 launch 元数据/日志（不改变官方提示）。
- 通过 `local-role-guidance` 工具返回，不修改 `official.SYSTEM_PROMPT`，不额外注入系统消息；避免破坏 guard 的系统提示/历史契约。
- 工具结果包含：role、version、stages（goal/preconditions/actions/readback/stop_if）、invariants、当前 state 的 next_candidates。

### 5.2 阶段（内容冻结，措辞可实现微调）

| 角色 | 阶段 |
| --- | --- |
| provider | 识别患者与目标 → 核对公开病例/既往处理 → 准备申请材料 → 提交或补证/暂不提交 → 回读案件状态 → 结束或如实未完成 |
| payer | 入队/文件完整性 → 核对适用规则与材料 → 评估条件 → 选择处理分支（批准/部分/拒绝/补件/转 MD/P2P） → 生成并核对函件 → finalize 后回读 |
| cm | 入队/开案 → 病历核对 → 外呼或消息（尊重 STOP） → 评估分段保存 → 照护计划草拟/保存/finalize → 结案或如实未完成 |

### 5.3 不变量

- 不要求所有 payer 必经 MD；不预设批准/拒绝/挂起为正确结局；存在材料不等于条件必需。
- 不要求所有 provider 必须提交；缺证、冲突、权限/身份不明时可以停止或补证。
- 不要求 CM 固定话术或固定轮数；患者 STOP、预算将尽、工具失败都是合法停止条件。
- 指导只给分支和检查点，不给具体任务答案、不按 task ID 分支。

## 6. F3：`local-fs-search`

### 6.1 范围

允许搜索：

1. `handbook_root` 子树（沿用现有隐藏目录/文件名过滤）。
2. 当前角色可读的 workspace 目录 `<case>/<role>`（不含其他 case、`shared` 以外路径）。
3. 固定 instruction / tool_references 文件（逐个文件）。

拒绝：workspace 根、其他 case、隐藏/verifier/judge/fixtures、符号链接、越界路径、外网 URL。

### 6.2 参数与限制

```json
{"path": "<allowlisted dir or fixed file>", "query": "1..200 chars",
 "max_results": 1, "case_sensitive": false}
```

- 单次最多 400 个文件、单文件 2 MiB、累计 16 MiB、结果 20 条、片段 240 字符；超限返回 `truncated: true` 与 `omitted`，不静默截断。
- 每个结果含：相对/可回读路径、1 基行号、字节偏移、文件 sha256、单行片段（去除换行，保留否定词与例外所在行）。
- 不持久化索引；查询与结果只在本 run 内存/工具结果中；不上传派生索引。
- 结果登记为 read observation；原文回读仍走 `local-fs-read`，并用 offset/limit 复核上下文。

### 6.3 失败语义

- 路径越界/隐藏：`REFUSED: search_path_outside_allowlist`。
- 查询空/超长/控制字符：`REFUSED: search_query_invalid`。
- 目录不可读/文件损坏：`ERROR: search_unreadable`（不编造依据）。
- 无匹配：`{"results":[],"no_matches":true}`，不返回“可能相关”的猜测。

## 7. 接线点（实现时按此检查）

| 位置 | 变更 | 兼容要求 |
| --- | --- | --- |
| `go_chi_state.py`（新） | `TaskState`、schema、校验、原子持久化 | 纯新增 |
| `go_chi_guidance.py`（新） | 版本化阶段指导 | 纯新增 |
| `go_chi_search.py`（新） | 有界搜索 | 纯新增 |
| `go_chi_tools.py` | 追加状态/指导/搜索工具；claim 门禁 | 新参数可选；`capabilities=None` 时工具集与 claim 不变 |
| `go_chi_runtime.py` | 创建 state、传入 bridge/tools、run_log 汇总 | 不改 system/instruction/history/预算 |
| `go_chi_mcp.py` | 可选 `state`，成功后登记 observation | 构造签名向后兼容；不吞工具异常 |
| `role_runner.py` / `go_chi_entry.py` | 显式传 capabilities 与 state 目录 | 旧配置默认可关闭 |

## 8. 失败与反例检查清单

- F1：错 case、未观察来源、伪造/未来 call_id、旧状态覆盖新受理、模型把推断填成事实、open unknown 被摘要改成成功/失败、超限、持久化失败、旧版本丢失。
- F2：payer 未走 MD 被误判失败、provider 缺证仍被逼提交、CM 患者 STOP 后继续外呼、冲突规则被压成单一结论。
- F3：相近关键词的无关政策、错角色/错版本、否定/例外在行尾、同名文件、空页/提取失败、超大结果、隐藏目录、跨 case。
- 兼容：`capabilities=None` 的旧工具集/claim/请求历史不变；新能力不改变账目、费用、重试与 B 收据语义。

## 9. 待外部 Gemini 审查的问题

1. 把 F1 状态放在 run 日志目录、而不是 `chi-accounting.json`，是否满足“每 run 可追溯 + 不重写账目”的要求？是否还需要独立 hash/seal？
2. claim 门禁要求“mutation 后必须回读”，是否会误伤合法的 payer/CM 结束路径（例如 finalize 后没有可读状态）？是否应只对 provider 强制？
3. 用工具名动词推断 read/mutation 是否足够保守？是否需要显式 catalog 映射并拒绝未知工具？
4. 通过工具而不是系统提示提供 F2 指导，是否足以让模型实际使用？是否需要把“先读指导/状态”写进 instruction 而不破坏官方提示契约？
5. F3 是否应包含 `<case>/<role>` workspace？只搜 handbook 是否会漏掉 payer 的公开 PDF？
6. `capabilities=None` 的兼容开关是否会被误用为绕过新身份/B 要求？是否需要禁止在真实入口关闭？

## 10. 实现记录（2026-11-01）

离线实现候选为 `a6aac1c80401ccbb815763b13bc46a9fbbf6d57f`，基于 PR31 合并后的 `443257c`。全量 Docker 套件 414 tests，2 个既有环境性错误（缺 `anthropic`），8 skipped；新增 32 个测试。

与冻结契约的实现对应和补充：

1. **状态位置**：`logs/task-state/task-state.json` + `versions/NNNNNN.json`；不写 `chi-accounting.json`，不改 journal schema。当前没有独立 seal；版本快照与 journal/hash 共同提供可追溯性。
2. **unknown 记录**：除契约字段外增加内部 `seq`，用于校验“更晚的只读观察”；summary 会暴露该字段，不暴露原始工具结果。
3. **事实来源更严格**：facts、gaps 来源、latest status、unknown resolve 都要求 observation `event=returned`；`returned_error/refused/failed` 不能作为已观察事实的依据。
4. **claim 同批保护**：若同一批中 claim 之后仍有待执行工具（例如先 claim 再写），claim 返回 `completion_batch_pending:<id>`，避免“先声明完成再执行写”。
5. **工具顺序**：F0–F3 工具插入在既有 payer evidence shadow 工具之前，保持 shadow 工具尾部和既有测试契约不变。
6. **入口**：`run_chi()` 默认 `capabilities="f0-f3-v1"`，`go_chi_entry.py` 显式传入；`capabilities=None` 仅用于离线基线/对照，不提供给外部 CLI 作为真实运行绕过开关。
7. **检索**：`local-fs-search` 接受一个已授权目录或固定文件；PDF 通过既有 `read_allowed_file` 提取文本，文本文件按 UTF-8 读取。结果不持久化索引。
8. **指导**：以工具返回，不修改官方 `SYSTEM_PROMPT`；版本/hash 写入 `run_log.txt`，不新增系统消息。

第 9 节问题的当前处理（仍待外部审查）：

| 问题 | 当前实现 | 仍需验证 |
| --- | --- | --- |
| 状态位置/账目 | 日志目录，版本快照，不写账 | 是否需要独立 seal/导出校验 |
| 写后回读 | 对所有角色启用 | 真实 payer/CM 结束路径的误伤率 |
| read/mutation 分类 | 动词表；未知工具按 mutation | 官方工具新增/改名时的保守性 |
| F2 工具化 | 不改系统提示 | 真实模型是否主动读取并使用 |
| F3 范围 | 单路径，可含 workspace/PDF | 真实 handbook/PDF 命中质量与越权边界 |
| `capabilities=None` | 仅离线基线；入口固定启用 | 防止真实运行误用 |

未验证项与下一步见阶段报告；真实模型、真实任务、官方判分、F4–F7、Z1–Z8 均未开始。
