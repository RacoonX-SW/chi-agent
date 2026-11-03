# 架构与代码评审（2026-11-02）

来源说明：第1–11节保留DeepSeek在未合并分支`codex/ab-capability-toggle`、提交`0ca0d45`记录的架构分析；模块数量/行数及其优先级是该报告的原口径，不是Codex重新全仓验收的结果。第12节起为Codex本轮源码初核、重构建议及负责人提案。当前仅写文档，不执行修复、重构或模型调用。

范围：`chi-agent/scripts` 61 个模块 / 约 2.1 万行，加测试与证据链。只读分析，未改实现。
结论：已踩的坑（profile 漂移、`index` 字段、workspace 路径、guidance digest、8192 六处、包外 import）根因相同——**同一事实重复表达，缺少单一来源**。

## 1. 配置与常量分散（高影响）

| 事实 | 出现位置 |
| --- | --- |
| 主输出 8192 | `go_chi_entry.py:31`、`go_chi_guard.py:89/246`、`go_chi_journal.py:725/974`、`go_chi_inspect.py:65`、`go_chi_auxiliary.py:40/73`、`go_chi_context.py:19`、`go_chi_runtime.py:231` |
| 请求上限 50/6/2 | guard、journal、entry 各自计算 |
| 时间策略 | `go_chi_policy.py` + 手抄的 `profiles/go-chi-entry.json` |
| 角色/端口/白名单 | `go_chi_mcp.py`、`go_chi_delivery.py`、`role_operator.py` 各维护 |

建议：`limits.py` 单一来源；profile 改为生成或只校验子集。影响 identity：是。

## 2. 路径与白名单策略重复

`_check_components` 在 `evaluation_bundle.py:81` 与 `go_chi_bundle.py:105` 各一份；`workspace_path` 在 `go_chi_resources.py:16`、`go_chi_tools.py:94/115`、`live_development.py:1729` 各一版；禁止目录集合在多处复制。
建议：`paths.py` 统一。影响 identity：是。

## 3. 错误码坍缩

`go_chi_guard.py:173` 把 `ContractFailure` 一律映射为 `chi_tool_batch_invalid`；真实排查只能靠重放 wire evidence。
建议：对外码不变，diagnostic 增加 `cause` 子字段（如 `unknown_field:index`）。影响 identity：是（证据 schema）。

## 4. Journal 三合一

`go_chi_journal.py` 1090 行：持久化 + 状态合法性 + CLI。`_validate` 数百行 if，新增字段需同时改 journal/inspect/entry。
建议：状态校验抽成纯函数模块。赛后做。

## 5. 双轨遗留代码

`live_development.py`（2718 行）、`model_runner_adapter.py`（1205 行）、`run_baseline.py`、`c_run_control.py` 属旧开发路径；Go CHI 只用其中很小部分。导致打包边界难判断（`run_baseline` 潜在 ImportError）。
建议：赛后按“进包 / 开发工具 / 历史存档”分目录；赛前只加静态 import 检查测试。

## 6. 测试策略

既有问题：`patch.object(entry, "_identity")` 掩盖真实配置漂移；超时断言曾写死 60/360。
建议：配置等价性测试、guard/contract 表驱动用例、评审检查项“是否打桩核心校验”。无 identity 影响。

## 7. 资源 manifest 手工维护

每题 11 项 manifest 手写，易漏 `visibility`（本轮 t027/t030 各写错一次）。
建议：`make_role_manifest.py` 自动扫描/分类/哈希并跑 preflight。无 identity 影响。

## 8. 可观测性

每次分析都临时写 Python 读 journal。建议加只读 `summary --run`（进包，影响 identity）。

## 9. 身份与策略耦合

`TIME_POLICY` 进入 identity，调超时也要新 release + 新 B + 新 state（本轮已发生）。
建议：把“行为身份”（代码/提示/工具/上限）与“运行策略”（超时/窗口）分开版本化。架构级取舍，赛后评估。

## 10. 不建议现在做

大文件拆分、全面类型化、重写 guard/journal。它们是失败语义的核心，重写等于丢弃已验证行为。

## 11. 优先级

- 赛前（有 identity 影响）：`limits.py`、`paths.py`、诊断 `cause`。
- 赛前（无 identity 影响）：manifest 生成器、静态 import 检查、表驱动契约测试。
- 赛后：journal 拆分、双轨分目录、身份/策略解耦。

