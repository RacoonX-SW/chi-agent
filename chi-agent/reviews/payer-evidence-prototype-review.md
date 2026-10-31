# Y：payer证据核对原型与开发shadow

当前结论：**Codex独立审核返工，Y离线验收未通过**。独立证据与R1–R3见文末“Codex独立审核”；以下实现者原交付记录保留其当时的自测/待审含义，不能据此覆盖独立结论。

2026-10-31：DeepSeek已按R1–R3返工并提交新候选，见文末“DeepSeek返工交付”；Codex原返工结论保留，**新候选待Codex复审**，不表示已通过。

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

候选快照复跑（从最终HEAD `git archive` 到 `candidate-tree/`，含固定vendor只读挂载）：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/candidate/scripts:/vendor \
  -v "$PWD/runs/payer-evidence-prototype-20261031-01/candidate-tree:/candidate:ro" \
  -v "$PWD/vendor/chi-bench/src:/vendor:ro" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /candidate \
  chi-agent-a-control:latest /opt/venv/bin/python -m pytest -q \
  tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py
```

退出0：**31 passed**（约1.6–1.9秒，两次快照运行）。首次漏挂vendor时同一快照5 failed/26 passed，修正与两份日志见下。

本地产物（忽略目录，不上传）：`chi-agent/runs/payer-evidence-prototype-20261031-01/`，含 `payer-tests.log`、`go-chi-regression.log`、`candidate-tests.log`、`candidate-tests-missing-vendor.log`、`environment.txt`、`counterexamples.py/.json`、`candidate-tree/`、`bundle/`、`failures.md`。

## 失败、修正与保留

1. 首次shadow测试7通过/1失败：`test_cancellation_is_recorded_and_propagated` 原断言只期望 `failed`，实际为 `started`+`failed`。核对实现顺序（先`start_tool`再执行回调）后确认是测试断言错误，改为断言两者及 `safe_error_code=chi_tool_cancelled`。原失败日志未逐字保存，说明与修正后日志见`failures.md`/`payer-tests.log`。
2. 契约反例不是程序故障：语义过度解释按设计仍 `valid`；报告明确保留这一“无法识别”结果，没有把它改写成成功。
3. 只读根导致pytest cache warning；未通过安装或放宽只读规避。
4. 候选快照首次复跑漏挂固定vendor：`run_chi` 导入 `chi_bench.experiment.agents` 时5个shadow runtime测试失败（26 passed/5 failed，`ModuleNotFoundError: chi_bench`）。这是检查环境缺项，不是候选代码失败；补只读 `/vendor` 与PYTHONPATH后同一快照31 passed。失败重放与修正后日志分别保存为 `candidate-tests-missing-vendor.log`、`candidate-tests.log`。
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

## Codex独立审核（2026-10-31）

**结论：返工；不批准继续shadow实验，不将整个Y候选记为离线验收通过。** 保留纯原型、成功/失败和合成接线作返工依据，不回滚或删除实现者证据；是否派实现者返工、是否创建PR及是否合并由用户决定。本轮没有派子代理、修改实现、push、创建PR或merge。

### 身份、差异与隔离

GitHub核实PR29已合并，fetch后origin/main仍为`0ac9f0fd9d4f5c4e5a41028727015768dbae8c07`。本地分支`codex/payer-evidence-prototype`，候选HEAD为`33d3e41283ac68d5dd0af283460a17bee11e8949`；实现提交`5ce8d9dd11220b3d6b4c4dedbccadf120d5c2f9f`，后两个提交只改交付文档。核对基线至候选14文件完整diff，再读纯模块、调用者、ToolContract/Guard、MCP/路径边界、包构建及两份新增测试。候选之外最初仅AGENTS.md/COLLABORATION.md两项已知用户改动，完整保存diff并在结束时比较，不覆盖/暂存/提交。

使用`git archive`导出精确候选及基线，Docker内解包到新的忽略目录`runs/payer-evidence-prototype-codex-review-20261031-01/`；候选228个跟踪文件，基线224个。`snapshot-manifest.json`保存各归档及逐文件hash；复验挂`/workspace:ro`并挂固定vendor，派生日志写`/out`，结束另复核快照及工作区实现文件未变。未使用实现者可变的candidate-tree或已有bundle来替代独立构建。

固定镜像`chi-agent-a-control:latest`实际ID为`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，实测Python3.12.15；vendor HEAD为`4444a07fa68a4f1623f841a292a54e284fc8e7f7`且干净，原model/PDF卷只读。所有复验禁网、只读根、无Key/模型凭据/真实账/官方题世界/Docker socket挂载；无安装、下载或依赖升级。真实Q/CHI完整历史本轮未重审，不将本轮合成结果冒充新身份准入或真实旧账结算证明。

