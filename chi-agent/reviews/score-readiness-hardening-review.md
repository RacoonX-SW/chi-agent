# 最终验证前 A–D 有界离线加固：实现与证据

日期：2026-11-05（Asia/Shanghai）。结论：A–D 已完成有界离线实现、Docker/Python 3.12 禁网自测、隔离包身份/预检和只读余量盘点；未进行任何真实模型、摘要、续写、B/C、患者、world、Trial、judge 或发布调用。official_reward 全部为 null。本文是唯一详细证据；短状态只写 [REVIEW_STATE](REVIEW_STATE.md)。

> **返工状态（2026-11-05）**：初审快照 `33e6ecabbda388f1947a96b892acef328d27c4e1` 的独立复审结论为**不通过**（2 项 P1、2 项 P2）；第一次返工 `4613fd110236c8c371a1f7df54573c5caecc8c7f` 复审仍**不通过**（R1/R4 限定通过，R2 剩 1 项 P1、R3 剩 1 项 P2）。原候选与两次失败均保留；R1–R4 追加在第 10 节，第二轮 R2/R3 追加在第 11 节，不覆盖第 1–10 节的历史含义。

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

## 10. 返工 R1–R4（初审不通过后追加）

初审 `33e6eca` 的“不通过、2 项 P1、2 项 P2”保持原义；本节只记录返工，不把返工通过回写成初审通过。返工代码候选为 `e9455042a055a87d7bc3fb97ece4cbcda93618f5`。

| 卡 | 提交 | 主题 |
| --- | --- | --- |
| R1 | `f2ecd84` | 同文件合法修复后才解除交付失败；state/completion v3 |
| R2 | `af08fe9` | runtime log 结构/嵌套键/类型/有限错误码严格校验 |
| R4 | `e9c503a` | 状态来源描述按 role/canonical 工具精确化 |
| R2b | `e945504` | 收窄 safe error code 集合，排除已知但非错误字面量 |
| R3 | 本文档提交 | 只读余量盘点 v2 与证据更正（脚本在忽略目录） |

### 10.1 R1 / P1：文件交付失败后的永久 claim 阻断

**独立反例（GPT 提供，已复跑）**：`local-fs-edit` 返回 `ERROR: old_string not found`，随后同一路径 `local-fs-write` 成功写成正确内容，`triage.get` 同 case 回读，`local-state-update` 更新状态，`local-claim_done`。baseline `6533776` 为 `recorded / mechanical_pass`；原候选 `33e6eca` 为 `REFUSED: completion_file_write_failed:bad_edit`，文件内容已修正。返工后恢复 `task marked as done / mechanical_pass`，6 次合成请求，无额外 HTTP。

**最小修法**：
- `TaskState` 观察新增程序拥有的 `resource`（仅 local write/edit/read 的绝对路径，最长 2048，拒绝控制字符）；匹配键为 `(scope, resource)`。
- 保留全部失败观察；`_unresolved_file_deliveries()` 只把“最后一次失败之后没有同 `(scope, resource)` 成功 write/edit”的失败列为未解决。
- 无关路径、其他 case/role、只在失败前成功的写、模型 note 均不能解除；后续再次失败会重新阻断。
- `failed` 仍先登记 open unknown；unknown 解析后若没有同资源成功修复，仍阻断。`refused` 不是失败交付。claim 后写、重复写、跨 case/患者保护不变。
- state 升 `chi-task-state-v3`，completion 升 `chi-completion-v3`，报告新增 `unresolved_file_deliveries`；旧 v1/v2 summary 只读接受，不重写历史。

**验收**：`test_go_chi_state.py` 覆盖同文件修复、无关文件/其他 case/其他 role、修复后再次失败、unknown 后同资源修复；`test_go_chi_capabilities_runtime.py` 用实际 SDK+MockTransport 覆盖上述 6 请求正常路径及无关文件仍拒绝路径。全部通过。

### 10.2 R2 / P1：日志保留的实际结构与有限错误码

**独立反例（GPT 提供，已复跑）**：原候选接受并保留
`physical_requests={"main":1,"injected":"synthetic-secret-marker"}`、
`completion={"schema":"chi-completion-v2","injected":"..."}`、
`safe_error_code="synthetic_secret_marker"`，且 `log_fallback=false`。返工后三者均 `accepted=false`、`fallback=true`、注入文本不保留。

