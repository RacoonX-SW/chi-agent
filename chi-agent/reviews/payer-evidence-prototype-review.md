# Y：payer证据核对原型与开发shadow

**DeepSeek实现者交付，待Codex独立审核。**

日期：2026-10-31（Asia/Shanghai）。范围见[五步计划](../openspec/changes/payer-evidence-prototype/design.md)与[行为契约](../openspec/changes/payer-evidence-prototype/specs/evidence-checkpoint/spec.md)。本报告只记录实现者自测和本地候选；新增真实B/C、患者、评审请求均为**0**，未读模型Key、未启动官方题世界、未调用项目模型API，`official_reward=null`。自测、本地commit和go判断都不等于Codex验收或真实业务收益。

## 基线与候选

| 项 | 实际值 |
| --- | --- |
| PR29核对 | 开工时 `origin/main` 仍为 `594791e401391c9f82a6ec5cfab5694af1df9242`（PR28 merge），规划HEAD `78f1c52` 不在main；按用户停止条件先交回缺口，未在旧分支追加实现 |
| 用户合并后基线 | `0ac9f0fd9d4f5c4e5a41028727015768dbae8c07`（PR29 merge；先fetch确认） |
| 实现分支 | `codex/payer-evidence-prototype`（从上述main建立） |
| 实现提交 | `5ce8d9dd11220b3d6b4c4dedbccadf120d5c2f9f`（12文件，+1166/−12） |
| 报告/状态提交 | 紧随其后的本地提交；最终分支HEAD为准 |
| 用户既有改动 | `AGENTS.md`、`COLLABORATION.md` 原diff保留，未修改、未暂存、未纳入提交 |
| 远端操作 | 未push、未创建PR、未merge/auto-merge |

候选身份按层记录：`5ce8d9d` 是代码/测试/规格的实现身份；报告与REVIEW_STATE追加提交只改变交付文档，不等于新的实现验收。两者都在同一本地分支，Codex应以最终HEAD的diff复核。

## 改动清单

| 文件 | 作用 |
| --- | --- |
| `scripts/payer_evidence.py`（新） | 纯离线来源注册与引用边界核对；无文件、网络、模型、凭据、world访问 |
| `scripts/go_chi_tools.py` | payer显式shadow时追加 `local-evidence-sources/excerpt/check` 三个有界只读工具；复用原dispatch lock、fatal、ToolContract、journal |
| `scripts/go_chi_runtime.py` | `run_chi(..., evidence_shadow=None)` 默认关闭；接受 `off`/`shadow`，仅payer可shadow，透传instruction |
| `scripts/role_runner.py` | 包外开发装配读取 `CHI_DEV_EVIDENCE_SHADOW`；默认关闭，仅payer，值非法即拒绝 |
| `scripts/go_chi_bundle.py` | allowlist加入纯模块，保证包默认导入完整；身份因此改变，未签发/复用B |
| `tests/test_payer_evidence.py`（新） | 22个纯契约/边界/反例测试，自造材料 |
| `tests/test_payer_evidence_shadow.py`（新） | 9个合成runtime/guard/包检查测试 |
| `openspec/.../design.md` | 写入第1步冻结的来源语义、可检测/不可检测、边界值、改动清单和数据流 |
| `openspec/.../spec.md` | 指向冻结值，避免两处数字漂移 |
| `openspec/.../tasks.md` | 标记实现者完成；明确不代替独立审核 |
| `README.md` | 新增离线测试命令、shadow开关与边界；未授权真实运行 |
| `docs/learning-agreement.md` | 只增关键取舍/下一入口，不记掌握 |

未修改：官方vendor/services/verifier、依赖锁/镜像、真实账/旧runs、模型/费用/超时策略、`evaluation_entry` live拒绝、全局协作规则。

## 五步结果

### 1. 收益假设与可检验契约

收益假设只限**可机械检测的引用/身份/先后关系错误**：引用不存在、未观察、同批新结果、参数可归属时的错case、hash不符、片段越界/倒序/过长、重复ID、坏结构/超限。明确不声称能检测：真实片段下的错误解释、建议/必需性的临床适用、签署效力、政策时效、文本是否语义支持主张。`reference_validation=valid` 已固定禁止命名成approved/evidence_sufficient/clinical_pass。

