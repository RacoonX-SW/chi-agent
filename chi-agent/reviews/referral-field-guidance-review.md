# 公开字段依据提示与付费验证收窄

日期：2026-10-28（Asia/Shanghai）。PR #19 已核对合并，基线 `a1aa625c3b9fbc36df2fd6bf57e67787b5f2e526`，新分支 `codex/referral-field-provenance`。同一个 gpt-6.1-terra/high 实现并 Docker 自测，主代理负责规格、固定候选、独立审核、教学和 GitHub。

固定实现 `ed15c2bcfae7076f1165c92b6bf52b3fa16caa65` 离线实现及必要新 B 通过；同一源码的一次 t013 新世界开发回归正常结束、仅影响目标患者，确定性部分 **9/9**、DeepSeek 局部 **4/4**。上次服务地点失败项本次通过，P.4 已完成。17:24 的离线/零新增费用记录保留；用户晚间明确继续后，21:20 起在允许时段完成真实验证，没有重跑 t019，也没有为刷全通过追加 C。单次已见题结果不证明稳定收益、泛化或官方评分通过。

## 为什么暂停 t019、先看 t013

[N 报告](provider-patient-binding-review.md)与 [O 报告](request-budget-awareness-review.md)中的最终 t019 均正常结束、只影响目标患者，确定性部分 9/9、DeepSeek 局部 8/8。最初 M 的错患者写入与轮数耗尽没有被这两次后续结果抹去；这里的通过仅指各自开发候选的已检查范围，official_reward 始终为 null。

用户认为 Token 有限，明确要求暂停 t019 的付费重跑、优先处理 t013。执行上保留共享程序的合成离线回归，不再每个小改动都用同一题付费重复确认；旧候选结果也不冒充新源码实测。后续确需恢复 t019 的付费覆盖时，先说明必要性，按新的明确安排执行，不默认恢复。

## 公开证据诊断与有界假设

O 的 t013 已正常收尾，但确定性部分为 8/9，服务地点检查失败；局部 DeepSeek verdict 全 true 不能覆盖它。主代理仅从旧 journal 的公开确认结果定位所选患者，再回读其实际展示过的 `tool_history`，没有把隐藏目标或可接受值交给实现/参赛模型。

公开 chart 多处写明 `outpatient physical therapy`，候选 orders 返回空；模型因此从公开笔记构建新请求。旧 reasoning 记录其在多个合法地点选项间犹豫，最后主要据机构名称选择。这支持检查“服务类别、机构名称与照护场所混用”的推理路径，但不构成独立临床裁决，也不证明只加提示一定能改变选择。

本次假设是：在做出建案选择的现有工具接点，明确要求分别追溯关键字段的公开依据，并在提交前回到原始材料核对，可能减少无依据的映射。采用小范围提示变化，先不增加语义模型、结构化确认步骤或硬业务门禁；隐藏评分可接受值、默认地点、按诊断/任务/患者映射均不进入代码和测试。范围见 [P 规格](../openspec/changes/referral-field-guidance/design.md)。

## 最终实现与调用链

新增 `scripts/referral_field_guidance.py`，版本 `referral-field-provenance-v1`，只含静态通用指导及 hash/description 格式器，适用于 `cases.create_from_order`、`auth.submit_authorization`。前者要求从实际公开 instruction/order/chart/规则分别推导 procedure、服务类别、紧急度、诊断与地点，机构名称本身不证明照护地点/级别；缺证或矛盾时核对相关材料，优先复用观察，在原有笔记/rationale 简记依据。后者要求把 request/form/package 与源材料交叉核对，重复同一猜测不是来源支持，不新建另一案件掩盖问题。

`_worker_run()` 仍使用原 SDK/官方循环。在 MCP 工具转换成 FunctionTool 后，`strict_to_function_tool()` 仅对 K C 调 `_apply_referral_guidance()`：保留原对象、名称、schema、回调和返回，仅在原 description 后追加一次指导。B/J/无关工具不追加；未改 provider profile、system prompt、预算反馈、患者确认、字段值或实际副作用派发链。

