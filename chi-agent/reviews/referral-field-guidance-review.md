# 公开字段依据提示与付费验证收窄

日期：2026-10-28（Asia/Shanghai）。PR #19 已核对合并，基线 `a1aa625c3b9fbc36df2fd6bf57e67787b5f2e526`，新分支 `codex/referral-field-provenance`。同一个 gpt-6.1-terra/high 实现并 Docker 自测，主代理负责规格、固定候选、独立审核、教学和 GitHub。

固定实现 `ed15c2bcfae7076f1165c92b6bf52b3fa16caa65` **离线实现验收通过，t013 的真实效果未验证**。本轮在用户禁用时段内，只完成离线工作，没有新增真实 B/C/评审，没有重跑 t019。P.4 保持未完成，不能称 t013 已修好。

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

## 真实调用与旧账接续

2026-10-28 17:24（北京时间）仍在用户禁用窗口，按用户要求只用文档执行时段规则，不增加程序时钟门禁，也不后台等待/自动唤醒。当前付费工作如下，未启动不算失败尝试：

| 项目 | 本轮状态 |
| --- | --- |
| P rebind 与新源码 B | 未执行，旧 B 不代替新源码前置 |
| t013 新世界 C、完整终态/确定性检查/DeepSeek 评审 | 未执行，留待允许窗口 |
| t019 付费 C/评审 | 按用户指令暂停 |
| 真实 provider 请求/业务工具调用/tokens/耗时/新增 API 费用 | 均为 0；不含 Codex 开发代理用量和离线计算 |

主代理在禁网只读 Docker 中复核旧请求明细与两套账目：全部已知请求仍 settled、两套 pending=null、controller clean；K/review 用量与估算合计与 O 最终对账一致，仍是 **319 个已计量请求 / 102.493324 CNY 保守估算**，非实际账单。本轮没有 rebind、清零、重写旧失败/claim，也没有把新源码归入旧 B；旧 accounting 与 current B 仍绑定 O 身份。证据 `audit_accounting.py` / `evidence/candidate-1/accounting.json`，四个当前控制文件 hash 已记录。这里核对账目/旧候选来源，不用新源码 `_input()` 误读旧捕获身份。

## 接下来怎样验证

允许时段且源码仍为已独立审核候选时，依次 rebind 接续旧账、必要新 B、一次 t013 新世界独立 attempt、完整终态、确定性部分和一次 DeepSeek 开发评审。先按既有流程离线核对评审载荷的固定模拟来源/秘密缺席，未知用量仍阻断，不自动重试。若失败，保留全部结果并分析，不因目标是 t013 就刷到全通过；不同时恢复 t019。

与 O 对照时，除本次工具 description 指导外保持模型、任务资源、50 次共享限制、输出与确认配置不变，检查服务字段、完整目标结果、非目标患者副作用、正常收尾及用量/成本。即使 t013 再次局部通过，也只是已见开发题回归；单次结果不证明泛化或成功率，提示接入本身更不证明业务已修复。

本次以 base=main draft PR 提交离线候选供审阅，P.4 的真实验证明确待办。official_reward=null，原版 Claude、正式配送/F.5 继续暂停；正式入口保持原行为。原始资料、手册、vendor/data、运行轨迹、评审原文和秘密不上传。