来源只取两类：本次payer运行实际送入主模型请求的公开instruction，以及成功返回并已进入下一请求历史的工具文本。复用原 `run_chi()` 的 `observed_request()` → `exchanges`，最终事件从 `journal.run["tool_events"]` 读取；不新建观察通道。来源ID `src-0001` 由程序分配，文本hash与片段hash由程序计算；模型只填case/claim类别/source_id/字符片段/规则性质/未解决项，不计算hash或维护计费状态。

片段统一为**UTF-8解码文本的0起始、结束不含字符索引**，不混字节/PDF页号。边界值冻结在design的“第1步冻结”表并在测试中覆盖精确边界与越界（见下）。接口核对基于当前源码：`run_chi()`、`MCPBridge.invoke()`、`local_tools()`、`ToolContract`、`ChiJournal.record_tool` 均为现有入口，未虚构。

### 2. 纯离线原型

`payer_evidence.py` 只依赖stdlib。`EvidenceRegistry` 提供来源登记/清单/片段读取/核对表验证；无任意文件读取、HTTP、模型、world写入或凭据。自造材料使用 `case-synthetic-001`、合成政策/表格/冲突文本，与t011人物、ID、题文、期望值无关，未复制原PDF或手册正文。

模型字段与程序字段分列；`rule_nature` 只输出为 `rule_nature_reported`，顶层固定 `rule_nature_status=unverified_model_report`，不把标签升级成已证实规则。所有结构/大小越界明确返回 `invalid` + 理由，不静默截断为有效。

### 3. 反例与go/no-go

契约场景在Docker/Python3.12实跑，全部失败与修正见“失败”节。关键反例：

- 合法引用但语义过度解释：claim写“政策要求暂停所有批准”，引用文本实际是“护士在条件满足时可批准”。结果 `reference_validation=valid`、`semantic_assessment=not_performed`；程序没有、也不声称识别临床错误（`runs/payer-evidence-prototype-20261031-01/counterexamples.json`）。
- 同一claim改为不存在的 `src-9999`：`invalid/source_unknown`。
- 建议性缺项：`rule_nature=recommended` + `unresolved.missing` 结构通过，不产生pend/blocked/request_info。
- 必需条款+缺文件：可表示 `not_met` 与missing，不自动提交request_info。
- 合法护士批准路线：不被结构层拒绝。
- 同批前排刚返回的结果：后排核对引用为 `source_unknown`，下一请求后才可引用。
- 其他case（参数含不同 `case_id`）、错误hash、越界/倒序/超长片段、重复ID、坏类型/额外字段/超限均明确invalid。

**决定：go（仅指值得做默认关闭的开发shadow接线，不等于模型收益成立）。** 依据：所有可机械校验的失配被准确拒绝；合法护士路线、建议性缺项和冲突/未知不被误拒绝；限制被准确输出；结果可通过原工具/journal保存；off不新增工具/提示/请求；没有新账、新模型调用或额外业务选择。未触发no-go条件（不是纯格式装饰、来源边界可实现、无需隐藏资料/新依赖/扩权、没有把语义猜测伪装成校验）。

### 4. 默认关闭的开发shadow

`run_chi` 仅接受 `None/off/shadow`，`shadow` 仅payer；包外 `role_runner` 仅在 `CHI_DEV_EVIDENCE_SHADOW=shadow` 时启用，生产CLI不设置该值。shadow只增加三个只读工具：来源清单（仅元数据，不返回正文）、有界字符窗口摘录、核对表校验。三者走原 `local_tools` tracked wrapper：同一dispatch lock、fatal优先、ToolContract pending匹配、`record_result`/`journal.record_tool`；不重入MCP锁、不调用模型、不新增计费所有者。

结构错误只让该核对请求返回invalid；同一运行后续业务MCP仍按原契约执行（测试覆盖）。缺核对表、semantic未判、invalid都不构成业务拦截。fatal在工具执行前停止；取消记录 `started`+`failed(chi_tool_cancelled)` 并传播。包构建包含新模块且排除 `role_runner`/tests；默认导入通过。

### 5. 固定候选

