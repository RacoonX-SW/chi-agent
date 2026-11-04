# 最终验证前 A–D 有界离线加固：实现与证据

日期：2026-11-05（Asia/Shanghai）。结论：A–D 已完成有界离线实现、Docker/Python 3.12 禁网自测、隔离包身份/预检和只读余量盘点；未进行任何真实模型、摘要、续写、B/C、患者、world、Trial、judge 或发布调用。official_reward 全部为 null。本文是唯一详细证据；短状态只写 [REVIEW_STATE](REVIEW_STATE.md)。

## 1. 基线、分支与提交

- 开工前重新 `git fetch origin`，实际 `origin/main=6533776c4155eb2ab487d8779284c8b66f722c34`，与交接快照一致；PR57/PR58 已合并。
- 本 checkout 开工时无未提交改动；从最新 `origin/main` 新建 `deepseek/score-readiness-hardening`。其他 worktree（`c2-input-output-recovery`、`context-recovery-plan`）保留且未写入；本 checkout 是本轮唯一实现写入者。
- 每卡独立提交，未 push、未开 PR、未 merge/auto-merge：

| 卡 | 提交 | 主题 |
| --- | --- | --- |
| A | `916ef48` | 区分业务状态回读、政策/文件证据；共同完成判断；状态/报告版本化 |
| B | `fe50ffc` | 本地工具契约矩阵、MCP 业务错误闭合、可选 index/整批零派发回归；不新增恢复策略 |
| C | `ea2e987` | 正式 harness/delivery 凭据集合一致；包内补 delivery 成员；三 role 装配/缺供给测试 |
| D | `0e9d079` | entry 失败保留有效 runtime 诊断；plans/gaps 指导；只读余量盘点 |

代码候选（包绑定）为 `0e9d079ac738a1950af8305975face97bbd9c90a`；本文档提交只追加报告/状态/勾选，不改变包内脚本。最终 HEAD 见交付回报。

## 2. 环境、命令与实际结果

所有 Python/测试在 Docker 内；无宿主依赖安装、无网络、无 Key/.env、无真实服务。

| 项 | 实际身份/命令 | 结果 |
| --- | --- | --- |
| dev 镜像 | `chi-agent-py312-review:dev` = `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，`/opt/venv/bin/python` 3.12 | 使用 |
| controller 镜像 | `chi-agent-py312-review:controller` = `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，`/opt/a-venv/bin/python` 3.12 | 使用 |
| Harbor overlay | 既有 `runs/harbor-launch-coverage-root/independent/overlay`（harbor 0.20.0 等）只读挂载 | 仅 C 真实组件测试 |
| 依赖卷 | `chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1` 只读 | 无安装/升级 |
| 挂载/网络 | 源码 `:ro`、`--network none --read-only --tmpfs /tmp`；测试 `runs` 使用隔离可写目录 | 未写真实 state |

主要命令与退出码：

```sh
# 全量适用 pytest（dev 镜像；Harbor overlay 只读；隔离可写 runs）
/opt/venv/bin/python -m pytest tests \
  --ignore=tests/test_dev_patient_adapter.py \
  --ignore=tests/test_dev_patient_network.py -q -rs
# exit 0：939 passed, 8 skipped, 322 subtests passed (27.82s)

# controller 侧
/opt/a-venv/bin/python -m unittest \
  tests.test_role_operator_config tests.test_role_validation_wiring -v
# exit 0：Ran 12 tests, OK

# 既有 anthropic 环境缺项（显式单列，未计入全量）
/opt/venv/bin/python -m pytest tests/test_dev_patient_adapter.py \
  tests/test_dev_patient_network.py -q
# exit 2：2 collection errors，均 ModuleNotFoundError: No module named 'anthropic'
```

基线对照为 899 passed、13 skipped、293 subtests、controller 12 tests OK；本轮新增测试后为 939/8/322。8 个 skip 全部是“依赖只在 controller 镜像”的 operator 测试，已在 controller 镜像通过；不是失败。Harbor 测试在 overlay 下实际执行，不再 skip。日志：`runs/score-readiness-hardening-20261105/pytest.log`、`controller.log`、`anthropic-gap.log`（本地忽略目录）。

## 3. A：完成来源、业务/文件读写与退出诊断