## 12. Codex结论：需要分阶段整理，暂不全面搬目录

当前乱点不仅是文件多：正式运行、开发调度、历史入口和被复用的兼容函数共处`scripts/`；发布边界依赖`go_chi_bundle.PACKAGE_FILES`；参数在配置/执行/守卫/审计中重复；错误的安全分类和具体定位信息没有分层。它们值得治理，但大规模路径迁移会同时影响导入、包manifest、身份、脚本/挂载和历史复现。

**建议：现在补边界与检查，随后做小范围可靠性修正；物理分层等功能稳定后单独评估，journal拆分和身份/策略解耦默认延后。** 这调整了第11节“赛前统一paths”的优先级，不直接把所有建议变成实施指令。当前用户明确要求先讨论、写结论，截断项留待文档完成后讨论；下列负责人均为建议，不表示已派发代码工作。

### 初步模块导航

| 职责 | 主要入口/模块 | 边界 |
| --- | --- | --- |
| 参赛执行 | `go_chi_entry`、`go_chi_runtime`、`go_chi_harness` | 接收外部输入、运行Agent；实际进包集合以allowlist为准 |
| 执行约束与证据 | `go_chi_guard`、`go_chi_contract`、`go_chi_journal`、`go_chi_evidence`、`request_budget` | 发送前校验、核算、工具/历史和失败证据，不能为整理代码放宽 |
| 自有Agent能力 | `go_chi_state`、`go_chi_guidance`、`go_chi_search`、`go_chi_context`、`go_chi_tools` | 任务状态、指导、资料与本地工具；机械检查与语义判断分开 |
| 工具及资源 | `go_chi_mcp`、`go_chi_resources`、`patient_identity_binding`、`payer_evidence`、`pdf_resource_reader` | 角色/路径/实体/引用及读取边界 |
| 构包与供给 | `go_chi_bundle`、`go_chi_release`、`go_chi_delivery` | 内层包、外层交付与供给检查，三者不能混称同一发布边界 |
| 开发操作者/实验 | `role_operator`、`role_runner`、`experiment_manifest`、`experiment_summary`、`role_resource_preflight` | 开发运行/资源/汇总；不能自动进入参赛包 |
| 开发环境模拟 | `dev_patient_*`、`role_cm_capture` | 本地CM患者替代及捕获，与官方模拟器分开 |
| 旧入口与复用兼容 | `live_development`、`model_runner_adapter`、`run_baseline`、`b_provider_transport`等 | 有的模块或局部函数仍被调用，不能整体标废弃后删除 |

导航只列主要入口，不冒充逐文件依赖图。例如当前`role_operator`仍从`live_development`导入捕获函数，Go runtime仍从`model_runner_adapter`复用SDK兼容函数，guard复用`b_provider_transport`的usage检查。DeepSeek的M1任务应补齐全部自有模块的实际成员和调用关系。

### 三层整理顺序

1. **先做边界可见性与回归约束**：模块/调用/进包地图，源码内导入清单，真实配置一致性检查，资源manifest生成工具。此阶段不移动现有运行文件、不改上限、不改历史账。
2. **经讨论后做有界修正**：修包依赖闭包；按用途明确常量来源；安全增加结构化诊断。每个PR只处理一种语义，固定候选和独立复验，不把截断新功能与目录重组一起提交。
3. **功能稳定后的单独重构**：按参赛runtime、包外开发工具、兼容/历史参考分层；必要时先抽取仍在使用的小函数。完整journal拆分、身份与策略解耦、全面类型化/框架替换延后；不把这些设为当前讨论或截断设计的前置。

物理分层的目标是可分发边界清楚、依赖单向、入口稳定，不以目录数量或文件长度作为验收结果。迁移前须有全调用清单、旧入口兼容/退出计划、manifest与挂载映射、历史复现说明、差异回归和身份处理方案；未过这些关口不搬目录。

## 13. 问题分级、初核事实和建议负责人

