# 输入摘要单次真实探针：执行与核验

日期：2026-11-04（Asia/Shanghai）。本报告接续[PR54包外接线及独立复审](validation-probe-wiring-review.md)、[绑定候选的S阶段草案](../openspec/changes/validation-preparation/proposal.md#4-s输入摘要端点兼容以后单独审批)及[本候选coding-B](validation-coding-b-review.md)。详细结果集中于此，短状态只见[REVIEW_STATE](REVIEW_STATE.md)。不改写历史失败、旧unknown或离线阶段零真实调用结论。

## 1. 本次授权与固定范围

用户在当前对话明确批准：

> 按PR54及摘要探针草案，批准配置SHA `8fe12ade59359c45a2cafb7d0ebc3f35b6b0318c74546af885002d9f646f0c29` 的 `vprep-s-001`，在 `eval-vprep-20261104` 同账执行一次指定payer任务，最多50个模型HTTP，仅开启摘要。保留payer-010旧unknown/pending，不核销、不重发；未触发即收口，异常或新未知立即停止。暂不授权其他真实运行。

启动命令第一次提交给自动审批时被拒绝，命令未创建进程、launch intent、attempt、world或输出，新增HTTP为0。用户随后明确补充：

> 同意本次 vprep-s-001 使用既有 Go 凭据，将指定 payer 任务输入、资料及手册片段、工具观察和触发后的摘要输入，发送至 `https://opencode.ai/inference/go/openai/v1/chat/completions`，模型为 `deepseek-v4.1-flash`；其余限制按上一条批准保持。

本地分别保留最初准入决定、拒绝现场、补充授权和重新核验记录，未绕过拒绝或清除历史。用户补充授权后，才启动下述唯一一次运行。次数上限是物理主请求、确认和摘要合计50；摘要≤1、确认≤2，continuation/患者/Y shadow均为0。未为触发更改模型、high、提示、工具、8192主/摘要输出、32768确认输出、原context预算或摘要4/5阈值；自动重试和回退为0。固定900秒准入及既有I/O/runner/operator窗口保持。

## 2. 候选、资源与离线准入

核实用户已合并[PR54](https://github.com/xsw932187210-cell/chi-agent/pull/54)，`origin/main=29327e11696ebad512f92cc2f7c0fd1a104f8965`；从其新建`codex/summary-endpoint-probe`，未续写已合并DeepSeek分支。主代理直接执行及记录，没有新增生产实现、测试、profile或依赖变更，没有派发实现代理。现有其他worktree保留，探针使用独有world/runner/network及输出。

| 项目 | 绑定值 |
| --- | --- |
| 配置原文件 | `runs/validation-live-20261104/probe-summary-draft.json`；SHA为上述用户批准值，原字节未修改 |
| 包外已审实现 | `afb9dff85de9599196f89c7c81a1f6b1d9691eee`；当前main相关scripts/profile/runbook无新增差异 |
| 候选清单 | [validation-candidate-20261104.json](validation-candidate-20261104.json)，原SHA `1846d79cd276aee9cb8414e9e80b78ac9639f227c3a2ae1a97bcefb9f3f9b1d2` |
| 实际内包 | 复用`runs/validation-preparation-20261104/exports/release/package`；bundle identity `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb` |
| runtime identity | `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559`，本候选既有B适用，不重跑/借用旧身份B |
| evaluation/state | `eval-vprep-20261104` / `runs/validation-live-20261104/state`，直接复用同账，不复制真实运行根 |
| run/attempt/task | `vprep-s-001` / `summary-probe-1` / `pa_t030_t030_o002_p01_triage_payer` |
| 资源manifest | `runs/representative-role-baseline-root/evidence/role-resources-payer-t030.json`，SHA `6518225bd1c91525c17ff4f735173baaf1bf9433ad1b479093c096f2c16d3ba2` |
| world/runner/controller镜像 | 分别`000ca509…` / `b22f7c66…` / `24bef2e2…`，精确完整ID见批准配置及本地核验记录，无pull/重建/替换 |
| 本次输出 | `runs/validation-live-20261104/probe-summary`，启动前不存在 |

执行前及补充授权后均在禁网、无凭据的Docker/Python **3.12.15**核验：精确配置/开关互斥、包外5文件hash、候选清单所列42文件、实际内包identity、公开/世界资源闭包、手册digest、同账严格history/B receipt/seal、旧两份accounting hash、未用输出及独占Docker名字。专用既有`go.env`单独在禁网容器验证为受限权限、仅含一个Go凭据变量，不输出值，不读取完整`.env`。主控制器禁网，经Docker socket创建实际runner/world；仅runner获得既有Go凭据及模型网络。

新核查脚本最初抄录旧hash少写字符，断言停止在离线阶段；对照原草案修正后通过。旧账本没有漂移，该核查失败不计模型HTTP，也没有新建attempt。原脚本、拒绝记录及后继核验均在本地忽略目录，不上传。

实际入口为已审`role_operator.py --config … --config-sha256 …` → `role_runner.py live` → 原内包entry/runtime。operator精确透传`--input-summary chi-input-summary-v1`一次，其余开关缺省关闭。payer不启用包外患者模拟器；官方world仅接收固定任务环境，不接收模型/judge凭据。Agent只见公开指令、工具参考、允许的手册/工作区及正常工具观察；操作者不解析隐藏expectations选择动作。自动末态capture后的既有deterministic checks设置`include_semantic_judge=False`，不是新增模型判分或官方成绩。

## 3. 执行结果与用量

**本次失败收口，摘要端到端兼容未通过。** 唯一一次真实控制器运行发生于北京时间20:42:14–20:47:29，约315.26秒；controller/runner均exit1，无OOM/restart。19个main之后自然触发第20个summary，未触发确认、续写或患者调用。全部20个请求settled、pending=null、halted=null，没有新增结果/token未知。86条tool事件原样留档；没有因失败追加请求或再次创建world。

第20笔摘要HTTP200、耗时60,502ms，但`finish_reason=length`；input=212,561、output=8,192，提供方细节同时记录reasoning=8,192。最终`content`为空，reasoning文本30,145 UTF-8 bytes。固定8192输出窗口被reasoning消耗，未产生可供解析的最终摘要JSON。原guard在`go_chi_guard.py:191–194`拒绝非stop/空正文，抛出`chi_summary_invalid`；尚未到`install_summary`，因此journal中summary事件仍为`requested`、candidate/checkpoint均null、projections为空。这是**已有响应但未接受候选**，不是HTTP仍在途；request本身已settled，run已failed，不能仅凭事件名判断pending。

禁网回放同一原响应，原`candidate_from_response`同样拒绝为`chi_summary_invalid`。摘要请求确实没有tools，也没有`response_format`；固定JSON schema在用户消息的`output_schema`中提供。因此HTTP200只证明本次固定无tools请求被端点接收并返回，不证明服务端结构化输出支持或候选schema验证成功。所选历史含58条message/41个source引用；选区、保护快照及原wire均保留，未安装候选、未发带checkpoint的下一main。摘要忠实度未做语义验收；净费用收益也未成立。错误路径没有让摘要续写、输出恢复或Y shadow接管。

| 本次用途（不含既有B） | 物理HTTP / settled | input / output tokens | list_cost USD | allowance USD | charged USD |
| --- | --- | --- | --- | --- | --- |
| main | 19 / 19 | 2,556,220 / 23,966 | 0.39751154 | 0.23850692 | 0 |
| summary（失败、未采用仍计入） | 1 / 1 | 212,561 / 8,192 | 0.03679935 | 0.02207961 | 0 |
| 合计 | **20 / 20** | **2,768,781 / 32,158** | **0.43431089** | **0.26058653** | **0** |

本次三项USD完整且分列，未知token数为0；charged=0仅为这20笔提供方返回值，不能推出旧账已核清、账户总消费为0或订阅余额。严格history/summary工具核验通过的是留证与结算一致性，不能将本次run升级为成功。既有coding-B的14个非accounting文件逐字未变，receipt及seal仍有效；同账accounting新增本次失败attempt，未清空历史。

操作者保存初始/最终capture、前后provider/payer资源快照，状态均ready；payer四份公开PDF投影检查通过。runner静止、`broker_drained=true`（payer无患者）、`world_quiescence=confirmed`。world/runner/network已由原操作者删除，包外只读审计按精确ID再次得到404；唯一已停止、标签匹配的controller在保存状态/日志后删除，再次查询404。没有清理其他资源或删除日志。末态deterministic checks仅为既有本地检查，保留未完成业务项，不计官方评分或临床通过。

## 4. 本地证据、保留项与核验

以下相对路径均在`runs/validation-live-20261104/`下，不上传GitHub：

| 证据 | SHA256 / 说明 |
| --- | --- |
| `summary-admission/admission-decision.json`及`admission-revalidated.json` | 均`d6c80b46eb3772167cb0da21051ee91e64a2f91e4369d0b7c86a747b32f574bf`；独立于原B授权文件 |
| `summary-admission/blocked-before-launch.json` | `d8422ad4a4d3d9acb2923788ff82a8627abc52325b2d76ce8437d9960b73387e`；保留自动审批拒绝及零启动现场 |
| `summary-admission/destination-authorization.json` | `13267fc7d33fce0451e2a677cecd384c7e46beeed2670e2763e9fcba85d2bc63`；补充授权原文 |
| `state/chi-accounting.json` | `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`；原B及新失败S，同账无新pending/halt |
| `state/run-seals/vprep-s-001.json` | `2d35490f34e7c28672b59a2274ec996a666f6348db84694f49a2d2d8d6e0a0dd`；按原严格reader重算一致 |
| `summary-admission/postflight.json` | `a0025e2fcd788e5013508b312d053c04f4236db88bb4a6fc2bcdc991374dbc9b`；每笔原wire/证据hash、参数、usage/费用、strict validation及capture |
| `summary-admission/failure-diagnosis.json` | `2b1b28ed28b4828095b70c2ea5bc64a5171cb6206737929d82e6130080ed155b`；原响应离线拒绝复现、length/reasoning及选区元数据 |
| `summary-admission/run-summary.json` | `4ae5dc3fc919dc9713bbffe1794941ee034247032055f83114d32a7fa2f2dcae`；只读摘要绑定同一accounting快照 |
| `probe-summary/orchestration.json` | `0f178cc6e295c37e60d186eb587394dac2c43335d05467c8f066b6d54ecf7d82`；主错runner_failed，capture/cleanup错误均null |
| `summary-admission/cleanup.json` | `4fad3b1f28e38c662dfbf6b4e2b1ca7d1a8955d7c8278d7fe5cc21fb0aa93ec3`；四个精确owned ID不存在 |

第20笔原request SHA=`1fc57c6ea563c8d5eb2b385cd4dcaa5fca9a92c50472a185e1be435cf5384b77`，原response SHA=`254454ddb75d2c1d5e092e65e7b699fbee63c2b03703d487c8798d0fd89dc435`。对应envelope及选择证据由严格reader逐项校验。`summary-trace.jsonl`保留一次requested事件，`recovery-trace.jsonl`为空；不将空恢复trace当作真实恢复通过。

旧`state-abl-on/chi-accounting.json`仍为`1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef`，pending仍为`real-ext-payer-010` round1；旧`state-abl-on2`仍为`7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9`。没有核销、ack/reconcile/rebind、重发或换根。历史特定后继授权缺口不由本次决定回填。

禁网核验命令及脚本保存在`summary-admission/`：`offline.sh`、`postflight.sh`、`diagnose.py`、`cleanup.py`及`final-check.py`。每笔实际请求的model/thinking/high/输出上限均复核；literal凭据扫描覆盖383个新state/输出文件，无命中，值不打印。最终文档检查exit0，复核11个文档引用证据hash、Decimal费用总和、本地链接、42个候选文件、旧账与当前配置字节，另核对controller日志无literal凭据；结果保留在`docs-check.json`。审计过程曾缺少既有model-deps只读挂载，清理审计挂载曾与`/run`冲突，修正后离线检查通过；这些是包外核查，不是重跑真实探针。未重跑全仓pytest/unittest，因为无生产代码、测试或依赖改动；PR54既有skip及anthropic缺项保留其历史含义。

## 5. 结论、剩余准入与DeepSeek有界任务

| 项目 | 本次结果 / 后续条件 |
| --- | --- |
| 单次许可 | 已消耗：1逻辑S、20物理HTTP；剩余30上限不是新运行许可 |
| 端点传输/响应 | 本样本HTTP200且用量可信；摘要length导致端到端**未通过** |
| 候选接受/下一main | 0安装、0投影、0后继main；尚未验证 |
| 忠实度/净收益 | 无已接受候选，未评价忠实度；无对照且失败成本已计入，不能宣称净收益 |
| 恢复探针 | 仍未授权；本次失败不自动转跑R、不开summary+recovery组合 |
| 正式Harbor/Z4–Z8 | 继续按原离线准备与各自准入处理，不从本次获取真实Trial/业务效果/未见集或发布许可 |

已知缺口是固定high+8192摘要请求在本样本只产出reasoning，没有最终JSON。后续先交DeepSeek离线诊断及最小方案，不在本轮顺带改包或重构。可直接使用以下Prompt：

> 只做CHI-Bench输入摘要失败的有界离线分析，基于已合并PR54和本报告，先检查实际checkout/分支/写入者。真实证据是vprep-s-001第20笔summary：HTTP200、finish_reason=length、input212561/output8192，其中reasoning8192、最终正文为空；原guard报chi_summary_invalid，所有20笔已settled、pending=null，未安装checkpoint。只读取本报告明确列出的selection/request/response/trace证据，保留原账及失败字节；不要读取Key/.env，不发真实模型/摘要/续写请求，不启动world/Trial/judge，不改pending、不重跑本attempt。所有Python/回放在禁网Docker/Python3.12。独立复现固定guard对原响应的拒绝，核对摘要输入体量、闭合选区/保护快照与输出预算关系，区分正确的停止机制和摘要可用性缺口。提出最小、可审阅的方案及离线验收契约：列清是否需要改变提示/选区/模型参数或包内代码、为何必要、涉及的风险和身份变化；不得自行调整模型/high/8192/阈值以强制触发或通过，不写全面重构。先交离线诊断和候选方案，新增生产功能及参数调整另立有界实施任务；内包有字节变化须重建身份、单独审核/重绑B与真实许可。不要把HTTP200、schema引用或剩余额度当作端到端通过或后继授权。Git仅上传允许披露的文档元数据，保留原受限证据本地。

原始授权、账本、wire/trace、任务内容、资料、手册、凭据及受限产物只保存在本地忽略目录。Git仅交付本报告和短状态。原C1 unknown及历史特定后继授权缺口、C5会话支撑、正式Harbor/配送、Z4业务效果、Z5未见集及Z8材料均不因本次获得通过；官方reward保持null。任何下一真实运行均须另行明确授权。
