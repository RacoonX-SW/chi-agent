# T：Go 确认超时、费用记录与有界恢复

日期：2026-10-30（Asia/Shanghai）。按[有界规格](../openspec/changes/go-chi-timeout-recovery/design.md)保留初始离线修复事实，并在 PR #24 中接续用户授权的费用反馈与独立恢复。原超时始终未结算，不改写旧失败；本报告按实际先后分别记录两部分。

## 基线与证据

GitHub核对PR #23 closed/merged，merge/latest origin/main=`25336ed774be934af1d7fc4765884d837e62ff15`；旧工作区干净，从该点建立`codex/go-chi-timeout-recovery`。原S记录不改。一个既有Terra/high实现者先完成只读分析，主代理制定规格、独立审核及Git；真实模型调用仍被未知占位阻断。

源码核对：`local-confirm-patient`复用Go runtime的AsyncOpenAI，未覆盖默认`httpx.Timeout(60.0, connect=10.0)`，因此read/write/pool各60秒、连接10秒；read是等下一数据的间隔，不是总墙钟时限。确认输出上限为32768。用户已登录的官方Console对应时段最后记录显示约88秒后HTTP200；单靠此信息不能补账。

主代理只读使用官方Console已有会话，未改订阅/隐私/权限/Extra Usage。当前可见26条记录及Extra Usage=Off；未调用推理API。Copy JSON未能从浏览器剪贴板读到内容；Download JSON动作后下载事件等待超时，不能据此断言导出失败。用户随后提供同名实际文件，确认导出已落盘。只读Docker解析的两种挂载均成功，原文件字节一致；一开始直接Downloads挂载等待较长，另复制到忽略工作区再解析，无安装/新依赖。

用户文件原字节1592 bytes，SHA-256 `7baff44917627c01f472fe1945ca5a4115a4d74daf1b73dea283b95f71eb40aa`。event显示模型/路由正确、非stream、attemptCount=1、HTTP200/outcome=succeeded；duration=88269ms、首次token约87568ms，input39957/output15799（含reasoning14759）、cache读写0、Console cost精确`0.01547295`。导出没有响应usage.cost/opencode.billing_source/list_cost/allowance；不能将该cost复制到三项USD或按比例补allowance。原JSON仅放本轮provider-source忽略目录，账户/user/session/位置等不上传。