**最小修法**：
- 为 `physical_requests`、`journal_usage`、`current_run_agent_usage`、`recovery_limits`、`task_state_target`、`task_state_claim`、`task_state_open_unknowns`、`completion`、`unresolved_file_deliveries` 定义精确键集/类型/边界；`completion` 支持 v2/v3 且校验 reason、target、claim、status view、reference、stagnation、limitations、note。
- 计数字段只接受非 bool 的非负 int；错误码只接受 `go_chi_diagnostics.SAFE_ERROR_CODES` 的有限集合；未知嵌套键、缺核心字段、bool/负数、未知 code 均 fallback。
- 保留正常 runtime 字段；fallback 只写白名单最小安全字段；`safe_cause` 继续严格校验；符号链接/超大/损坏/重复键/非有限值继续拒绝；first/outer/journal/cleanup 分层不变。
- 新增实际 runtime 日志回归：`go_chi_entry._read_run_log()` 接受 `CapabilityRuntimeTests` 产生的正常日志。

**验收**：`test_score_readiness_diagnostics.py` 覆盖三个原始反例、未知嵌套键、缺核心字段、bool/负数、未知错误码、正常日志保留、cleanup/写入失败和 secret 不进入保留结果；全部通过。

### 10.3 R3 / P2：包外余量盘点证据更正

**原分析问题（保留为历史）**：`inventory.py` 分别读取 run_log/run_result/context/trace，没有一致 hash 快照；读取间变化会混合旧 status/provider_requests 与新 input_tokens。trace 缺失时 refusal/error/unknown 仍为 0；completion 缺失时 claim_present 仍为 false。`estimated_to_actual_input_ratio` 用“最大单请求估计 / 全 run 累计 input”，不能用于判断估计准确率。

**返工**：
- 新 `inventory.py` 对每个 run 的 5 个文件各读取两次并比较状态+SHA-256；只有 `snapshot_stable=true` 才输出派生指标；变化时只输出 `snapshot_status=changed_during_read` 和空指标，不生成混合结果。
- 输出 `source_hashes`（status/bytes/sha256）；缺失、损坏、超大、截断、空文件分别有 status；只有 `trace_status=present` 才能输出 0，`completion_status` 缺失/无效时 `claim_present=null`。
- 删除不可配对的估计准确率指标，改为 `estimated_token_ratio=null`、`estimated_token_ratio_status=not_measured_no_same_request_usage`。
- 旧 `inventory-v1.json` 保留；新输出 `inventory-v2.json`，不改写旧分析结论。

**独立检查**：`inventory_checks.py` 实测 missing trace → `trace_refusals=null`、`claim_present=null`；corrupt trace → `trace_status=invalid`、计数 null；complete trace → 0/1 有效；读取间变化 → `snapshot_stable=false`、指标 null；真实 payer-014 → hashes 匹配、前后文件 hash 不变、`trace_refusals=4`、`claim_present=true`。真实行仍按候选/角色/任务/模拟器分组，未补零、未发布 p95/分数。

### 10.4 R4 / P2：来源描述矛盾与测试覆盖表述

**修法**：
- `local-state-update` 描述改为按 role 列出精确 canonical 状态读：provider `cases.get_case`/`auth.check_status`；payer `payer_intake_hub.get_intake_case`、`triage.get`、`review.get_nurse_review_data`、`review.get_md_review_data`、`determination.get_summary`、`p2p.list`、`payer_letter_center.list`；cm `cm_chart.get_chart_data`。其他 chart/document/policy/workspace-file/error/refused 仍只是证据。
- payer guidance 明确 `payer_letter_center.list` 是允许的 case-scoped letter-state read，`payer_letter_center.get` 及其他 letter/document/file 读只是证据；cm 明确 `cm_chart.get_chart_data` 不是 care-plan finalize 的证明。
- 未放宽 `BUSINESS_STATUS_READS`，未新增状态来源。新增独立测试核对描述、`source_kind_for` 接受/拒绝和 guidance 文本。