### 3.1 修复前反例（独立构造，baseline `6533776`）

脚本：`runs/score-readiness-hardening-20261105/counterexamples/a_before.py`；baseline 输出：

```json
{"after_business_readback": [true, null],
 "after_later_file_write": [false, "completion_readback_required:f1"],
 "file_read_as_status": "ACCEPTED",
 "policy_read_as_status": "ACCEPTED"}
```

确认三个当前缺陷：业务回读后保存交付文件被要求再次业务回读；workspace 文件读可冒充 `latest_business_status`；handbook/policy 读也可冒充。

### 3.2 实现

- `go_chi_state.py` 升级 `chi-task-state-v2` / `chi-completion-v2`。观察新增程序分类 `source_kind`：`business_status`、`business_mutation`、`business_evidence`、`policy_evidence`、`file_evidence`、`file_deliverable`、`patient_evidence`、`neutral`、`unknown_mutation`。
- 业务状态来源由程序固定的公开 canonical 清单决定，模型不能提名：
  - provider：`cases.get_case`、`auth.check_status`；
  - payer：`payer_intake_hub.get_intake_case`、`triage.get`、`review.get_nurse_review_data`、`review.get_md_review_data`、`determination.get_summary`、`p2p.list`、`payer_letter_center.list`；
  - cm：`cm_chart.get_chart_data`。
  独立测试同时核对清单与固定公开 catalog 的 role allowlist。
- `latest_business_status` 只接受 returned、read、目标 case 匹配的 `business_status`；文件/政策/患者/一般业务证据、错误 case、陈旧、`returned_error`、`refused` 均拒绝，错误码有限且可定位（`chi_state_source_not_business`、`chi_state_source_not_read`、`chi_state_case_mismatch`、`chi_state_stale` 等）。
- 完成判断改为一个 `_completion()`，`record_claim()` 与 `completion_report()` 共用：
  - 最后业务写之后必须有更晚的业务状态回读；
  - 其后成功保存交付文件不再要求额外业务回读；
  - 文件写 `returned_error` 仍阻止完成；文件写 `failed` 仍登记 open unknown 并阻止；`refused` 未派发，不当作失败交付；
  - open unknown、claim violation、重复写/claim 后写保护保持。
- 报告展示 `latest_business_status` 的 call_id/tool/kind/scope/event/seq、`last_business_mutation`、`last_file_mutation`、`required_readback`、`claim_policy=optional_final_text` 和 `final_text_without_claim_not_blocked` 限制；没有新增最终硬门禁、自动补发或 Runner 重启。
- 工具描述与 guidance（`chi-role-guidance-v2`，D 再升 v3）说明业务状态证据与文件交付证据的区别；`local-state-update`/`local-completion-check`/`local-claim_done` 描述同步。
- `go_chi_summary.protected_snapshot` 接受 v1/v2 task-state；旧 v1 只读解释，不迁移/重写历史。v1 报告的旧含义不被新规则追溯否定。

### 3.3 修复后反例

```json
{"after_business_readback": [true, null],
 "after_later_file_write": [true, null],
 "file_read_as_status": "chi_state_source_not_business",
 "policy_read_as_status": "chi_state_source_not_business"}
```

### 3.4 验收覆盖

- 同 case 业务写→业务读→状态→claim；随后文件写仍可 claim，报告 `mechanical_pass`。
- 文件/政策/患者/chart 读不能设状态；`returned_error`/`refused` 不能设状态；错误 case 拒绝；拒绝不部分修改 state。
- 文件写 `returned_error` 阻止完成；`refused` 不算失败交付；`failed` 登记 unknown。
- 无 mutation、仅文件任务不被判失败；claim 与报告 reason 一致；claim violation 阻止 claim 并报告 `violation`。
- unknown 解析要求匹配证据类型：业务 unknown 只能由业务状态读解析，文件 unknown 只能由文件读解析。
- 实际 SDK+MockTransport 正常/错误来源/结束路径见 B 的 runtime 测试。

剩余限制：CM 公开工具面没有 care-plan 读取工具，`cm_chart.get_chart_data` 只是 case-scoped 业务资源读；报告是机械/来源检查，不能证明 plan finalize 的临床正确性。`final_text` 未 claim 仍不会被程序阻止，已在报告字段中明示。