### 独立执行与实际结果

下列共用Docker外壳从`chi-agent/`执行；路径变量展开与本次绝对挂载等价。`run_checks.py`只在容器内调用pytest，保存原stdout、XML、完整子命令/退出码与耗时；没有过滤失败或跳过项。

```sh
Y_REVIEW_ROOT="$PWD/runs/payer-evidence-prototype-codex-review-20261031-01"
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$Y_REVIEW_ROOT/candidate/chi-agent:/workspace:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$Y_REVIEW_ROOT:/out:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  --entrypoint /opt/venv/bin/python chi-agent-a-control:latest \
  /out/run_checks.py payer tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py
```

| 同外壳中的实际程序/参数 | 退出码 | 独立结果与本地证据 |
| --- | --- | --- |
| `run_checks.py payer tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py` | 0 | 31 passed，pytest 2.30秒；`payer.log/xml` |
| `run_checks.py go-regression go-regression`（容器内展开`tests/test_go_chi_*.py`） | 0 | 100 passed、8 skipped、48 subtests，pytest 3.31秒；`go-regression.log/xml` |
| `run_checks.py independent /out/test_independent.py`（首版6项） | 1 | 3 failed / 3 passed，0.03秒；`independent.log/xml`，三失败即R1–R3 |
| `run_checks.py independent-extended /out/test_independent.py`（增加3项真实边界，未改候选） | 1 | 3 failed / 6 passed，0.03秒；`independent-extended.log/xml`；真实规范JSON 65,536/65,537字节、Unicode字符/registry总限、ID/action/topic边界通过，三原失败仍在 |
| `capture_runtime.py cross-case crosscase-runtime` | 0 | 成功**复现缺陷**而非验收通过：真SDK/本地fs工具+合成HTTP，3个合成请求，CASE_B文件被CASE_A核对标valid；完整wire和结果在`crosscase-runtime.json` |
| `capture_runtime.py off baseline-off` / `off candidate-off` | 各0 | 分别挂基线/候选快照；各2个合成请求。两者还显式设置环境`CHI_DEV_EVIDENCE_SHADOW=shadow`，不经开发装配的核心off路径仍无新工具 |
| `compare_and_wrapper.py` | 0 | 上述两份完整请求body/返回/业务调用一致；包外runner的off、payer shadow、provider/cm shadow拒绝、enforce拒绝共5项通过；`comparison-and-wrapper.json` |
| `bundle_audit.py` | 0 | 独立build/validate/逐项hash/集合检查33文件，隔离`-I -S`导入不借工作区脚本；程序0.232秒，`bundle-audit.json`/`bundle-import.log` |

8个skip的实际原因由独立XML提取：5项Harbor controller overlay未安装，3项当前`/opt/venv`缺Docker SDK；都未记通过，未为本审核安装或加载新依赖。没有扩大重做旧G/H或真实世界链路。off等价证明限定为本次同一合成轨迹的完整body/工具/预算反馈和调用结果，不声称穷尽所有任务。

独立包manifest为`e847a6ae346405c477020d911908a40e3413ec64b32e3e210c2a8bb24f58042e`，entry config为`29423f878784d39c1764062939db28e3d6f72eed0daa71dfe6178889c342d3a8`，与实现者报告一致。新模块在包内，role_runner/dev_patient/tests在包外；独立子进程导入来源确为新包路径。与W包身份不同，只报告变化，不签发B、不复用旧B、不rebind真实账。