**测试覆盖表述更正**：原适用 pytest 的 8 个 skip 实际为 `test_go_chi_operator` 3 项 + `test_role_operator_config` 5 项。controller 的 12 项是 `test_role_operator_config` 5 项 + `test_role_validation_wiring` 7 项，**不覆盖**前 3 项。返工单独在 controller 镜像运行 `tests.test_go_chi_operator`，**3 tests OK**；证据 `runs/score-readiness-hardening-20261105/controller-operator-rework.log`。不能再只用 12 项声称覆盖全部 8 个 skip。

### 10.5 返工后的测试、包与历史

| 检查 | 实际结果 |
| --- | --- |
| 适用全量 pytest（dev；Harbor overlay；隔离 runs） | **exit 0：948 passed、8 skipped、333 subtests passed**（27.44s） |
| controller `test_role_operator_config` + `test_role_validation_wiring` | **exit 0：12 tests OK** |
| controller `test_go_chi_operator` | **exit 0：3 tests OK** |
| anthropic 两模块 | **exit 2：2 collection errors，`ModuleNotFoundError: anthropic`** |

新包（代码 `e945504`）：

| 项目 | 实测 |
| --- | --- |
| Go manifest | `b3d0e87bd10b30a9d2adb6af00585dbeaad92b4c2e7b5d203fbcc97c4233d8a8` |
| runtime identity | `e339836ffc0ce6ed081f6c9a413e487faa6b6c52c7bb49160d0c8a13724298d4` |
| release manifest | `c2f9d680fb55221b5ec25fb4998e62f5725120964c67750601f5bff8ab748ca3` |
| release source_commit | `e9455042a055a87d7bc3fb97ece4cbcda93618f5` |
| 旧 evaluation manifest | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，不变 |

42 成员；相对初审包 `f70bb13d…` 无增删，变化 6 个脚本：`go_chi_diagnostics.py`、`go_chi_entry.py`、`go_chi_guidance.py`、`go_chi_state.py`、`go_chi_summary.py`、`go_chi_tools.py`；其余 36 项一致。隔离无 Key/禁网 preflight 实际 `identity_verified`、upstream clean、`official_reward=null`。新身份没有新 B；旧 B 不适用。

历史保留：旧 S 账仍 `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`，`pending=null`、`halted=null`，`vprep-s-001` 仍 failed/`chi_summary_invalid`、20 settled；未核销/重发/迁移/换账根。旧 accounting/pending/receipt/seal/wire/轨迹未改。

### 10.6 仍未验证

- 真实模型、摘要、续写、B/C、患者、world、Trial、judge、发布仍为 0；`official_reward=null`。
- 新包真实端点是否接受 v3 state/completion/log 校验、真实模型是否按新描述使用工具、真实 Harbor/operator/官方患者/取消/在途/清理仍未验证。
- CM 仍没有公开 care-plan 读取工具；`cm_chart.get_chart_data` 只是机械业务资源回读，不能证明 plan finalize。
- `final_text` 未 claim 仍不会被阻止；这是保留的既有边界。
- 两个 anthropic 模块的 collection error 与 dev 镜像 8 个 operator skip 继续单列，不写全环境全绿。

## 11. 第二轮返工 R2/R3（第一次返工不通过后追加）

第一次返工快照 `4613fd110236c8c371a1f7df54573c5caecc8c7f` 的独立复审结论为**仍不通过**：R1、R4 限定离线通过，R2 剩 1 项 P1，R3 剩 1 项 P2。初审 `33e6eca` 与第一次返工 `4613fd1` 的失败均保留原义；本节只记录第二轮修复，不覆盖前两轮结论。

| 项 | 提交/证据 |
| --- | --- |
| R2 修复 | `36db613358ac9d01d792ee8f0bb4d39431c02b9e` |
| R3 修复 | 包外 `runs/score-readiness-hardening-20261105/inventory.py`，SHA-256 `00433eaac6f675fc05ef491be5b4f72571e278e9ab28694afc8ba1be3a622952` |
| 第二次返工代码候选 | `36db613358ac9d01d792ee8f0bb4d39431c02b9e` |

### 11.1 R2 / P1：非法嵌套类型不得击穿错误处理