官方[Inference计费字段](https://opencode.ai/v2/docs/console/api/inference/)区分余额实扣、list_cost和allowance；[API说明](https://opencode.ai/v2/docs/console/api/)列有Usage读权限，但未给出可用于补齐该单次响应费用的公开接口。本轮不猜测私有API、读取浏览器cookies、扩充Key权限或新建Key。确认用途与十一月隐私仍按原限制处理。

## 实现与首轮审核

`go_chi_policy.TIME_POLICY` 纳入固定profile和包身份。`run_chi()` 保存运行起点；`ChiGuard.handle_async_request()` 完整校验后，在单调准入窗口内durable reserve，再按可信purpose覆盖HTTP timeout extensions并限定发送/读取总时长。主/B read60、I/O120秒；确认read360、I/O420秒，connect10、write/pool60不变。B/C准入180/900秒，窗口耗尽不reserve；已发请求不因准入窗口结束立即取消。operator先校验B360、C1380至3600秒等待范围，再创建资源/读Key；非日历门禁。

新request evidence保存`dispatch`版本/purpose/session SHA/UTC毫秒/原文bytes，账目保存dispatch_version并在完整审计交叉核对，hash保护元数据，旧request/wire/seal不重写。哈希是本地持久性证据，不代表提供方认证或签名。`inspect_history()` 先持Q→CHI锁并校验预期账身份/hash，完整验证合法pending/halt，再列出已知费用完整性及缺件；`inspect_provider()` 只读校验外部JSON/SHA，不调用模型或补账。Console cost用Decimal作为独立观察，不填三项费用；新记录可报告尺寸/session/time一致性，仍不声称唯一绑定或授予运行权限。

主代理首轮差异审核发现并交同一实现者修正四个边界：event.id与requestID不一致应拒绝；legacy虽无dispatch仍可核对已保存原文字节数；pending=null但halt=billing_details_unknown要列实际缺失费用字段；reserve的dispatch长度范围应与后续审计一致，非法输入不能先留下inflight。实现者修正后停写，未接触真实题文/账/JSON/Key。自测通过不代替独立审核。

## 固定候选与独立验证

候选 **`c587b446a54833393c1feb7deaeb3ac6fca47bfb`**；主代理从Git archive提取独立快照，禁网、源码/vendor/SDK/PDF只读、data/runs/tmp隔离，无Key/真实账挂载。最终独立包31个allowlisted文件，manifest **`a63e3b751e3218ffa998ae322b971a2d9d9df8fe5fb1de8117c31a8edb34c767`**，运行身份 **`1dfff8fb6bf78fcdfe9155597a8584ae333d8d0c126d346a84b7f2579609751d`**。33个运行/操作者源文件hash与时间条件冻结在忽略的`evidence/frozen-candidate.json`；实际模型请求和账内容写入的本轮预算均为0。

复用dev镜像`b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`、controller镜像`24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Python3.12；实现者使用的controller别名与主代理镜像ID相同。SDK卷、PDF卷及固定上游的全部身份字段与S逐字段一致，仅bundle manifest变化，无安装/改锁/重建/G/H重做。

| 验证 | 实际结果 |
| --- | --- |
| 实现者逐次Go回归 | 63 passed/2 skipped/20 subtests/2.17s；增加场景后63/3 skipped/20/2.12s，再91/3/20/2.33s、92/3/20/2.38s、94/3/20/2.89s；全部禁网合成，无失败测试 |
| 实现者controller及包 | controller两次均4项通过，最终0.005s；自测包build/preflight通过但为首审前临时产物，未用于正式验收/运行。日志完整保留 |
| 首审修正后目标回归 | 39 passed、15 subtests、0.54s，覆盖上述四个边界；一次apply_patch上下文不匹配在写入前拒绝，拆分后应用成功，无生产运行 |
| 主代理全量独立回归 | **425 passed、3 skipped、168 subtests、18.22s**；controller专用4项/0.004s通过，覆盖dev中依赖controller的跳过场景 |
| 主代理独立SDK八例 | 主/确认extensions和总时限、HTTPX timeout、外部取消、新请求过窗零reserve、已发请求跨窗完成均通过。使用真实锁定OpenAI SDK和MockTransport；7次模拟请求，真实请求0；未知新attempt阻断，秘密/会话原值不写wire |
| 完整旧历史副本CLI负例 | 坏主账hash、坏提供方JSON hash、未结算rebind三例均明确拒绝，副本主账原字节不变、无migration marker；原历史只读，不在真实账试写迁移 |
| 真实只读历史与用户JSON | 新包inspect-history exit0，完整Q/CHI/归档/请求/工具/seal/receipt结构审计通过；正文长度133919与导出相同，原缺dispatch/response/三项费用仍列出。execution_allowed=false、correlation unavailable、unique_match=false，费用完整性仍false |
| 独立归档 | allowlist归档真实解包、无Key/禁网且原源码不可见preflight通过，与原包identity JSON完全相同 |

独立脚本先以原S包核对：用户JSON的模型/路由/用途相关参数、字节数、服务端开始在本run窗口内、完成在客户端run结束后等十项候选关系均相符；原本地请求SHA `a40e691302ad3b0805ce035da78124c86f6056a7fc684976eb13fabffbe89d55`。旧请求没有持久会话关联元数据，时间/大小相符不自动构成唯一提供方绑定。也没有确认业务内容返回，不能把旧失败或未确认患者改成成功。证据仅在本轮`provider-forensics.json`和新包`actual-inspect.json`，不反馈参赛Agent。

最终主代理审计首命令漏挂现有SDK卷，入口import因缺httpx失败，尚未读取账；补回只读SDK/PDF后继续同一候选核验，原日志保留。浏览器的未派发读取/空剪贴板解析和下载事件超时见前文；真实模型/业务工具均未因这些尝试调用或重试。

## 初始离线部分的用量、交付与限制

初始离线部分 **真实模型请求0、业务工具调用0、Claude0**；新增余额实扣/价目价值/套餐消耗均为0 USD。旧Q/R/S当时为26发起、25已结算、1未结算；已知费用及历史CNY沿用S原账，不与Console观察cost合并、不把未知尾项改0。开发/审核Codex自身token账单未核实，不并入Go运行账。后续反馈授权及新增真实运行见下一节。

独立归档 `runs/go-chi-timeout-recovery-root/exports/chi-go-entry-c587b44-bundle.tar.gz`，**125888 bytes**，SHA-256 **`e05f4736977b27ad8260ae12cc87ea245c7c1fb94f23e576c76f566ada25d4ef`**，含31文件+manifest和必要空目录；不含provider原JSON、任务、手册、vendor、Key、控制器或轨迹。外部依赖/公开输入/角色MCP仍由调用方提供，完整Harbor/F.5与官方评分没有验证。

c587b44当时仅在上述离线/故障/只读证据范围通过，尚无新来源的真实B/C，也未验证真实长确认在新配置下的结果、硬取消/daemon故障或完整计费恢复。初始部分不改旧主账identity，pending继续阻断迁移和调用，没有人工回填或自动核销。之后用户另行批准的留档继续方案及新候选结果见下节，不能据后续成功改写这段历史。

最终Docker核对旧 **49230文件/30链接** 全部原字节不变，旧范围无新增/删除路径；Q/CHI全部归档/wire/工具/seal/receipt完整，主账仍SHA `0832f113ccb8dd5342f06e6ae211af3eaf87e9e9d8032d65d1c85d705e0aa55b`，pending仍为S第9请求。33冻结源文件和归档身份不变；两种原Key存在、没有准备运行Key文件；342个新文件/18086444 bytes扫描无配置秘密，原JSON原字节不变。完整输出为忽略的`evidence/final-audit.json`，最终上传另按显式源码/文档清单和patch扫描，不上传该JSON或原始轨迹。

上传24份受审代码/合成测试/配置/职责文档，完整patch及路径秘密扫描通过；分支已推送。首次GitHub创建因连接中断未得到结果，先查询确认无open PR再补建，成功创建并附加base=main的[PR #24](https://github.com/xsw932187210-cell/chi-agent/pull/24)。这是GitHub传输重试，不是模型请求重试；由用户审核合并，未merge/auto-merge。文档提交和PR不替代上列c587b44源码验收身份。

## PR费用反馈修订（2026-10-30）

用户明确要求充分利用Go订阅推进开发/实验，不因金额或费用精度缺项反复暂停。PR #24实际核对仍open/unmerged，在原分支继续反馈修订；原c587b44离线通过与当时零真实调用事实保留。主代理将新版费用策略与旧严格策略分开，保持旧Q/native源码/账、Extra Usage关闭和零自动重试。

另因用户最初要求未知用量全局阻断，主代理只就“已有官方后台tokens但未完整响应的这次旧超时能否留档继续”澄清，用户明确选择**允许留档后继续新试次**。规格据此只授权一次精确目标的未结算留档：不settle、不改旧失败/wire/seal/费用、不重发旧请求；后续采用新候选、新B、fresh world，固定最多1B+1次t012+原冻结t014/t017各一次，总请求上限156。实际实施/独立复验及运行结果在本节接续，不预填通过。

### 反馈候选、费用策略和独立审核

唯一Terra/high实现者复用原SDK/guard/journal，完成后停写；主代理按差异审核，要求补强留档前快照的v1字段、原pending集合与既有留档前缀一致性，以及warning仅按新attempt策略计算。实现者修正后固定 **`721b14e17e37917d27f333d7aac6aaedfa99b9ad`**，原Q/native源码及旧attempt契约保持原样。

新 `FEE_POLICY=go-chi-record-incomplete-fees-v1` 同时绑定profile/包配置和每个新attempt的launch。`ChiJournal.settle()`先验证tokens，再由`_fee_decision()`保留原billing_error并单独决定是否停止。缺金额/source留null及不完整warning；明确非Go来源或余额实扣仍停止，非法数值/类型/token冲突仍拒绝。费用缺项与结果/token未知分别处理，不自动回退或重试。

实现者Docker自测：首轮28 passed/17 subtests，随后31/20、33/28；全量专项两次均110 passed/3 skipped/44 subtests，控制器4项，主审反馈修复后36 passed/32 subtests（0.42秒）。这些是开发检查，不替代下列主代理独立复验。

主代理从候选Git archive提取独立源码，在无凭据、禁网、只读源码/SDK/PDF/vendor和隔离data/runs的Python3.12 Docker内验证：**440 passed、3 skipped、191 subtests（19.24秒）**，另controller 4项（0.004秒）。完整真实旧历史只读挂载，在临时副本上验证5条链：精确旧事件留档后所有旧attempt/文件不变、重复留档拒绝、跨来源不能复用旧B、真实SDK合成B的3次缺费用响应仍完成并保留null、随后新的带dispatch未知仍阻断。副本测试真实模型调用0，不能作业务能力证据。

新包31文件，manifest **`09fdf7008949b9babf90b9848e5d11c0d90d59466958a81d5a9daa375a037c62`**，运行身份 **`0cd78f67750c313aa96ed45e6f6f986561d47e2b7ca2817ce56a46e080cd5f46`**；SDK/PDF/vendor身份全部与初始T相同。33个运行/操作者源hash、4个配置及序列固定在`financial-feedback/evidence/frozen-candidate.json`。归档`chi-go-entry-721b14e-bundle.tar.gz`为129,227 bytes，SHA **`c54adc01f6d18e9b3c9fb6c39600a4e7c6ca50afac6a6c242a6f9d08d00263a5`**，实际解包并在原源码不可见的挂载下通过独立预检；不是完整Harbor/F.5配送验收。

### 实际留档、迁移与调用前检查

费用反馈前基线49,545文件/30链接。对唯一旧`s-go-v2-c-t012-1-20261029-001`第9请求执行一次`acknowledge-unsettled`；事件hash为`aa598c488c24fccb8b43157eb958c0f4124ca6503ed408643a4ec1c56f1bcdce`。原主账`0832f113ccb8dd5342f06e6ae211af3eaf87e9e9d8032d65d1c85d705e0aa55b`按原字节归档，用户原JSON旁证保留原字节，原5个attempt及失败/seal/wire不变。留档后的primary为`ea23d9a6dbff9f8f50f931a2d81f761e790a55a0969417875ee7b3c3c08e0ed7`，pending/halt=null；独立逐字节验证其余49,544文件/30链接不变。账目中旧请求仍pending未结算，汇总仍有1个历史未知，未作唯一提供方关联或费用回填。

然后用上述留档后hash执行一次显式`rebind-history`，原来源`91f0f382ce79235b1174c7322e8d1f3804d629d23816566f471f4f2ed6cf2eeb`迁至新身份，新增第3次来源归档。调用前检查首次Docker命令漏挂SDK卷，导入httpx失败，真实请求0；保留`prepaid-no-sdk.log`，补挂既有只读卷后检查通过，没有安装或修改依赖。Key只检查Go/native均存在，临时0600文件仅含Go Key，未输出值。此为操作者启动命令错误，不是模型业务决策错误。

所有本节本地证据根为忽略的`runs/go-chi-timeout-recovery-root/financial-feedback/`；`operator-audit/`保存操作者脚本/固定配置，`evidence/candidate-1/`保存独立验证及运行审计，`actual/`保存原始终态和日志。不上传原JSON、真实轨迹、隐藏检查或受限包。

### 固定条件下的全部真实试次

模型固定`deepseek-v4.1-flash`，SDK base URL为`https://opencode.ai/inference/go/openai/v1`，无`[1m]`；thinking/high、固定SDK/PDF/vendor/镜像和公开提示不变。B为6次/1024，C主/确认共享50次、确认最多2次、主输出8192/确认32768，零自动重试及回退。资源继续使用S提前固定的dataset revision与三个task/hash；t012是已见开发回归，t014/t017在S按兼容元数据选定后未运行，本次各只运行一次，未因结果换题或改候选。四份新配置在所有真实请求前冻结，依次新attempt/fresh world执行，不恢复旧S配置。

run前缀均为`t-go-fee-`，后缀均为`-20261030-001`：

| run中段 | 结果 | 模型请求（主/确认） | 工具开始/返回/拒绝 | 控制器耗时秒 | 适用开发检查 |
| --- | --- | --- | --- | --- | --- |
| b | complete，当前来源B收据有效 | 3（3/0） | 2/2/0 | 6.574 | inspect_code → verify_patch → final |
| c-t012 | complete，claim_done=true | 23（22/1） | 46/45/1 | 452.138 | 8/8通过，1项不适用 |
| c-t014 | complete，claim_done=true | 28（26/2） | 41/38/3 | 624.888 | 8/8通过，1项不适用 |
| c-t017 | complete，claim_done=true | 29（28/1） | 34/32/2 | 379.695 | 9/9通过 |

合计**83次真实OpenCode模型请求，全部已结算tokens，无新增未知；123次工具开始、117返回、6拒绝、0 failed/returned_error**。四次控制器耗时合计1463.295秒（约24分23秒，含各自准备/捕获/清理，不是全部开发时间）。本次无失败B/C、无重跑、未挪用剩余额度；各请求usage/费用/诊断与响应耗时保存在`actual-<label>.json`，不是按整数百分比估计用量。

工具开始次数完整汇总：`auth.check_status=5`、`auth.finalize_provider_determination=1`、`auth.submit_authorization=3`、`cases.create_from_order=3`、`cases.get_case=2`、`cases.list_cases=3`、`chart.get_patient_chart_by_patient=21`、`chart.list_candidate_orders=1`、`chart.search_patients=5`、`docs.create_submission_bundle=3`、`docs.list_case_documents=3`、`docs.upload_evidence=3`、`forms.list_required_forms=2`、`forms.save_form_response=3`、`inbox.list_messages=5`、`people.list_ordering_providers=3`；本地`claim_done=3`、`confirm-patient=9`、`fs-edit=1`、`fs-list=13`、`fs-read=25`、`fs-write=3`、`read-patient-observation=1`；B的`inspect_code=1`、`verify_patch=1`。逐run分布和原结果hash保留在独立audit JSON/工具证据，模型并未收到操作者隐藏检查。

拒绝全部保留：t012一次、t014三次、t017一次患者确认返回`selection_evidence_unverified`；t017另一次公开观察工具返回`observation_unavailable`。5次选择依据拒绝未发确认provider请求，模型继续读取公开材料后自行选择下一动作；没有人工代选、删除拒绝或HTTP自动重试。9次确认工具调用只有4次实际确认请求，四次响应耗时依序为**80.479、70.457、76.758、55.537秒**。前三次均超过原60秒read并在新界限内返回，是实际长等待恢复证据，不能推断所有未来请求必然成功。

三题原世界初始provider均2202条/payer0条；结束后t012为2227/2、t014为2224/2、t017为2228/2。独立对全部两侧资源逐条语义比对，变化分别27、24、28条，均能关联目标患者，无非目标、归属不明或混合变更；workspace内容与审计轨迹另由工具证据保留，不把资源计数单独当作充分证明。三题target_case均`submitted`，payer intake均`in_progress`，提交包/字段/服务地点等适用程序检查通过。所有初末捕获/manifest/resource hash、runner静止、容器和网络清理均独立核对，无capture/cleanup/primary error。

### 逐试次用量、费用与历史保留

下表是Go响应给出的三种独立USD口径，不能相加；余额实扣为这批已收到响应的字段值，不是完整账户对账。订阅固定费另计。

| 试次 | 输入tokens累计 | 输出tokens累计 | 余额实扣 USD | 价目价值 USD | 套餐消耗 USD |
| --- | --- | --- | --- | --- | --- |
| B | 1,360 | 106 | 0 | 0.00015470 | 0.00011603 |
| t012 | 6,646,790 | 23,974 | 0 | 1.00989762 | 0.75742325 |
| t014 | 7,818,635 | 35,236 | 0 | 1.18889414 | 0.89167062 |
| t017 | 6,273,269 | 28,572 | 0 | 0.93976913 | 0.70482687 |
| 本次合计 | **20,740,054** | **87,888** | **0** | **3.13871559** | **2.35403677** |

这批真实响应费用字段均齐全，warning=0；缺金额仍可继续已由真实SDK的合成3请求B验证，未冒充本次真实服务发生过缺项。累计输入是多次上下文重复发送之和，三个C的单请求最大输入分别431,634、497,241、363,719 tokens；**没有百万token上下文实测**。

Q/R/S/T全部保留后累计109发起、108已结算、1旧未结算；已知输入21,788,027/output93,970，已知余额实扣0、价目价值3.29880808、套餐消耗2.47410616 USD，**三项完整性均false**，未知尾项仍在，不填零或把Console cost并入。旧native CNY历史全部原字节不变，不与USD相加。

最终实际主账SHA **`3814a9452869ef36e5be93c3fdc051348be6909741be4125c02e4181630bb362`**：9个attempt、3个来源转换，active pending/halt=null，唯一旧S第9请求仍未结算且有显式留档链。最终逐字节核对其余49,544旧文件/30链接无变化，原5个attempt及旧封存/证据/账归档不变；没有清零或另建历史根。33冻结源hash、4配置、独立包及解包预检身份不变；全部owned容器/网络已清理，临时单Go Key文件已删除，两种原Key仍存在。833个新文件/143,100,226 bytes扫描无配置秘密，完整证据为`evidence/final-audit.json`及`retention-final.json`。

### 当前验收结论与交付边界

**721b14e在本轮工程修复、新B及三次provider开发任务的适用检查范围通过**；原失败、拒绝、claim、费用及旧未知均保留。两次固定未见题提供有限迁移样本，尚无重复性统计或全赛道泛化结论。三题`submitted/in_progress`与部分程序检查不等于临床批准或官方评分；Claude和Go付费临床评审未调用，official_reward=null。

独立包可在原源码目录不可见时预检/启动，正式角色输入已由实际C执行验证；本地操作者不是官方提交包的一部分。原stock harness不会自动选择自有适配器，完整Harbor类型/配送、F.5最终冻结继续暂停。Go非编码用途及十一月隐私支持仍未获官方明确确认，用户已知悉并授权当前开发使用；不能写成官方用途或十一月ZDR已确认。t013不重跑、t019例行付费复测不恢复，没有程序日历门禁、后台等待/唤醒或Antigravity操作。