### R1 [P1] 文件来源的病例归属丢失，其他case可被标valid

位置：[payer_evidence.py](../scripts/payer_evidence.py#L138)的来源登记、`_case_scope()`（145–156行），以及311行的匹配分支。

触发：已观察`local-fs-read`读取`.../workspaces/CASE_B/payer/record.txt`，其调用参数只有path；随后提交CASE_A核对，引用该文件对应source_id。`_case_scope()`只识别顶层case_id，把这类文件默认为`run`；`_claim()`又放过所有run作用域来源，因此返回`reference_validation=valid`。独立纯模块反例失败后，另走真SDK/原本地工具路径复现：目标为CASE_A，结果excerpt明确为自造`CASE_B`，reference仍valid、semantic未判。没有读取实际患者材料或启动官方世界。

影响：这是来源身份错误，不涉及判定引用文字在临床上是否支持主张；`semantic_assessment=not_performed`不能消除它。已知workspace路径已含可机械判定的case，不能把“无case_id参数”当成“可支持任意case”。报告虽承认参数归属限制，但该限制未满足原spec的错case拒绝契约，不能据有限测试判go已充分成立。

返工要求：从已有路径allowlist/可信结构元数据导出文件case；真正共享公开手册另标shared_public。无法证明归属的临床结果/混合病例列表标不可用于目标case核对，不默认为共享。补文件路径与参数归属两种反例，并保留允许引用共享政策的正例；不加临床语义猜测，不扩文件读取权限。

### R2 [P2] 已观察资源更新没有失效/历史版本语义

位置：[payer_evidence.py](../scripts/payer_evidence.py#L138)逐call登记，及313–318行hash比对；记录没有资源键、generation或superseded状态。

触发：同一CASE_A文件路径在R2观察old文本，R4又观察new文本。之后引用旧source_id，即使附上完全正确的旧hash，仍返回valid。来源hash只能说明引用与那份旧文本一致，不证明没有被本次已观察的新版本替代。该检查只涉及同一路径明确重读后内容改变，不要求判断医疗政策的法定时效或哪条医学规则正确。

影响：spec明确包含可证明版本/状态失效，当前实现并未覆盖；原测试的“错误hash”不是“版本失效”的替代测试。报告承认没有独立版本判断是诚实的限制，但仍不足以满足现行契约、宣称机械失配全部拒绝。

返工要求：为可证明同一资源的重读/变更定义generation和superseded标记，至少不能在无区分情况下把旧版当作当前可用支持。历史引用若需要保留，须在契约/返回中明确历史用途与当前适用未核验；若决定缩减版本能力，须先交用户决定收窄契约，不能由实现者用限制说明替代验收。旧观察和原hash仍保留，不改写历史。

### R3 [P2] 无效核对提前修改目标case，污染后续合法核对

位置：[payer_evidence.py](../scripts/payer_evidence.py#L245)的`self._case_id = case_id`。

触发：首份核对填CASE_B，action为空且claims为空，返回invalid；但在累计到这些错误后仍把CASE_B写进registry。随后合法CASE_A核对被永久返回`case_scope_mismatch`。当前测试只验证首份合法后禁止换case，未覆盖首份无效时应不提交状态。

影响：结构错误没有拦截业务MCP，但已经影响后续核对请求，不能说只拒绝该次请求。它还使模型错误输入能够决定原本应受程序控制的长期case状态。

返工要求：验证失败不提交case状态；优先从可信运行上下文确定目标，或者在全部结构/来源校验通过后才原子绑定，并测试“失败→合法”“合法→跨case”两条路径。不通过清空旧失败记录恢复运行。

### 覆盖、限制与结论层级

- 已独立验证的正向范围：固定字符/hash与真实JSON大小边界、显式case_id不符拒绝、两个registry不共享观察内存、合法引用仍semantic未判；原测试中的同批未观察/自身结果/错误hash/目录排除、建议性缺项/护士路线、fatal/取消以及核对错误后业务MCP继续等均实际重跑通过。
- 原spec的覆盖并未闭合：文件case、可证明资源更新和失败状态原子性为本轮新增的实测缺口。非公开路径/符号链接/提示注入方面，纯模块没有文件/执行入口且原allowlist未改；原新增测试未提供完整端到端恶意路径矩阵，不把静态无入口当作已穷尽验证。
- 包外开发开关通过本地fake runner测试；统一`role_operator`当前runner_env不透传该shadow环境变量，因此不能把仅在宿主设置开关说成已完成统一操作者/真实shadow业务运行。这一可用性边界未执行真实实验，不在本轮自动补接线。
- 实现者报告正确区分自测、语义未判与待审，未写成Codex已验收；原首次取消断言失败日志未逐字保存的缺口仍保留，未补造。本轮首次镜像元数据模板查询因缺失Entrypoint字段退出1，改用安全`index`查询后确认同一镜像ID；没有修改镜像。独立反例首次6项和后续9项的失败日志分别保留，未覆盖为通过。
- 全部合成HTTP来自MockTransport，fake server/工具只处理自造材料，相关usage/费用只是隔离合成数据；不计入真实账。新增真实B/C/患者/评审请求0、真实token未产生、新增三项USD费用均0，official_reward=null。没有Key读取、官方题重跑、真实账操作或新B。

| 层级 | 本轮可写的结论 |
| --- | --- |
| 实现完成 | 实现者已交付候选，有明确缺陷，五步自测不等于需求验收完成 |
| 离线验收通过 | **整个Y未通过，返工R1–R3**；上述独立通过项只保留限定证据意义 |
| 真实运行已验证 | 否；本轮不执行，W既有真实结果保持原范围 |
| 用户验收通过 | 否；由用户决定，不代替用户合并或验收 |

下一步建议：先由用户决定是否交原实现者按R1–R3返工，再固定新候选，由Codex针对差异、独立失败反例和受影响回归复验；不因当前常规测试全绿就开启模型、真实题或付费临床评审。上次通过的实现身份仍为W，Y只登记实际已审候选与未通过结论。

收尾`final-integrity.json`确认候选228/基线224项快照与归档hash不变，工作区实现/测试逐项仍匹配固定候选，三份审核文档165个相对链接可解析。Git HEAD仍为原候选；只追加本报告、REVIEW_STATE和学习账本，均留本地未提交。两份用户既有diff结束比对一致；没有暂存、提交、推送或创建PR。


## DeepSeek返工交付（R1–R3，待Codex复审）

**DeepSeek实现者返工交付，待Codex独立复审。** 原Codex审核结论、证据与“未通过”判断原样保留；本节只记录返工实现、自测和限制，不冒充复审通过。新增真实B/C、患者、评审请求仍为0，未读Key、未调用项目模型API、未启动官方题世界；`official_reward=null`。

### 身份与改动

| 项 | 实际值 |
| --- | --- |
| 被审旧候选 | `33d3e41283ac68d5dd0af283460a17bee11e8949` |
| 返工实现提交 | `c1b123ad856a3e721263a9d1f9bb47510c949c0e` |
| 报告/状态提交 | 紧随其后的本地提交；最终分支HEAD为准 |
| 分支 | `codex/payer-evidence-prototype`（同一未合并分支；未rebase/merge main） |
| 用户改动 | `AGENTS.md`、`COLLABORATION.md` 保留，未暂存/提交；Codex审核文档原意保留，仅追加本节和状态 |

相对旧候选的代码/测试/契约改动：

| 文件 | 改动 |
| --- | --- |
| `scripts/payer_evidence.py` | 来源作用域（case/shared_public/unattributed/conflict）、文件路径分类注入、资源键/generation/superseded、仅全通过后原子绑定case |
| `scripts/go_chi_tools.py` | 从既有workspace/handbook/固定输入allowlist构造分类器；不读正文、不扩权限 |
| `tests/test_payer_evidence.py` | 新增文件错case、路径/参数冲突、共享政策、unattributed、替换失效、相同内容重读、非文件不建版本键、失败→合法case |
| `tests/test_payer_evidence_shadow.py` | 新增真SDK/本地fs工具的文件错case、共享handbook正例、同路径写入后旧引用失效 |
| `design.md`/`spec.md`/`README.md` | 冻结R1–R3语义、理由码与失败状态规则 |

### R1：文件来源病例归属

- **原触发**：`local-fs-read` 参数只有path时被当作run共享来源，`CASE_B` 文件可被 `CASE_A` 核对标valid；Codex纯反例与真SDK/本地工具合成HTTP均复现。
- **修复**：运行时分类器复用既有 `workspace_path`/handbook根/固定公开输入的allowlist结构：
  - `<workspace>/<case>/<role|shared>/...` → `case:<case>`；
  - handbook、instruction、tool reference → `shared_public`；
  - 非文件工具只有参数含结构 `case_id` 才绑定case；
  - 无路径case且无 `case_id` 的临床结果/混合列表 → `unattributed`，引用返回 `source_case_unverifiable`；
  - 路径case与参数case不一致 → `conflict`，返回 `source_case_conflict`。
  不读正文、不按关键词猜病例、不扩大allowlist。
- **自测**：`test_file_source_from_another_case_is_rejected`、`test_file_path_and_argument_case_conflict_is_rejected`、`test_source_without_case_argument_is_unattributed`、`test_shared_public_source_is_allowed_for_target_case`，以及runtime `test_runtime_file_from_other_case_is_rejected`、`test_runtime_shared_handbook_is_valid_support` 全部通过。
- **Codex反例复跑**：`capture_runtime.py cross-case` 现输出 `reference_validation=invalid`、`reasons=["source_case_mismatch"]`，不再把CASE_B文件标valid。

### R2：资源更新后的旧引用失效

- **原触发**：同一文件路径先观察old、后观察new，引用旧source_id并回传正确旧hash仍valid；hash只证明引用与旧文本一致。
- **修复**：仅对 `local-fs-read` 的同一规范化路径建立资源键。后一次内容hash不同→generation加一，旧来源 `current=false`、`superseded_by=<新id>`；旧文本/原hash保留；引用旧来源返回 `source_superseded`，`excerpt`同样拒绝。相同内容重读不失效。非文件结果不建资源键，不做版本推断。本轮不支持“历史引用仍作为当前支持”的模式。
- **自测**：`test_replaced_resource_supersedes_old_source`、`test_identical_reread_does_not_supersede`、`test_non_file_results_are_not_given_version_keys`、`test_runtime_resource_update_supersedes_old_file` 通过；runtime用 `local-fs-write` 改同一文件后，旧来源invalid、新来源valid。
- **限制**：只处理可机械证明的同路径内容变化；不判断医疗政策法定时效，不把不同工具/不同路径的文本当同一资源。同一路径不同offset窗口也会被后一次观察取代，这是保守取舍。

### R3：无效核对不污染case状态

- **原触发**：首份invalid核对（CASE_B、空action/claims）仍写入 `_case_id`，随后合法CASE_A被 `case_scope_mismatch` 拒绝。
- **修复**：删除验证前的case赋值；只有整份核对的结构、来源、版本、范围、claim全部通过（`reasons`为空）才原子绑定首次合法case。invalid不提交长期状态；已绑定后另一case仍拒绝；不清空旧失败记录。
- **自测**：`test_invalid_checklist_does_not_bind_case`（CASE_B invalid → CASE_A valid）、`test_target_case_is_frozen_after_first_structural_check`（A valid → B rejected）通过。
- **限制**：本轮没有从world/operator取得独立“可信目标case”，采用契约允许的“全部通过后原子绑定”方案；它防止错误输入污染，但不能证明清单里的目标case就是任务真实case，仍依赖模型填写与后续来源/业务检查。

### 实际Docker执行与结果

环境与旧候选一致：`chi-agent-a-control:latest`（ID `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`）、Python 3.12.15、vendor `4444a07fa68a4f1623f841a292a54e284fc8e7f7`、卷 `chi-h-root-model-deps-20261027-v1`/`chi-k-pdf-deps-20261027-v1`；全部禁网、只读根、无Key、无world、无Docker socket，未安装/升级依赖。

| 检查 | 命令/目标 | 退出码 | 结果 |
| --- | --- | --- | --- |
| payer纯原型+shadow | `pytest -q tests/test_payer_evidence.py tests/test_payer_evidence_shadow.py` | 0 | **41 passed**（1.59秒） |
| Codex独立反例 | `pytest -q runs/payer-evidence-prototype-codex-review-20261031-01/test_independent.py` | 0 | **9 passed**（0.03秒；旧候选为3 failed/3或6 passed） |
| 真SDK/本地fs跨case复跑 | `capture_runtime.py cross-case rerun-crosscase` | 0 | 3合成请求；check `invalid/source_case_mismatch` |
| Go CHI回归 | `pytest -q tests/test_go_chi_*.py` | 0 | **100 passed、8 skipped、48 subtests**（2.41秒） |
| 独立构包 | `scripts/go_chi_bundle.py build` | 0 | **33文件**，含`scripts/payer_evidence.py`，排除`role_runner`/tests；`manifest_sha256=7a54698c49b0c4f85bf698a60089a412e1725da2ef1abe88ce67efcd2aa6cd1c` |
| 隔离导入 | 从新包scripts路径导入`go_chi_tools,payer_evidence` | 0 | 来源为`/bundle/scripts/payer_evidence.py` |

8个skip仍为5项Harbor overlay未安装、3项controller venv缺Docker SDK，未记通过，未安装依赖。off等价、同批未观察、fatal/取消、核对错误不拦截业务MCP均在41项中重跑通过。包身份相对旧候选 `e847a6ae...` 变为 `7a54698c...`，只报告变化，未签发/复用B。

证据目录（忽略、不上传）：`chi-agent/runs/payer-evidence-prototype-r1r3-20261031-01/`，含 `payer-tests.log`、`independent-tests.log`、`go-chi-regression.log`、`bundle-build.log`、`rerun-crosscase.json`、`bundle/`。

### 本轮失败与修正

1. 返工首版 `default_source_scope` 只接受2个参数，而注册器按 `(tool, arguments, result)` 调用，导致9个既有正例和新增用例共13项失败（`TypeError`/unattributed）。修正为接受可选`result`后，纯原型29项通过。该错误来自本次返工，未用放宽断言掩盖。
2. 旧测试 `test_source_without_case_argument_is_run_scoped` 断言“无case参数的工具结果可作为任意case支持”，与R1明确冲突；按新契约改为 `..._is_unattributed` 并断言 `source_case_unverifiable`。这是有依据的契约修正，不是为让错误行为通过。
3. Codex原独立反例在旧候选为3 failed（扩展6 passed/3 failed）；本次未覆盖其原始日志，修正后同一`test_independent.py` 9项全过。原日志仍保留在Codex目录，未改写。
4. 其余无真实请求重试、账目变化或旧证据覆盖；`runs/payer-evidence-prototype-codex-review-20261031-01/` 未修改。

### 结论层级与未验证项

| 层级 | 本轮状态 |
| --- | --- |
| 实现完成 | R1–R3返工已实现并本地固定候选 |
| 离线验收通过 | 仅实现者自测；**待Codex复审**，不等于通过 |
| 真实运行已验证 | 否；真实请求0 |
| 用户验收通过 | 否；由用户/Codex后续决定 |

未验证：模型能否稳定使用字符索引；可信目标case仍来自核对表（无world/operator独立目标）；同一路径不同读取窗口的版本语义为保守近似；MCP混合列表若带单一`case_id`仍无法识别混合；真实payer行为/终态收益、临床正确性、官方评分均未验证。上次通过实现身份仍为W `ad2569937e0afe649807669c70f86da97c708e86`，本返工不改变它。