## 4. B：工具契约一致性与有界错误分类

### 4.1 本地工具对照（实际接缝测试）

新增 `tests/test_score_readiness_tool_contracts.py`，逐工具覆盖合法与边界非法输入：

| 工具 | 描述承诺 | 实际接受/拒绝（实测） |
| --- | --- | --- |
| `local-fs-read` | 绝对路径的 instruction/handbook/fixed reference/role workspace 文件；offset/limit ≥1；PDF 有界 | workspace/handbook 读取成功；`/etc/passwd`、相对路径 `ERROR`；offset=0 schema 拒绝 |
| `local-fs-list` | role workspace/shared case/handbook 目录 | 目录成功；文件路径/`/` 返回 `ERROR` |
| `local-fs-write` | `<workspace>/<case>/<role>/<file>` 或 `<case>/shared/<file>`；创建缺失父目录 | role/shared 写入成功；其他 role/相对路径 `REFUSED`；缺 content schema 拒绝 |
| `local-fs-edit` | 同 write 路径；old_string 必须存在；replace_all 控制全部/首个 | 首替换与全部替换成功；缺失 old_string `ERROR`；空 old_string schema 拒绝 |
| `local-fs-search` | handbook/public 目录、fixed reference、目标 case role workspace；max_results 1–20 | 目标 case 命中；其他 case `REFUSED`；handbook 命中；max_results=0 schema 拒绝 |
| `local-claim_done` | 无参数；缺回读/失败文件/open unknown/pending 批次可拒绝 | 缺回读 `REFUSED: completion_readback_required:*`；open unknown `REFUSED: completion_blocked_unknown:*`；满足后 recorded |
| `local-task-state` | 无参数、有界摘要、不含原始结果 | v2 摘要成功，observation 不含 `result` |
| `local-state-update` | facts/status 必须引用已观察 call；status 必须是业务状态读 | 文件/政策/患者/chart 来源拒绝；错误 case/陈旧/未知键拒绝（state 测试） |
| `local-completion-check` | 无参数；v2 机械报告，不 claim | v2 报告成功，含 `claim_policy` |
| `local-role-guidance` | 无参数；v3 指导，不含 task ID/答案 | 非空参数 schema 拒绝；v3 返回成功 |
| `local-read-patient-observation` | patient_id + offset ≥0；仅已返回 chart | 缺 offset/负 offset schema 拒绝；合法路径由既有 patient binding 测试覆盖 |
| `local-confirm-patient` | patient_id + 非空 instruction/chart quotes；必须单独调用 | 空 quote schema 拒绝；单独调用/证据校验由既有 patient binding 测试覆盖 |
| `local-evidence-*` | payer shadow-only；不批准/不阻断 | 既有 `test_payer_evidence_shadow.py` 覆盖；本轮未改生产逻辑 |

### 4.2 MCP/协议回归

- 公开 role allowlist/name 映射、schema、name collision、role mismatch 保持；未读隐藏实现或判分规则。
- 实际 SDK+MockTransport：MCP `isError=True` 返回 `returned_error`、闭合 tool history、不 poison binding；模型在同一 Runner 继续合法读取并 claim。合成响应仍计使用量。
- 可选 `index` 被规范化为合法调用并从存储批次丢弃；bool/负 index、其他未知字段、重复 ID、坏 JSON、未闭合批次仍在任何派发前 fatal。
- 混合批次第二个调用 schema 非法时，整批零派发、无 tool event，run 以 `chi_tool_batch_invalid` incomplete 结束。
- **P0 结论：未复现“当前、可信、未派发的业务拒绝被误判 fatal”。** payer002 后继根因是已修的可选 `index` 兼容；现有 MCP 业务错误已有返回路径。因此本卡没有新增 2/3 次恢复策略、没有清 `guard.error`、没有放宽协议/角色/case/未知副作用/取消/未知 usage/持久化错误。

## 5. C：正式配送与默认 off 配置

### 5.1 发现并修复的供应不一致