**独立反例（GPT 提供，已复跑）**：在其余字段合法的 runtime 日志中分别设置
`completion["verification"]=[]`、`business_effect={}`、`required_readback=[]`、`remaining_limitations=[{}]`。原候选 `_read_run_log` 与 `_failure_run_log` 均抛 `TypeError`，无 fallback；合成 entry 在 `chi_timeout` 后遇坏日志也抛 `TypeError`，无最终安全 JSON。

**最小修法**：
- 所有嵌套 validator 在枚举/set membership 前检查 `str` 类型；覆盖 `verification`、`business_effect`、`required_readback`、`remaining_limitations` 元素、reference/status `event`、`source_kind`、`unresolved_file_deliveries.event` 等。
- `_read_run_log` 外层增加读取/验证异常边界：任意畸形嵌套 JSON 返回 `None`，不向上抛；`_failure_run_log`/cleanup 读取坏日志时走明确 fallback。
- 不吞写盘错误：`_write_run_log` 仍返回 False，main 仍以 `chi_log_persistence_failed` 收口；首个 `chi_timeout` 保留在 `safe_error_code`/`first_error_code`，外层错误另列。
- 正常 runtime 日志、有限错误码、safe_cause、first/outer/journal/cleanup 分层、wire/journal 原字节不变。

**返工后实测**：四个原始反例均 `accepted=false`、`fallback=true`、注入文本不保留；`verification`/`business_effect`/`required_readback`/`limitations` 的 list/dict/null/int/string 错误类型均 fallback；reference/status/unresolved event 的 list/dict 错误类型也 fallback。合成 entry 先 `chi_timeout` 再遇坏日志时返回受控失败（exit 1）、stdout 安全 JSON、`run_log.log_fallback=true`、`safe_error_code=chi_timeout`、`first_error_code=chi_timeout`。正常实际 runtime 日志仍 `_read_run_log` 非 None。

**测试**：`tests/test_score_readiness_diagnostics.py` 新增嵌套类型矩阵、reference/status/unresolved 类型矩阵和合成 entry 错误边界回归；全部通过。

### 11.2 R3 / P2：区分“JSON 可解析”和“记录完整”

**独立反例（GPT 提供，已复跑）**：原盘点对
`completion={}`、`completion` 有 schema 但缺 `claim`、`completion={"schema":"chi-completion-v3","claim":17}` 分别输出 `present/false`、`present/false`、`present/true`；`trace` 只有 `{"role":"tool"}` 或 `{}` 时仍 `present` 且计数 0。

**最小修法**：
- `_completion_state()` 校验受支持历史版本 v1/v2/v3、必要键集、verification/business_effect、target、claim 结构、claim_violation、open_unknowns、note 及 v2/v3 的 claim_policy/reference/required_readback/limitations/unresolved；缺字段标 `incomplete`，错误类型/未知键/非法 claim 标 `invalid`，相关 `claim_present` 为 `null`。
- `_trace_counts()` 要求每行是 dict、`role` 在受支持集合、`content` 为 str；坏行/缺字段将 `trace_status` 改为 `invalid`，拒绝/错误/unknown 计数为 `null`。只有完整 trace 才输出 0。
- 保留已通过的 SHA 快照、读取变化停止、缺文件/空/损坏/截断区分、删除不可配对准确率指标；旧 `inventory-v1.json`/`inventory-v2.json` 保留，新输出 `inventory-v3.json`，脚本 SHA 见上。

**返工后实测**：`completion={}` → `invalid/null`；缺 claim → `incomplete/null`；`claim=17` → `invalid/null`；合法 v1 真实样本 → `present/false`；合法 v3 真实样本 → `present/true`；trace `{"role":"tool"}`/`{}` → `invalid/null`；完整 trace 明确无事件 → 0；缺文件/空/坏 JSON/截断/读取变化均保持 null 或明确状态。真实 payer-014 行 hash 匹配、前后文件不变、`trace_refusals=4`、`claim_present=true`。

**独立检查**：`runs/score-readiness-hardening-20261105/inventory_checks_v2.py`，输出 `inventory-checks-v2.log`；新盘点 `inventory-v3.json`。旧输出不被覆盖。

### 11.3 保留的 R1/R4 与回归