新模块纳入 K execution identity。run journal 的 `referral_field_guidance` 保存版本/整体指导 hash，实际追加的各工具记录该段指导、原 description 和追加后 description 的 hash。相同原工具再次转换不会累积文本或重复写元数据；已追加对象再次处理、原描述变化或身份冲突明确失败，不悄悄替换。持久化失败继续传播，不在证据未保存时正常前进。

这是**模型指导**，不是程序已检查医学/业务语义。schema 合法、元数据来源正确和字段选择正确是三种不同结论。提示也可能增加补查或让模型在歧义处停下，不能预先称更省 Token 或更易完成。

## Docker 自测与主代理独立审核

复用 dev `chi-agent-dev:latest`，实际 ID `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，Python 3.12.15；复用 H SDK 卷 `chi-h-root-model-deps-20261027-v1` 和 K PDF 卷 `chi-k-pdf-deps-20261027-v1`。没有安装、下载、改锁或新建镜像，没有重做 G/H。P 没有运行 controller/world。

实现子代理禁网自测为 329 tests / 143 subtests，通过，工具 stdout 为其证据；其 data/runs 为 tmpfs，不写旧运行资料。停止实现后，主代理先读完整生产差异、调用接点和必要测试，再从 Git archive 固定 `ed15c2b`，只读挂源码/固定 vendor/卷、空 data/runs、无 Key/环境凭据/socket 的禁网容器独立通过 **329 tests / 143 subtests**，16.73 秒。测试包含实际 SDK/固定官方循环的两个不同合成地点路径：指导各出现一次，原 schema、参数和业务后端调用保持，确认请求不混入指导，也没有因为提示增加一次模型请求。模型输出是合成预置，不能证明真实模型会遵循提示。

主代理另写 4 组独立检查，全部通过：

- 静态模块只依赖 hash/JSON，无任务/患者/隐藏答案读取；K-only 源码身份与原 30/50 入口边界。
- 原 schema/回调不变，相同原工具再次转换不累积；无关/别名工具保持原值，描述/标记冲突拒绝。
- 元数据持久化失败传播，不静默前进。
- 独立构造的真实 SDK 请求经 GuardedTransport/合成 HTTP：仅一次已结算请求，两个实际 wire description 的 hash 对应 journal，原参数/回调分别接收两个不同合成值，无业务改写或新工具。

另外复用主代理 O 的 6 组独立边界检查，覆盖旧 profile/policy 身份、包含本次的预算算术、伪造/陈旧/额外 system、未授权 50 次覆盖、两次确认共享计数、无第 51 次及未知用量阻断；全部通过。未修改 O 预算模块/transport、患者确认模块或其业务门禁，没有为通过改变断言口径。

独立命令使用上述只读快照、固定 vendor 和卷，环境 `PYTHONPATH=/workspace/scripts:/pdf-deps:/model-deps:/workspace/vendor/chi-bench/src`，`PYTHONDONTWRITEBYTECODE=1`，执行 `/opt/venv/bin/python -m pytest -q -p no:cacheprovider tests` 和两个独立脚本。所有 Docker 命令为 `--network none --read-only`，data/runs/tmp 各自隔离；没有真实任务夹具、Key 或 Docker socket。证据为 `runs/referral-field-root/evidence/candidate-1/{pytest.log,independent.json,budget-regression.json}`；独立脚本 `check_independent.py`，旧预算脚本在 `runs/request-budget-root/`。

## 从离线候选接续真实验证

17:24（北京时间）的禁用窗口内未启动真实请求，早期证据 `audit_accounting.py` / `evidence/candidate-1/accounting.json` 保留，不能把它当晚间最终账目。用户随后明确“按照计划来继续处理 t013”；21:20 核对时间允许、PR #20 仍未合并、分支干净、生产源码与固定候选逐文件相同，因此继续原分支的 P.4，不新增实现改动或重复离线全量测试。

禁网保存 **32,188 个旧文件**指纹，原累计保守估算 102.493324 CNY；两套 pending=null、controller clean。再核对固定候选快照、profile/基础 system prompt、确认协议、50 次限制、固定任务资源、镜像/锁/依赖与 O 一致，仅检查配置 Key 存在而不输出。证据 `prior-live-files.json` / `experiment-live.json`。随后 `rebind-source` 明确登记 P 身份、接续旧账并归档旧 B，使用自己的新 B，未清零历史。

复用 README 的 Docker 函数及原包装，实际顺序为 `rebind-source` → `k-b-smoke --run-id p-b-20261028-001` → `c-run --task-id pa_t013_t013_o002_p01_new_referral_provider --run-id p-c-t013-20261028-001` → 该捕获目录的 `deterministic` → 一次 `review --review-id p-review-t013-20261028-001`。本地包装 `runs/referral-field-root/{live-control.sh,review-control.sh}` 与上一轮包装字节相同，没有新流程或自动重试。

## 全部真实尝试与终态

| attempt | 结果 | provider 请求 | 工具调用 | input / output tokens | 耗时秒 | 保守估算 CNY |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `p-b-20261028-001` | smoke_completed | 3 | 2 | 4,938 / 212 | 5.394 | 0.011572 |
| `p-c-t013-20261028-001` | completed_ungraded | 33（含确认 1） | 57 | 9,340,069 / 31,398 | 337.940 | 18.931322 |
| `p-review-t013-20261028-001` | complete，局部 4/4 | 1 | 0 | 54,843 / 3,196 | 17.857 | 0.135254 |

耗时口径沿用 O：B 为说明材料生成至清理，C 为 claim 落盘至清理，review 为目录创建至结果写出，均不含此前准备。费用沿用锁定账目峰值保守公式，含已报告生成用量，非实际账单或折扣后金额；Codex 开发代理用量另计。全部请求 settled、全部工具 returned，没有失败 API attempt 被省略；两次本地确认预检分别因候选观察不完整和选择引文未验证被拒绝，不算实际确认 API 调用，记录保留。

C 有 32 次主请求和 1 次确认；确认在第 8 次请求正常 stop，input=59,601、output=9,242，估算 0.193138（已含 C 总额）。第 32 次请求调用 claim_done，第 33 次输出最终答复；实际用到了原 30 次以后的额度，最后仍余 17，未触发低余额软提醒。32 条反馈均按此前已返回声明及共享计数重算一致。不能仅凭本次使用额外额度就把业务改善单独归因于 50 次上限。

完整终态独立核对为绑定目标患者，只有目标 1 case/1 service_request/1 submission，case=submitted、付款方 intake=in_progress，无其他患者的上述业务实体，无最终付款方 determination。建案时 Agent 实际传入 `service_type=rehab_therapy`、`site_of_service=office`；代码未代选/重写该字段，也未向 Agent 提供隐藏可接受值。确定性部分 **9/9 true**，包括上轮失败的 `new_referral.site_of_service`；DeepSeek 的 2 个 evidence/2 个 submission 项均 true。这里完成当前开发检查，不等于独立临床裁决、最终批准或官方 reward。

capture manifest SHA-256 `6f8be16bf293a5b162655d4cb59d0c1dd60bde7aeb5903b4654c62f591ffa4dc`。实际 run 的指导版本/整体 hash 与固定模块一致；主代理用固定官方公开函数及 FastMCP 元数据重新生成原 description，再追加指导，两个工具的原/后 hash 均与真实 journal 完全相符。实际 SDK wire 的序列化关系由前述固定 SDK 合成检查覆盖；本轮没有声称另抓取了每次完整 HTTP 正文。

### 全部工具调用

B 各调用 smoke_lookup、smoke_transform 一次；review 无工具。C 的 57 次如下，含已返回拒绝的本地调用：

| 工具 | 次数 |
| --- | ---: |
| auth.check_status | 2 |
| auth.finalize_provider_determination | 1 |
| auth.submit_authorization | 1 |
| cases.create_from_order | 1 |
| cases.get_case | 4 |
| cases.list_cases | 1 |
| chart.get_patient_chart_by_patient | 10 |
| chart.search_patients | 1 |
| docs.create_submission_bundle | 1 |
| docs.list_case_documents | 2 |
| docs.upload_evidence | 1 |
| forms.list_required_forms | 2 |
| forms.save_form_response | 1 |
| forms.validate_form | 1 |
| inbox.list_messages | 1 |
| local-claim_done | 1 |
| local-confirm-patient | 3 |
| local-fs-list | 7 |
| local-fs-read | 13 |
| local-fs-write | 1 |
| local-sleep | 1 |
| people.list_ordering_providers | 1 |
| 合计 | 57 |

### 开发评审的实际载荷核对

发送前按既有文档做禁网审计：`_input()` 来源/清理/已结算检查通过，固定官方文档的无真实患者数据/PHI 声明通过，全部配置秘密不在消息正文。仅发送 adapter 的 16 份内联材料、Agent 产物、4 项 rubric 和提示，不追加原始 world 或手册；未把评审结果回灌参赛 Agent。

完整 canonical HTTP 消息正文（不含认证 header）220,557 bytes，SHA-256 `ad64d562740c1552b6462ae417353966a5827b034e4d6af38683c00d7136a884`；内联 workspace 为188,600 bytes，SHA-256 `9a31dfc8abe454803fdf562dcb315fa03a579cb1cd1051bac35122b44638ecca`。审计证据 `review-payload-audit-t013.json`，两个 hash 均与实际 settlement identity 相符。本次凭具体证据获准一次评审，不作为全局外发豁免。

## 历史、费用与清理对账

主代理独立复核 32,188 个旧文件，只有 K accounting/controller/current-B 和 review accounting 四个允许指针改变；旧 B 原字节已归档，旧失败、claim、终态与费用保留。K/评审逐请求用量及估算与总账一致，两套 pending=null、controller clean；按精确 ID 复核两个 runner、一个 world、一个 network 均不存在，未操作其他资源。

本轮合计 **37 个已计量请求、59 次工具调用，保守估算 19.078148 CNY**。全历史累计 **356 个已计量请求 / 121.571472 CNY**，均非实际账单。从用户新增约 50 CNY 的规划起点扣除本轮后，按同口径尚余 **30.921852 CNY**，这是规划余量，不是账户余额；record_only/null 未改变。本项超过原建议预留，后续先缩减可选实验并重排，不因预留就花完。

证据为 `actual-summary-live.json`、`terminal-metadata.json`、`final-reconciliation-live.json`，对应脚本 `summarize_actual_live.py` / `reconcile_live.py`。原始 B/C/评审完整记录留在既有忽略目录。本次实际运行期间及完成后生产源码均与独立候选相同，无人工代选业务动作。

## 对照、限制与下一步

O 的 t013 为 28 请求/47 工具、312.140 秒、4,539,533 input tokens、估算 9.332018 CNY、确定性 8/9；P 为 33/57、337.940 秒、9,340,069 input tokens、18.931322 CNY、确定性 9/9。地点项本次恢复通过，但输入用量和保守估算约翻倍，不能称整体效率提高。相同参数的额外查询至少包括 cases.get_case 3 次、auth.check_status 1 次、docs.list_case_documents 1 次，表明仍有观察复用/上下文增长问题；尚未做因果归因或实际账单测量。

两轮保持同模型/思考、资源、预算、输出及确认配置，显式变化为本次工具指导；模型仍有随机性，且 t013 是已见开发题。单次 9/9、4/4 不证明指导有稳定因果收益、泛化或官方成功率。当前先收束 t013 开发验证，不再刷题；t019 保持付费暂停。

下一项按既有截止前计划准备正式可运行入口和提交包，复用已验基础，在有限预算内用正式入口的一次未见兼容题运行兼顾部署和迁移验证。重复查询/上下文成本作为后续有界改进候选，不因本次成本增加就临时加入大改或新 API 试跑。

PR #20 更新为可审阅交付，由用户决定合并。official_reward=null，原版 Claude、正式配送/F.5 的暂停不因本轮完成自动解除；正式入口保持原行为。原始资料、手册、vendor/data、轨迹、评审原文和秘密不上传。