停写后显式暂存本轮12个文件并本地commit；未push/PR。报告与REVIEW_STATE在紧随的文档提交中；最终HEAD为交付候选。`AGENTS.md`/`COLLABORATION.md` 用户改动未纳入。

## 场景覆盖（自测）

| 契约场景 | 覆盖 | 实现者自测结果 |
| --- | --- | --- |
| 充分自造材料、合法护士批准 | `test_nurse_approval_route_is_not_structurally_rejected` | 通过；未强迫MD/挂起，semantic未判 |
| 必需条款+缺文件 | `test_required_gap_and_missing_file_are_represented_without_submission` | 通过；不补造存在、不自动request_info |
| 仅建议性缺项 | `test_recommended_gap_is_kept_as_unresolved_not_converted` | 通过；不转硬条件 |
| 来源矛盾/必需性未知 | `test_conflicting_sources_are_both_located` | 通过；两侧定位，未挑权威 |
| 合法引用但语义过度解释 | `test_semantically_wrong_but_structurally_valid_reference` + `counterexamples.json` | 通过（即按设计无法识别），semantic始终未判 |
| 不存在/未来/自身/仅执行未观察 | `test_unobserved_and_future_ids_are_invalid_until_observed`、`test_errors_listings_and_shadow_results_are_not_sources`、`test_same_batch_result_is_not_citable_until_next_request` | 通过；均invalid且不登记 |
| 其他case/run、篡改hash、越界 | `test_source_from_another_case_is_rejected`、`test_source_hash_tampering_is_rejected`、`test_range_boundaries_and_span_limit` | 通过；理由明确 |
| 非公开路径/符号链接/注入 | 纯模块无文件/执行入口；来源仅内存文本 | 未新增路径能力；恶意文本不被执行 |
| 重复ID/坏类型/额外字段/精确边界 | `test_duplicate_and_bad_claim_ids`、`test_malformed_structures_are_rejected`、`test_size_limits_and_exact_boundaries`、`test_excerpt_tool_bounds_and_text` | 通过；2000字符、32 claims、4000片段、64KiB、16 unresolved等精确边界 |
| off等价/provider-cm隔离 | `test_off_path_has_no_shadow_tools_or_prompt_change`、`test_other_roles_have_no_shadow_tools`、`test_shadow_is_payer_only` | 通过；工具定义/系统提示一致，无evidence工具 |
| shadow错误/同批/fatal/取消 | `test_shadow_structure_error_only_rejects_that_request`、`test_same_batch_result_is_not_citable`、`test_fatal_stops_shadow_tool_before_execution`、`test_cancellation_is_recorded_and_propagated` | 通过；业务不受影响，fatal/取消原样传播 |
| 独立包/身份/历史 | `test_bundle_contains_module_and_excludes_dev_assembly` | 通过；包33文件含新模块，排除开发装配；真实账未触碰 |

“通过”仅指上述合成/自测断言，不是Codex独立复验，也不是真实模型行为。

## 实际执行、环境与证据

全部在Docker内，复用既有镜像/卷，无安装、下载或升级。解释器 `Python 3.12.15`；controller镜像ID `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`；dev镜像 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`；vendor固定 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 且工作树干净；SDK卷 `chi-h-root-model-deps-20261027-v1`、PDF卷 `chi-k-pdf-deps-20261027-v1` 只读。命令均禁网、只读根、无Key、无Docker socket。

纯原型与shadow测试：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$PWD:/workspace:ro" -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  chi-agent-a-control:latest /opt/venv/bin/python -m pytest -q \
  tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py
```

退出0：**31 passed**（22纯契约+9 shadow），pytest 1.50秒，命令壁钟3秒；1条只读根无法写pytest cache的warning，不影响结果。

Go CHI回归（同环境）：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$PWD:/workspace:ro" -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  chi-agent-a-control:latest /opt/venv/bin/python -m pytest -q tests/test_go_chi_*.py
```

退出0：**100 passed、8 skipped、48 subtests passed**，2.46秒；8个skip是本环境未装Harbor overlay/缺Docker SDK的既有条件跳过，未记为通过。

包构建（同镜像）：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$PWD:/workspace:ro" -v "$PWD/runs/payer-evidence-prototype-20261031-01:/out:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  chi-agent-a-control:latest /opt/venv/bin/python scripts/go_chi_bundle.py build --target /out/bundle
```