- R1：同 `(scope,path)` 后续合法 write/edit 才解除交付失败；无关文件/case/role、未解决 unknown、后续再次失败仍阻断；失败记录不删除；实际 SDK 六请求修复路径可 claim，无额外 HTTP。第二轮 `edge_checks` 与全量测试回归通过。
- R4：`BUSINESS_STATUS_READS` 未扩大；canonical 描述、letter list/get、CM chart/finalize 边界不变；8 个 skip=operator 3+role config 5；controller 12 项与 operator 3 项分别执行并记录。

### 11.4 第二轮测试、包与历史

| 检查 | 实际结果 |
| --- | --- |
| 适用全量 pytest（dev；Harbor overlay；隔离 runs） | **exit 0：951 passed、8 skipped、350 subtests passed**（29.24s） |
| controller `test_role_operator_config` + `test_role_validation_wiring` | **exit 0：12 tests OK** |
| controller `test_go_chi_operator` | **exit 0：3 tests OK** |
| anthropic 两模块 | **exit 2：2 collection errors，`ModuleNotFoundError: anthropic`** |

新包（代码 `36db613`）：

| 项目 | 实测 |
| --- | --- |
| Go manifest | `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d` |
| runtime identity | `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc` |
| release manifest | `cfc3d9f42bd9ef2bcf766924faa895dc415f1ed0cd91e8dca0d355ec3d98d1c3` |
| release source_commit | `36db613358ac9d01d792ee8f0bb4d39431c02b9e` |
| 旧 evaluation manifest | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，不变 |

42 成员；相对第一次返工包 `b3d0e87b…` 无增删，只有 `scripts/go_chi_entry.py` 变化；其余 41 项一致。隔离无 Key/禁网 preflight 实际 `identity_verified`、upstream clean、`official_reward=null`。新身份没有新 B，旧 B 不适用。

历史保留：旧 S 账仍 `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`；`pending=null`、`halted=null`；`vprep-s-001` 仍 failed/`chi_summary_invalid`、20 settled。未改旧 accounting/pending/receipt/seal/wire/轨迹。

### 11.5 仍未验证

- 真实模型、摘要、续写、B/C、患者、world、Trial、judge、发布仍为 0；`official_reward=null`。
- 新包真实端点是否接受 v3 state/completion/log 校验、真实模型行为、真实 Harbor/operator/官方患者/取消/在途/清理仍未验证。
- CM 仍无公开 care-plan 读取工具；`cm_chart.get_chart_data` 只是机械业务资源回读，不能证明 plan finalize。
- `final_text` 未 claim 仍不会被阻止；这是保留的既有边界。
- anthropic 两个模块的 collection error 与 dev 镜像 8 个 operator skip 继续单列，不写全环境全绿。

## 12. GPT/Terra 收口 R3 与最终独立离线结论

第二轮候选 `50dd338` 的独立复审为**有条件通过**：包内 `36db613` 的 R2 通过，R1/R4 回归通过，但包外盘点仍因非字符串 schema 抛 TypeError，且错误类型的 mutation call ID / reference 被标为 present。本节追加关闭这一 P2，不覆盖 `33e6eca`、`4613fd1` 的不通过或 `50dd338` 的条件结论。

### 12.1 有界实现与交付边界

用户随后明确要求“直接让Terra改……改完提交pr合并”，本轮由一个显式 `gpt-6.1-terra` / `high` 实现及 Docker 自测，停止写入后 GPT 主代理独立复验、文档和 Git。仅对本 PR 按最新用户指令在检查通过后合并；不启用 auto-merge，不改变其他任务的默认用户合并流程，也不恢复真实运行许可。

最终包外实现候选：`8992af1132f8e369dbfeb86542474ea7a7726c9e`。新增可审的 `scripts/go_chi_readiness_inventory.py` 与 `tests/test_go_chi_readiness_inventory.py`；工具仍不在 `PACKAGE_FILES`，没有修改 R1/R2/R4 或其他参赛包代码。将工具纳入版本控制是为了使修复随 PR 可复现交付，不上传忽略目录的旧轨迹、账本或任务载荷。