1. `go_chi_harness` 的宿主凭据拒绝集合缺少 `DEEPSEEK_API_KEY`，而 `go_chi_delivery.FORBIDDEN_ENV` 已包含它。修复为 harness 直接复用同一集合。修复前反例（baseline + 真实 Harbor 组件 + 假 environment）返回 `NO_ERROR`；修复后返回 `RuntimeError chi_harness_environment_invalid`（`counterexamples/c_before.log`、`c_after.log`）。
2. harness 新引用 `go_chi_delivery` 后，该模块原先不在 `PACKAGE_FILES`，正式包会缺模块。已将 `scripts/go_chi_delivery.py` 纳入包成员，并生成新包身份。

### 5.2 三 role 装配与缺供给（真实 Harbor 组件、假 environment）

`tests/test_score_readiness_delivery.py` 使用 `AgentFactory`/`GoChiHarness`/`MCPServerConfig` 等真实 Harbor 组件和记录型假 environment：

- provider 8020、payer 8100、cm 8200 各一条正常装配：先无 Key preflight，再 live；live 参数含 `--role`/`--output-root`/`--history-mode`，不含 `--input-summary`/`--output-recovery`/`CHI_DEV_*`/`dev_patient`；exec env 仅 `OPENCODE_API_KEY`。
- 缺/错 role、错端口、坏 bundle SHA、缺 Key、preflight 非零、宿主 `DEEPSEEK_API_KEY`、非空 scoped env 均在命名边界停止；缺 Key/preflight 失败不会启动 live。
- `install()` 仍是明确 no-op；没有新增网络下载、安装或 Key 搜索。
- 正式包排除 `dev_patient_adapter.py`、`dev_patient_broker.py`、`role_operator.py`；CM 正式患者供应与包外 Go 模拟器分列。
- 默认 off：`GoChiHarness.CLI_FLAGS == []`；entry 的 `--input-summary`/`--output-recovery` 默认 None；两者同时给出时在 identity 前以 `chi_summary_configuration_invalid` 拒绝；`RECOVERY_POLICY.default_enabled=False`、`SUMMARY_POLICY.default_enabled=False`。
- 摘要/恢复正式透传仍未实现；本卡只列缺口：若最终采用，需在正式 harness 增加显式、互斥、默认 off 的参数接线并重新取身份/授权，不能把包外 CLI 能力当成正式适配已完成。

### 5.3 隔离包身份与预检

从 `git archive 0e9d079:chi-agent` 的只读快照构建；未打桩 identity/profile：

| 项目 | 实测身份 |
| --- | --- |
| 新 Go canonical bundle manifest | `f70bb13db0faa07aed1e715cd0395fdd2aec9be0e47587b41ef9ca62d9edf509` |
| 新 runtime identity | `119ee6cbb0e4a456e4266c602889b76dc621430e5638ebe93166a45c23a5d684` |
| 新 release manifest（raw SHA256） | `6442a06bdd0004b3cd5053b4fdbf7eb56524e00732f6b1673a72097e785c5f73` |
| release source_commit | `0e9d079ac738a1950af8305975face97bbd9c90a` |
| 旧 evaluation canonical manifest | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，不变 |

与 PR58 已审包 `76be6620…`（41 成员）逐成员比较：新增 `scripts/go_chi_delivery.py`；变化 8 项：`go_chi_bundle.py`、`go_chi_entry.py`、`go_chi_guidance.py`、`go_chi_harness.py`、`go_chi_runtime.py`、`go_chi_state.py`、`go_chi_summary.py`、`go_chi_tools.py`；其余 33 项一致。新包 42 成员。

隔离预检命令（无 Key、`--network none`、`/package:ro`、vendor/deps 只读）实际返回 `status=identity_verified`、`identity_sha256=119ee6cb…`、upstream clean=`4444a07…`、`official_reward=null`。预检只证明离线身份/导入，不证明业务/MCP/模型或执行许可。新身份没有真实 B 收据；旧 B 不适用，不能复用旧许可。

## 6. D：安全诊断保留、已有指导与余量盘点

### 6.1 修复前反例

`counterexamples/d_before.py` 在 baseline 上模拟 runtime 已写有效 `run_log` 后 entry 外层失败：entry 用精简日志覆盖，`completion`、`context_requests`、`journal_usage`、`safe_cause` 等丢失，计数被改写为 0。baseline 输出见 `d_before.log`。

### 6.2 实现