退出0：33文件；`manifest_sha256=e847a6ae346405c477020d911908a40e3413ec64b32e3e210c2a8bb24f58042e`，`entry_config_sha256=29423f878784d39c1764062939db28e3d6f72eed0daa71dfe6178889c342d3a8`；包含 `scripts/payer_evidence.py`，不含 `role_runner.py`/tests。新增allowlist文件使包身份相对W改变，**未签发或复用任何B**，也未迁移真实账根。

本地产物（忽略目录，不上传）：`chi-agent/runs/payer-evidence-prototype-20261031-01/`，含 `payer-tests.log`、`go-chi-regression.log`、`environment.txt`、`counterexamples.py/.json`、`bundle/`、`failures.md`。

## 失败、修正与保留

1. 首次shadow测试7通过/1失败：`test_cancellation_is_recorded_and_propagated` 原断言只期望 `failed`，实际为 `started`+`failed`。核对实现顺序（先`start_tool`再执行回调）后确认是测试断言错误，改为断言两者及 `safe_error_code=chi_tool_cancelled`。原失败日志未逐字保存，说明与修正后日志见`failures.md`/`payer-tests.log`。
2. 契约反例不是程序故障：语义过度解释按设计仍 `valid`；报告明确保留这一“无法识别”结果，没有把它改写成成功。
3. 只读根导致pytest cache warning；未通过安装或放宽只读规避。
无真实请求重试、未知放行、账目变化或原证据覆盖。

## 程序可证明与不可证明

**可证明（仅限实现者自测）**：在合成输入上，来源必须来自本run已观察文本；不存在/未观察/同批/自身/错误case/错误hash/越界片段被准确拒绝；合法护士路线与建议性缺项不被结构层误拒；大小与结构边界确定；off路径工具/提示/请求等价；shadow结果经原journal保存且不改变业务调用；包可默认导入。

**不可证明**：模型是否会正确使用字符索引、shadow是否改善payer决策或t011终态、真实临床解释是否正确、官方分数、跨任务泛化、真实账/身份可用性。`valid` 只表示引用边界通过。

## 耗时与未记录项

- 两条测试命令壁钟各约3秒（pytest内部1.50/2.46秒）；包构建未单独计时。
- 整个实现/调试阶段未逐项计时，记为**未记录**；不把对话时长或Docker壁钟冒充完整阶段耗时。
- 新增真实请求、token、三项USD费用与`official_reward`：**0 / 未产生 / 0 / null**；开发对话自身消耗不混入CHI账。

## 未验证项与主要限制

1. 未运行任何真实模型，因此不知道模型能否稳定产出有意义的字符偏移；这是该机制最主要的可用性未知。
2. case归属只在工具调用参数含结构化`case_id`时可判定；无该参数时来源仅标run级，程序不靠正文猜归属。
3. 仅排除了本地 `local-fs-list` 与shadow自身结果；MCP“列目录/摘要”类结果无法机械区分，仍可能被引用为来源（但不会被当作事实已证实）。
4. 政策时效/版本失效没有独立判断；只有模型回传 `source_sha256` 时才能发现错版本/篡改，而hash由程序比对。
5. shadow对模型行为、请求量、成本与payer终态的影响均未测；不得据此声称收益。
6. 包身份已改变，旧W的B不能跨身份复用；真实运行前仍须另行授权、重新处理B并复核隐私条件。
7. Harbor正式CLI/真实Go Trial/F.5/官方判分、临床内容评审保持原暂停边界。

## 交付结论

实现者已按五步完成纯原型、反例、go判断、默认关闭shadow接线、合成与包检查，停写并本地固定候选；**待Codex独立审核**。Codex应优先复核：`payer_evidence.py` 的越界/身份语义、`go_chi_tools.py` shadow分支是否保持off等价与业务不拦截、`go_chi_runtime/role_runner` 的启用边界，以及包allowlist/身份变化；再独立重跑上述Docker命令。任何生产强制、真实模型试验、临床或官方结论均需另立规格与授权。
