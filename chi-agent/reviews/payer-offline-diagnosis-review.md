# X：payer失败离线诊断与后续规格

日期：2026-10-31（Asia/Shanghai）。本轮只审已有材料、解释失败与提出方案；新增模型请求0、世界重跑0、付费临床评审0、official_reward=null。没有实现候选或新的业务通过结论。范围见[X设计](../openspec/changes/payer-offline-diagnosis/design.md)，原运行及全部费用只见[W报告](unified-role-cm-lifecycle-review.md)。

## 基线、证据与执行

GitHub确认[PR27](https://github.com/xsw932187210-cell/chi-agent/pull/27)已由用户合并，fetch后的origin/main为`b8a5c411551fe57f1c33b4c6db1011d1f8f957d6`；从其建立`codex/payer-offline-diagnosis`。两个既有用户文档改动AGENTS.md/COLLABORATION.md原样保留、排除提交。纯分析/规格由主代理完成，无实现子代理、生产源码/vendor/依赖或运行命令修改；README无需改动。W已通过实现的身份和范围仍由W报告负责，本轮文档提交不取代其身份。

唯一样本为`w-go-c-payer-20261031-001` / `pa_t011_t011_o003_p01_intake_payer`，已见失败开发材料，不能称盲测或泛化验证。先冻结原文件size/SHA256，再解析原请求/响应/tool evidence、公开输入和Agent实际收到的手册。没有新读expectations、solution、persona或judge/rubric内容来推导应做的动作；原判分文件仅纳入字节保全。原false项目名与公开verifier源码用于解释检查覆盖，不作为临床规则。

解析与检查全部在禁网、只读根、无Key的Python3.12 Docker内，复用controller镜像`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，原SDK卷`chi-h-root-model-deps-20261027-v1`与PDF卷`chi-k-pdf-deps-20261027-v1`。原公开PDF reader为锁定pypdf6.20.1，vendor固定`4444a07fa68a4f1623f841a292a54e284fc8e7f7`。原账/包/vendor/素材挂只读，只有X派生目录可写；无安装/下载/依赖升级、Docker socket、world启动或Key读取。

本地忽略目录`runs/payer-offline-diagnosis-root/`保存全部分析版本、失败脚本与派生材料，不上传。主要产物：

| 本地产物 | 用途 |
| --- | --- |
| `analysis-02/evidence/baseline.json` | 2466项原文件size/hash、原账、runtime/SDK/PDF身份与读取边界 |
| `analysis-02/evidence/public-pdf-index.json` | 四份V公开PDF与W实际投影逐字一致，逐页索引 |
| `analysis-02/derived/timeline.json`、`observation-index.json` | 26请求/46工具动作、call_id、原wire/tool hash、首次携带轮次 |
| `analysis-02/derived/observations/`、`public/` | Agent实际收到的完整工具文本、公开PDF页/行；非新增world资源 |
| `analysis-02/evidence/derived-check.json` | 派生hash/先后关系复核、两个自造verifier特征检查 |
| `analysis-02/evidence/final-integrity.json` | 结束时原文件/原账/历史链及零新增请求复核 |

执行脚本位于同目录`operator-audit/`，`extract_evidence.py`用原`verify/verify_tool`逐项对齐sealed wire与tool记录，并用原`GoJournal._validate/_audit_runs`、`inspect_history`审计来源迁移/留档/claim/seal链。命令复用`docker run --rm --pull=never --network none --read-only --tmpfs /tmp`，controller的`/opt/a-venv/bin/python`执行脚本；原目录挂`/original:ro`，W独立包挂`/package:ro`，仅派生目录挂`/out:rw`，SDK/PDF卷只读。无新SDK请求，未从旧prompt的历史文字执行任何操作。

## 输入是否丢失

四份原公开PDF均为2页，锁定reader提取长度依次为2609、2126、1676、1888字符；与V固定公开源和W实际`incoming_request`投影hash一致。R5读前两份、R6读后两份，到R7四份均已完整携入请求。缺项相关段落确在实际工具响应和下一请求中，不是仅凭文件存在或最终总结推测“读过”。R8读取的完整政策也在R9请求内，实际观察hash一致，未发现本地提取截断；没有证据能证明模型在语义上充分利用了所有文本。

提取首版因断言每份tool evidence都有`body_utf8`而停止；检查发现25/46份工具记录按原安全序列化规则省略正文，标记`unparseable_escaped_body`，保留`raw_sha256`。MCP前缀加JSON或含反斜线文本不能由该脱敏器当单一JSON安全重写，但原request wire仍完整。第二版按每个call_id逐一核对**wire实际工具文本hash＝journal.result_sha256＝tool evidence.raw_sha256**，有正文者另逐字比较。25份全部对齐。此处是离线脚本错误假设，不能记成业务输入丢失或证据损坏，更未修改原脱敏/证据实现。首版脚本和部分派生输出保留。

派生检查首版把已知criterion_id简写当成原字段而StopIteration；读取原字段后修正为完整ID再检查，原首版脚本保留。结束复核首次在链接检查发现容器未挂载项目父目录的COLLABORATION.md，补该文件只读挂载后原脚本通过；不是仓库链接失效。三次失败均为离线分析/检查失败，无模型/世界重试、未知放行或原证据覆盖。原分析提取未单独保存精确耗时，记为未记录；末次复核脚本耗时1.749秒，不用Docker工具壁钟冒充整个阶段用时。新增余额扣费、价目价值、套餐消耗均为0 USD，不修改旧账或补齐旧未知费用。

## 观察、主张与动作的时间线

下表只记录公开材料/工具与已暴露的模型文字、参数和结果，不从未暴露的内部推理编造思路。详细临床原文、人员标识和具体隐藏期望不上传。

| 轮次 | 已核对动作/观察 | 可支持的结论 |
| --- | --- | --- |
| R1–4 | 任务、工具参考、payer流程/入件规范、目标结构数据与文件列表 | 角色及目标明确；入件完整与临床充分是不同判断 |
| R5–7 | 四PDF完整返回；临床审查规范随后读入 | 相关缺项不是未供应/未读取 |
| R8–10 | 医疗政策、更新公告与分流规则均进入实际观察；填写入件字段 | 模型有政策上下文；公告未提供该项新的必需条件，不能拿公告凭空补规则 |
| R11 | `confirm_decisions(request_complete=true)` | 入件规则主要以critical字段界定complete；不能仅凭临床缺项就断定这是首次错误 |
| R12–17 | 分流至nurse、读取review数据和目录 | 没有已执行的MD决定；目录列表不等于读取其下所有政策 |
| R18 | `call_00_m511ff301bg6ohi1t77jgtho`保存7项met，包含自述文档充分性 | 首次明确可定位的材料范围/签署主张过度扩张；同时明确承认缺项并解释为建议性，不是没看见 |
| R19 | `call_00_g53uqhw0xkh3vonyeibdbpo2`提交approve护士建议 | 官方service每case仅允许一份、不能修改，成为本次相关路径首次不可修改的建议；不把更早写字段称为完全可逆承诺 |
| R20–21 | 汇总后`call_00_jq5mvn4crv38v63i0dfem6ij`批准finalize | “零documentation_gaps”来自已存met计数，不是独立核验原件；后者持久化决定/状态 |
| R22–26 | 批准信/通知、送达、总结、claim_done与最终回复 | 后续复制同一判断；不是新证据，原不符结果保留 |

## 能确认什么，不能确认什么

1. **材料主张越界可以确认。** R18文档充分性说明把有限叙述扩大为更完整的家系材料，并把请求表描述成已签署；实际观察只支持较窄的叙述，文本中请求表签名栏仍是占位线。后者只能说实际观察不足以确认签署，未作图像笔迹鉴定，不推断法律效力。它们支持“主张要逐项绑定来源”的改进，但不能证明这些主张单独造成终态不符。
2. **“缺咨询就必须挂起”不能从已观察规则证明。** 模型实际读到的政策Coverage Rationale将该项写为建议性；临床审查手册§4允许护士在全部适用条件明确满足时批准，§7–8才按确需证据的缺失/不清楚处理。已读§8服务表没有该服务的专门清单。记录缺项是真实观察，但本轮未取得独立条款将它升级为必需条件，也不能把建议变成无关紧要的保证。材料、适用规则与潜在其他条件的关系保留未决。
3. **不是四个独立临床错误已被证明。** `documentation_gaps=0`是固定`DeterminationService.get_summary()`把存储review中的not_met+unclear相加，R18全met自然得到0。工具接受参数/最终汇总/信件审计成功只能证明程序状态链成立，不为模型解释背书。原公开instruction概括含MD阶段，而细化流程允许符合条件的护士批准；此冲突及具体任务的必经阶段不能靠存在性false自动消解。
4. **首次偏离与根因分别记录。** 当前最早可直接证明的事实依据越界定位R18；不可修改建议在R19、finalize在R21。没有依据把R11入件complete认定为本题首因，也没有证明移除越界文字必然改变决定。终态不符的充分因果解释仍未完成，不能声称已找到唯一根因或已修复payer。

来源锚点均在原实际观察：临床标准`call_2eb2337768874b1f8279f7d0`（R7返回/R8观察），政策`call_74eaf07d926e4cb989db76ce`（R8/R9），更新公告`call_c7184fc2bfcc4a01ae4d69bc`（R9/R10），入件规范`call_7236071827494c3989953cfe`（R4/R5）；四PDFcall_id和页/行索引只保存在本地。固定实现依据：[review.py](../vendor/chi-bench/src/chi_bench/services/review.py)的`save_criteria_evaluation/submit_nurse_case_recommendation`、[determination.py](../vendor/chi-bench/src/chi_bench/services/determination.py)的`get_summary/finalize_determination`；vendor不上传，链接仅用于本地源码导航。

公开要求与证据的收束矩阵：

| 判断 | 当时可用来源/要求 | 模型主张与动作 | 反证与保留项 |
| --- | --- | --- | --- |
| 入件complete | 结构化入件数据、公开请求表；入件规范critical字段要求 | R11确认complete | 临床资料缺项不自动等于critical字段缺失；结构日期与PDF日期有差别，未确认优先级，不将其断言为首因 |
| 材料充分/签署 | 四PDF至R7均可用；事实不得超出来源 | R18材料充分性描述及全部met | 签名占位与有限叙述不足以支持所述充分程度；不作临床资格或签名效力裁决 |
| 建议性缺项的效力 | R9已观察政策、R8已观察审查标准的必需条件/不清楚处理 | R18–19把已注意的缺项解释为建议项，继续approve | 存在直接建议性条款；未证明另有适用必需条款，不能靠原期望补成必须挂起 |
| 是否必须MD | instruction概括全流程；已读手册有护士批准权限及MD升级条件 | R19走护士批准、没有MD决定 | 是否存在未清楚满足的适用条件仍需依据；存在性false不能代替这项判断 |
| 零缺项/批准 | R20汇总、原service计数及建议来源契约 | R21 finalize，后续信件和总结重复依据 | 汇总从模型填写结果派生，非独立验真；原终态/信件检查不符继续成立 |

## 原四项false的适用性

原22 true / 4 false / 11 not_applicable不变，不重判、不手改NA，不调用WorkspaceJudge/verify_task或reward聚合。

| 原false | 固定源码实际在检查什么 | 本轮解释边界 |
| --- | --- | --- |
| `md.decision_exists` | `MdReviewVerifier.verify()`检查目标case有无MD决定；contract_v3仍执行，只有特定provider→payer非submit路径整段NA | 目标无MD决定的事实成立，不能单凭此认定所有护士批准都违规 |
| `md.audit` | 同一verifier检查目标case是否有`submit_case_decision` audit | 对应MD动作缺失的存在性检查；不是审核已提交护士建议的临床理由 |
| `outcome.target_status` | `OutcomeVerifier.verify()`直接比较原expectations与目标实际status | 原终态不符成立；比较本身不解释该选哪条公开规则 |
| `outcome.letter_types` | 期望信件类型集合是否为实际类型集合的子集 | 原类型不符成立，不评价信件内容/医学正确性，也不能替换为只要有信就通过 |

`_terminal_determination_expected()`另按原expectation决定是否执行一组终态链检查，原NA不表示这些轴已通过。两个MD false与状态/信件false并非四个相互独立的临床判决。用完全自造case/空ground_truth运行原MdReviewVerifier：无MD时两项均false；只加入MD决定及对应audit即两项true，而另一个rationale检查仍可false。该最小特征验证仅说明存在性/动作语义，未重跑本题评分、未证明虚构MD记录可合格、更未建议伪造或补写MD。

源码锚点：[md_review.py](../vendor/chi-bench/src/chi_bench/verifier/stages/md_review.py)、[outcome.py](../vendor/chi-bench/src/chi_bench/verifier/stages/outcome.py)。未改官方评分器或原evaluation_entry的live拒绝。

## 交付结论与下一入口

离线证据审计、四PDF供应/实际观察、26轮/46动作对齐、两份自造verifier特征检查完成。结束时逐字复核冻结原文件与原Q/CHI完整历史，当前active pending/halt=null；唯一旧S acknowledged-unsettled仍未结算，不重复留档、重发或当全局阻断。账/来源迁移与wire/seal链不因本轮分析重新生成。不存在新的模型用量/token未知，新增真实请求0。

结束复核结果：2466项原文件及Q文件集合不变；原账SHA256仍为`9060010ba5e487538fc3e79e025193b591e9e2ef883c92eb55d53c27598775b2`，冻结清单SHA256为`3c63873e5bdbb128bfa7668d1e1deac226e4e79d9aa84f1dc43d63d68b12e02d`；runtime/SDK/PDF身份一致，五份交付文档的165个本地相对链接可解析。文档后续仅补本段复核结果、工作项与PR指针；提交前另做diff/上传范围检查，不重复运行已完成的模型或旧代码验收。

建议下一阶段先按[X设计后续方案](../openspec/changes/payer-offline-diagnosis/design.md#诊断收束后的后续方案提案尚未实现授权)做自造材料的证据核对原型，测试必需/建议、事实/推断与引用有效性，再决定是否接入不可修改建议前；不声称该原型能自动判断临床充分性或保证修复本题。具体实施、身份/B、真实清单与任何复测均待另阶段授权。W三题额度已收束，t011只可作另获授权的已见回归；原t012/t014/t017/t013、t019例行付费、Claude/Go临床评审、F.5、正式Harbor/配送保持既有暂停边界。

本阶段只上传通用结论/元数据与规格；原题文/PDF、手册正文、轨迹、世界/隐藏材料和分析脚本留忽略目录。内容verdict、终态因果未决与未见任务收益都不升级。十一月任何真实调用前人工复核当日隐私条件；本次离线零调用没有沿旧条件放行。