高优先表示先核实风险，不等于已认定故障或违规。Codex本轮仅阅读相关源码/记录，未运行故障复现、测试或真实账审计。后续工作包与验收标准只维护在[收尾设计第15节](../openspec/changes/project-completion/design.md#15-可靠性治理与分阶段重构)，勾选只在对应tasks，实际许可/状态只在REVIEW_STATE。

| 项目 | 重要性和当前判断 | 建议负责人/动作 |
| --- | --- | --- |
| 未结算后改用新state | 高；未合并批次报告同时记旧pending、使用新state和“无换账根”，存在口径冲突；尚未核实根目录/授权/准入关系 | Codex先审计事实与语义；有确认缺陷后另议最小修复，不先动账 |
| 输出截断/续写 | 高；源码明确主响应length停止，属现行保护，续写是新能力；不能视为已经确定的bug修法 | Codex主导与用户讨论，未选方案、不实现新purpose |
| 包内局部导入包外模块 | 中高；`model_runner_adapter._budget_check()`局部导入`run_baseline.evaluate_budget`，后者不在Go包allowlist；Go当前主链不走该函数，未做隔离触发复现 | Codex核对闭包并提出小范围修正；不把整个旧开发入口塞进包补洞 |
| 输出/请求配置重复 | 高影响风险；多处重复已见，尚未证明当前数值全部有漂移 | Codex划定用途/硬边界并核对一致性；后续核心修正由Codex负责 |
| t027签核/P2P | 高影响解释问题；公开服务允许P2P不签核，但pending阻止finalize、completed可导向最终决定 | Codex核对原实际P2P过程/公开任务要求；暂不新增题目专用强制规则 |
| 错误cause丢失 | 中；guard将不同ContractFailure归为统一批次错误，定位依赖原wire | DeepSeek按冻结诊断契约实施，Codex复审schema/秘密与旧记录兼容 |
| manifest手工易漏 | 中；报告已有漏visibility案例，生成流程可以防止重复 | DeepSeek做显式分类/校验工具及反例，Codex复审外发/角色边界 |
| import/配置/契约检查薄弱 | 中高；只导入模块不足以覆盖局部导入，打桩核心身份可能掩盖问题 | DeepSeek补独立检查，Codex核对是否真覆盖隔离包/坏配置和不可达代码 |
| 模块地图、状态及报告整理 | 中；影响接手与验收判断，主线状态有旧后续步骤，未合并记录另有新结果 | DeepSeek补完整地图/来源索引，保留历史；本轮先更正主线讨论入口 |
| 路径全面统一、journal拆分、身份解耦 | 结构债务，当前不因“乱”直接升级为紧急修复 | 暂缓，功能稳定后另开规格；Codex审核边界、再分配实现者 |

DeepSeek负责实现不意味着其任务不重要；划分依据是是否触及核算、工具历史、业务解释及安全边界，以及是否已有可冻结的局部验收。实现与独立复审保留；同一工作区仍只有一个写入者。

2026-11-02后续C3已在隔离包实际触发上述局部导入失败，并以纯函数提取补齐闭包；Go主循环并未因此被证明发生过故障。两种导出包、函数行为/签名及身份链的独立证据见[C1/C3阶段报告](../reviews/c1-c3-admission-package-review.md)。表中是初核时判断，其余项不随C3完成而关闭。

C4随后按[用途边界契约](../openspec/changes/project-completion/policy-boundaries.md)完成不改数值的一致性核对及独立漂移反例，证据见[C4报告](../reviews/c4-policy-consistency-review.md)。独立安全检查保留，未做常量归并或扩大预算；外部编排计时仍不在动态通过范围。

## 14. 两项必须保留的不确定性

### 未结算请求与新state

2026-11-02后续只读核查已完成，事实、来源和结论见[C1/C3阶段报告](../reviews/c1-c3-admission-package-review.md)：确认旧pending仍在时切换了state和evaluation；所选证据未闭合未知处置与特定后继授权，不能据此恢复真实准入。下面保留初核问题及原来源，不改原账或未合并报告。

[未合并批次报告来源](https://github.com/xsw932187210-cell/chi-agent/blob/0ca0d45/chi-agent/reviews/real-external-batch-a-review.md)第14节记：`payer-010` transport错误、旧state仍pending，后用新state；同节称“无换账根”。需要比较实际evaluation/root/identity、用户决定、后继准入和全局累计，不能仅凭这些文字判定已经违规，也不能认定未结算没有影响。

短时间Console导出没有session匹配，不足以单独证明请求未到服务端。应区分连接前明确失败、请求派发后未知、Console缺记录和已验证结算/显式留档。不得删除pending、补0费用、重发旧请求或只更换root来修“报告问题”。若核实用户明确批准独立evaluation或留档继续，也要写出授权与来源关联，不伪造原请求settled。

### t027的合法路径

2026-11-03后续[C5核查](../reviews/c5-p2p-public-path-review.md)已关联旧工具结果和导出：两次均先record_outcome取得completed/uphold，再get_summary推荐deny，以overridden=false完成denied；原MD仍p2p_review/unsigned不等于跳过P2P。但get_context无活动会话、目标session为空，模型note声称讨论已举行缺少会话支持。故机械依赖链已核对，交流/业务充分性未验证，原21/22与false不改。以下保留初核时未决问题及来源。

本轮已读固定vendor `services/review.py::submit_md_case_decision` 与 `services/determination.py::_resolve_source_state/finalize_determination`：P2P决策可不签核，待完成P2P会阻止finalize，完成的P2P结果可导向最终决定。原运行是否走过相应完成链、是否有override、最终依据是否一致仍未独立核实。

因此既不能从“两个工具都允许调用”推出任意组合合法，也不能从一个false推出所有P2P都必须签核。此前报告的“仅期望选择差异”是待核对解释，原21/22结果保留，不据此修改官方检查或给Agent注入隐藏期望。

## 15. 截断项的待讨论材料

用户要求完成本次文档后再讨论；这里不冻结方案、不授权实现或真实请求。下一次先核对一次原length响应的reasoning/content/tool_calls构成、预算及usage是否已结算，再讨论：保持停止并调整输出预算；仅普通文字的有界续写；工具调用截断的安全拒绝/重新生成策略。残缺tool_calls/JSON不得拼接后执行。

若最终选择续写，还须明确同attempt/账目、历史关联、每次发送前准入、总请求与次数、取消/超时/未知处理、完成判据及禁止重复旧工具。不能把“最多2次、新purpose”当成已经由用户决定的方案，也不能只加一条“继续”提示就宣称可恢复。

后续用户要求同时考虑输入增长，并认可借鉴Codex/Harness的分层视图、同步摘要与检查点原则。详细方案/来源/实施关口集中在[输入治理设计](../openspec/changes/project-completion/input-context.md)；此处保留输出选项的未决状态，不把输入原则的认可扩大成输出续写或真实请求授权。

本轮补读当前profile/guard：主循环上限8192、确认32768、coding-B1024；guard收到可信usage先留证/结算，再校验响应，主响应length报chi_output_truncated，确认length交本地确认逻辑处理但不代表绑定成功。历史[独立开发评审](../reviews/deepseek-development-review.md)出现8192个completion全部为reasoning、content为空的length；之后该评审用途改用32768，下一笔完成。这不是当前主循环的同条件对照，不能证明仅扩大上限就能解决它的截断。[真实批次报告](../reviews/real-external-batch-a-review.md#31-round-17-的提供方记录2026-11-01-补核)也记provider输出8192且reasoning8192，但其原响应未收全，不能仅凭用量推断finish_reason。

因此输出侧待讨论的首选顺序为：先按推理/文字/工具参数分类并核实耗尽的预算，再评估主循环更高输出上限（32768只是候选，须同步输入预留、guard/journal/profile及身份/时间验证）；仍截断时是否允许纯文字的有限续写另定。工具批次截断保持整批不执行，不执行看似完整的前半批；任何重生成都会新增请求并改变零自动重试规则，需显式限定已知结算、零工具派发、同账总限额和次数。传输/用量未知保持停止，不能套用已知length恢复。上述选择尚未冻结或实现。

后续用户澄清DeepSeek原建议为带purpose/预算/工具合法性校验的受控接续，并要求写入实施方案。新首版以[输出恢复实施契约](../openspec/changes/project-completion/output-recovery.md)为准：保留现有单次上限，不接流式；无工具时接续合法上下文，含工具时整批零执行并重新生成；新对话由Sol/high规划审核和唯一Terra/high子代理实现。前段“优先提高上限”保留为讨论过程，不再作为首版默认；实现及真实协议证据尚未产生。

## 16. DeepSeek 可靠性工具候选：Codex 独立核对

2026-11-02。固定候选 [`f4162d7`](https://github.com/xsw932187210-cell/chi-agent/tree/f4162d74efeb61da5832364ad99d88a9d231f37b)；基线 `fc7d678`。差异为7个工具/测试/文档文件，未改runtime。远端核对时PR39为既有文档规划PR；DeepSeek的`codex/reliability-boundaries`已推送但未查到对应open PR。结论：暂缓将该实现候选合入main，以下两项交DeepSeek修复后固定新候选再复审。不修改当前代码。作者交付及其自测来源见[固定版本交付报告](https://github.com/xsw932187210-cell/chi-agent/blob/f4162d74efeb61da5832364ad99d88a9d231f37b/chi-agent/reviews/reliability-boundaries-review.md)，不将作者记录写成Codex执行结果。

核对环境：通过`git archive f4162d7 chi-agent`在`/tmp/chi-reliability-review-bxJTT1`取得不可变源码快照；容器`chi-agent-dev:latest`，实际Python3.12.15，`--network none --read-only --tmpfs /tmp`，只读挂载该快照及既有model/pdf依赖卷；未挂Key、world、真实账目。定向命令`/opt/venv/bin/python -m unittest tests.test_import_inventory tests.test_make_role_manifest tests.test_config_limits_consistency`：24 tests，OK，退出0。未重跑全量；作者报告的2个anthropic环境错误/11 skip仍为作者证据，不改为本轮全绿。

### R1：provider正常输入选错world（P1，阻断M2）

[`make_role_manifest.py`第120行](https://github.com/xsw932187210-cell/chi-agent/blob/f4162d74efeb61da5832364ad99d88a9d231f37b/chi-agent/scripts/make_role_manifest.py#L120)无论provider/payer都使用`world_paths[0]`构造主world，而PA_WORLDS将payer排在首位。合成一个合法provider任务，fixture manifest的world_id为healthverse-pa-v2-provider，生成结果仍指定healthverse-pa-v2-payer；调用原`role_resource_preflight.validate`得到`world_invalid`。这不是当前已有运行代码的故障，影响新增三角色manifest工具的正常provider路径。

Docker复现：复用`tests.test_make_role_manifest.ManifestTests`临时fixture，将payer任务复制为`prior_auth_provider/tasks/pa_provider_synthetic`，移除request目录，将fixture manifest改为provider world_id；调用build_manifest与带原preflight的write_manifest。实际输出：

```
python=3.12.15
provider_selected_world=prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json
provider_preflight=REFUSED:world_invalid
```

DeepSeek修复与验收：按实际任务fixture/公开资源契约选择并校验主world，保留原要求的完整world-only清单，不改原preflight放行。补provider/payer/cm三个正常路径，补任务world_id与所选world不匹配的拒绝反例；三个角色均须经过原preflight，不能只断言生成JSON的字段。

### R2：最终落盘不是原子的不可覆盖（P2，阻断M2契约）

[`write_manifest()`第156–168行](https://github.com/xsw932187210-cell/chi-agent/blob/f4162d74efeb61da5832364ad99d88a9d231f37b/chi-agent/scripts/make_role_manifest.py#L156)先检查`output.exists()`，最终使用`os.replace(temp, output)`。mkstemp只保护临时文件，不能保护最终路径；检查后其他写入者创建的最终文件会被覆盖。实现/交付说明中的O_EXCL不可覆盖承诺未覆盖实际最终写入。

Docker确定性复现：输出最初不存在；使用preflight回调先运行原validate，然后向最终路径写入`created-by-another-writer`；回调返回后write_manifest成功并覆盖该文件。实际`concurrent_output_overwritten=True`。仅使用容器/tmp合成文件，没有覆盖项目或真实manifest。

DeepSeek修复与验收：最终提交必须具有原子不覆盖语义，不能只加第二次exists检查；已有/竞争创建的文件与链接保持原字节，失败清理临时文件，预检失败不留下最终产物。保留确定性、大小/hash、权限分类和原preflight。补竞争创建、正常写入、预检失败及写失败测试；不扩大到runtime/账或目录迁移。

修复完成后重跑新增反例及上述24项相关回归，说明实际Python/容器/退出码和新候选SHA，再独立核对。暂不要求为这两项运行真实模型或重新收费B/C；不得顺带修C1/C2/C3/C4或pending。M1/M3已跑定向检查不等于整包验收通过，既有run_baseline闭包缺口及未锁依赖仍单列。