- runtime `run_log` 升级为 `chi-go-run-log-v2`（新增 schema 和 `final_output_claimed`）。
- entry 失败路径：有界读取（1 MiB、拒绝符号链接、重复键/非有限值/未知 schema/未知顶层键），只复制白名单字段；`safe_cause` 必须通过 `validate_cause`；`safe_error_code` 等只接受有限 code；哈希只接受 64 hex。
- 有效 runtime 日志保留 `safe_cause`、计数、usage、completion/context 等，另加 `first_error_code`/`outer_error_code`/`journal_error_code`；`cleanup_error_code` 在 finally 单独补写，不覆盖首个失败。
- 无日志/损坏/过大/未知 schema/符号链接：写明确 `log_fallback=true` + `log_fallback_reason=invalid_or_missing_runtime_log` 的最小安全日志；不合并任意文本，不输出原异常正文或 secret。符号链接不被跟随，写入失败按 `chi_log_persistence_failed` 处理。
- guidance 升为 `chi-role-guidance-v3`，在原有 stages/invariants 上增加 `plans`、`open_gaps`、`blocked` 和“可选 MD、患者拒绝/STOP、不适用/受阻分支仍合法”的 note；没有新增义务清单 schema 或硬 claim 门禁。

修复后反例保留 `completion/context_requests/journal_usage/safe_cause/provider_requests/tool_events`，并显示 first/outer 分层（`d_after.log`）。测试另覆盖损坏、超大、未知 schema、额外顶层键、坏 cause、符号链接、cleanup 失败。

### 6.3 只读余量盘点（已选 run，分组、不补零）

脚本：`runs/score-readiness-hardening-20261105/inventory.py`；输出 `inventory.json`。只读已存 `run_log/run_result/context/trace/orchestration`，未启动服务。

| candidate | role | task/标签 | simulator | status | provider req | input/output tok | context max chars / est tok | elapsed ms | 900s 准入余量(粗) | trace REFUSED/ERROR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W-actual | provider | CASE-ACT-001（公开输出标签） | none | complete | 21 | 4,886,284 / 31,545 | null / null | 474,377 | 425,623 ms | 1 / 1 |
| W-actual | payer | CASE-6B9F238D（公开输出标签） | none | complete | 26 | 4,059,724 / 21,965 | null / null | 319,665 | 580,335 ms | 0 / 1 |
| W-actual | cm | cm_afib_moderate_anxious_001 | dev-go | complete | 33 | 3,901,866 / 28,392 | null / null | 382,263 | 517,737 ms | 1 / 2 |
| real-external-v2 | provider | pa_t032_t032_o002_p01_new_referral_provider | none | incomplete `chi_timeout` | 17 | 3,147,059 / 33,754 | 1,072,759 / 268,190 | 468,725 | 431,275 ms | 0 / 0 |
| real-external-v5 | cm | cm_afib_moderate_anxious_001 | dev-go | complete（completion blocked readback） | 37 | 5,465,882 / 53,288 | 677,215 / 169,304 | 602,449 | 297,551 ms | 4 / 6 |
| real-external-v7 | payer | pa_t027_t027_o002_p01_nurse_review_payer | none | complete（mechanical_pass, claim present） | 35 | 6,963,185 / 35,726 | 887,726 / 221,932 | 724,930 | 175,070 ms | 4 / 1 |

- 估算 token 与真实 input token 的比例分别为 0.085、0.031、0.032（仅这三组有 context 数据）；byte 估计不是 tokenizer 计数。
- W-actual 旧日志没有 context/usage 字段，保持 null，不补零；未把不同候选/旧 schema 混为一个样本。
- `elapsed_ms` 是 runner/orchestration 粗值；准入余量按 900s 减 elapsed 的上界计算，不是“最后一次新请求”的真实时间戳。
- real-external-v5 的 completion 为 `blocked`、reason `completion_readback_required:call_02_…`，claim 为 null；这是 final_text 未 claim 的现有边界，不是本轮新增硬门禁。
- 未从 6 个样本发布稳定 p95、通过率或分数提升，也未据此修改任何上限/窗口/额度。

### 6.4 时间层