- schema 查表前严格检查类型；必要字段、mutation call ID、reference、status、stagnation、unresolved 的类型/结构不合法时产生 invalid/null，不再抛 TypeError 或误报 present。
- v1 非空业务状态按原三字段读取，v2/v3 按七字段读取；v3 未归属文件资源的 `resource=null` 保留为未解决失败元数据，不解释为已修复。主代理审查时发现并要求补齐这两处兼容反例，最终修正后才通过。
- 保留 claim 的 null/对象/缺失/非法区分、trace 完整性、SHA 快照、变化停止及缺项不补零。畸形非标量 reward 也不会因集合操作击穿盘点；不生成官方评分结论。
- 原 `runs/score-readiness-hardening-20261105/inventory.py` 及旧结果未改。原脚本 SHA256 仍 `00433eaac6f675fc05ef491be5b4f72571e278e9ab28694afc8ba1be3a622952`；新脚本 SHA256 为 `86b7938b214735d5f7e4ee7d09e9242410b07188416f58f0b09441472320f110`。

### 12.2 主代理实际独立验证

固定只读快照：`/private/tmp/chi-readiness-final.U8R4dd/snapshot/chi-agent`，与上述实现提交的两份新文件字节相同。Docker/Python3.12，dev 固定 ID `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`；`--pull never --network none --read-only`、`/tmp` tmpfs、源码/依赖与所选历史证据只读，仅专属导出目录可写。无安装/升级、无 Key/env 注入、无真实服务或 Docker socket 挂载。

| 检查 | 实测 |
| --- | --- |
| `/opt/venv/bin/python -m unittest discover -s tests -p test_go_chi_readiness_inventory.py -v` | exit 0，**9 tests OK**；不是引用子代理自测 |
| 独立原失败反例 | schema list/dict、mutation call ID=17、坏 reference 均 invalid/null；无异常 |
| 独立合法/缺项反例 | v1/v2/v3 的 claim null/对象正常；空 completion、缺 claim、claim=17 分别 invalid/incomplete/null |
| trace / 快照 | 缺失、空、坏 JSON、坏行、超行数有明确状态/null；完整记录才 0；读间变化不输出混合指标 |
| 一组必要真实元数据 | 仅 payer-014，5 文件原始 hash 匹配并前后不变；refusal=4、claim=true；其余行未重新逐组盘点 |
| 包 / 历史 | 下述 42 成员逐源字节相同；旧 S strict inspect，120 文件 hash 全同；旧脚本 hash 不变 |

证据与独立脚本保存于本地忽略目录 `runs/score-readiness-hardening-20261105/final-r3-8992af1/`；原始输出不上传。检查脚本最初写于上述 `/private/tmp/chi-readiness-final.U8R4dd/`。本次不重复整套历史回归：`36db613` 已独立实测的 951 passed / 8 skipped / 350 subtests、controller 12 + operator 3、两个 anthropic collection errors 保持其限定范围；本次只新增包外工具与测试，未将旧数量冒充最终树重跑结果。

### 12.3 身份、历史与最终结论

逐一比较最终树 `PACKAGE_FILES` 的 42 个源文件，与已独立审核的 `36db613` 源快照全部同字节；从本轮快照重新构建 Go 包，manifest 仍为 `c5f569e8a20439c07f020fd8776af4aba4d62da0c64e86e2da88e744cc077f0d`。实际隔离包无 Key 禁网 preflight 返回 `identity_verified`，runtime 仍 `2a9a32711f8e3de43eac037fe2c745c803c09851e71947dae36325d1931953fc`。不把包外提交变化冒充内包变化；第11节 release 继续明确绑定其原 `source_commit=36db613…`，本轮未重新生成另一外层 wrapper。

旧 S accounting 仍 `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`，failed/`chi_summary_invalid`、20 settled、pending/halted null；未改旧 pending/receipt/seal/wire，未核销、重发或换账根。

**最终限定离线结论：通过，R1–R4 的本次有界缺陷已关闭，可交付本 PR。** 无真实模型/摘要/续写/B/C/患者、world/Trial/judge 或发布；不证明正式配送、摘要忠实度/收益、临床结果或官方分数。新候选仍无新 B；旧 B 不适用，最终候选的真实 B/九题及后续运行须另行具体批准。CM 无公开 plan 回读、final_text 未 claim 不被阻止等已明确边界仍保留。