| 层 | 值 | 作用 |
| --- | --- | --- |
| 主请求 read | 240s | 单次 socket 读取 |
| 主请求 I/O | 300s | 单次 main 绝对上限 |
| 确认 read / I/O | 360s / 420s | 确认子请求 |
| CHI 准入 | 900s | 从 run 开始后允许新请求的窗口 |
| B 准入 | 180s | coding-B 新请求窗口 |
| 辅助/患者 read | 450s | 开发患者模拟器连接/读取 |
| CHI operator | 1380s | 包外 controller 的 C 超时下限 |
| role runner | 1500s | 包外 development runner 超时 |
| role operator max | 2040s | controller 配置固定上限 |

## 7. 历史保留与边界

- 旧 S 账 `runs/validation-live-20261104/state/chi-accounting.json` 仍为 `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`；`pending=null`、`halted=null`；`vprep-s-001` 仍 failed/`chi_summary_invalid`，`vprep-b-001` complete。未核销、未重发、未迁移、未换账根。
- 未改旧 accounting/pending/receipt/seal/wire/轨迹；未读隐藏 expectations/solution/verifier；未读 Key/.env。
- 旧 v1 task-state/报告保持原语义；新代码只读接受 v1 summary protected snapshot，不重写历史。
- 旧 B 收据不适用于新包身份；新身份需新 B 和另行真实授权。

## 8. 明确未改 / 未验证

- 未做真实模型、摘要、续写、B/C、患者、world、Trial、judge、发布；`official_reward=null`。
- 未新增摘要接续、方案 B 选区上限、层级记忆、新清单硬门禁、加额度、全面重构、Runner 重启或自动补发。
- 摘要/输出恢复默认关闭且互斥；Y 关闭；摘要 v2 真实兼容/忠实度/净费用收益仍属 PR58 独立专项，未验证。
- 正式 harness 尚未透传摘要/恢复；若采用需另立接线与授权，不能把本离线通过当成正式启用。
- CM 业务状态回读只能依赖 case-scoped `cm_chart.get_chart_data`；公开工具面无 plan 读取，机械报告不能证明 plan finalize。
- `final_text` 未 claim 仍不会被阻止；报告已如实标注 `final_text_without_claim_not_blocked`。
- 真实端点是否接受新 state/report/guidance、真实模型是否按新规则使用工具、真实 Harbor world/Trial/operator、官方患者模拟器、取消/在途和清理仍未验证。
- 开发镜像缺 `anthropic`，两个 dev patient 模块在适用全量中显式排除；8 个 operator skip 只在 dev 镜像出现，controller 已 12/12 通过。
- 本报告不声称临床正确、业务通过、官方分数或稳定统计收益。

## 9. 给 GPT 独立复审的入口

1. 分支/提交：`deepseek/score-readiness-hardening`；A `916ef48`、B `fe50ffc`、C `ea2e987`、D `0e9d079`；包绑定代码候选 `0e9d079…`。
2. 本文与 [REVIEW_STATE](REVIEW_STATE.md)、[tasks](../openspec/changes/score-readiness-hardening/tasks.md)。
3. 关键源码：`scripts/go_chi_state.py`、`go_chi_tools.py`、`go_chi_mcp.py`、`go_chi_contract.py`、`go_chi_runtime.py`、`go_chi_summary.py`、`go_chi_guidance.py`、`go_chi_entry.py`、`go_chi_harness.py`、`go_chi_delivery.py`、`go_chi_bundle.py`。
4. 新增测试：`tests/test_go_chi_state.py`、`test_go_chi_capabilities_runtime.py`、`test_score_readiness_tool_contracts.py`、`test_score_readiness_delivery.py`、`test_score_readiness_diagnostics.py`。
5. 本地证据（忽略目录）：`runs/score-readiness-hardening-20261105/`（`pytest.log`、`controller.log`、`anthropic-gap.log`、`counterexamples/*`、`inventory.json`、`package/exports/*`、`package/preflight.log`）。
6. 复核建议命令：`git diff 6533776..HEAD -- chi-agent/scripts chi-agent/tests`；按第 2 节命令重跑；用新 manifest `f70bb13d…` 重跑隔离 preflight。

本 Prompt 只授权离线实施和本地提交；未 push、未开 PR、未 merge/auto-merge。等待 GPT 复审及用户决定 Git 交付和任何真实运行。
