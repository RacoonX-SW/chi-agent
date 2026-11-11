# U 有界设计

## 已核对基线与职责

2026-10-30，GitHub PR #24 已 merged，merge commit 为 fd140bd805e906aa95c6afc1a1e76ab813c441e7；本次 fetch 后 origin/main 恰为同一提交，不将历史 SHA 自动当作最新。工作区干净，从该点建立 codex/harbor-launch-coverage。

固定官方 checkout 为 4444a07fa68a4f1623f841a292a54e284fc8e7f7。已读 experiment/runner.py 的 --agent-import-path 选择、agents/openai_agents_harness.py 的 BaseInstalledAgent/AgentContext/trajectory 接点、experiment/docker_env.py 的环境与 exec/日志/stop 接口，以及现有 go_chi_harness.py、包白名单与实际 runner 日志入口。官方 pyproject 的 harbor>=0.20.0 在 uv.lock 固定为 0.20.0；现有 SDK 卷无 harbor。旧 harness 测试用 FakeHarness，仅为合成单元证据。

本地操作者创建与捕获开发世界；独立参赛 runner 接收外部输入并自主调用工具；Harbor 加载适配器、调用安装/运行/上下文钩子并传播进程结果；官方 verifier 在运行后判分。包外操作者/覆盖盘点不得成为 runner 的依赖，也不得把隐藏材料挂给 Agent。

## A：真实组件与独立包

- 使用真实 Harbor 0.20.0 AgentFactory/import path、BaseInstalledAgent、AgentContext/ExecResult 和适用生命周期。不得替换这些类或伪造它们通过；原 FakeHarness 单测可保留并标明范围。
- 优先实际执行固定官方 ChiBenchDockerEnvironment 的 exec/文件/清理边界及真实角色 MCP。如果完整 Trial 可在 disable verifier 条件下执行，应优先取证；若仅验证组件子集，应精确列出未经过的 CLI/Trial/配送接点，不把组件通过写成完整 trial。
- 使用干净导出包，原源码目录不可见，包/官方 vendor/依赖/公开输入/输出分离。明确传入适配器 import path；stock CHI 名称注册与默认 key allowlist 不自动认识 Go，不能宣称 stock 直接支持。不得改 vendor、原 SDK/PDF 锁或官方评分器。
- instruction 必须来自调用方，角色与单一 MCP 对应，路径和身份预检先于凭据/发送。只安全注入 OPENCODE_API_KEY；测试使用专用合成值，不读取 .env 实际值。DEEPSEEK_API_KEY 等不得转发或改变宿主 os.environ。
- 验证真实 runner 的正常退出、外部指令/角色工具可见性、工具循环、标准结果/run output/trace/运行日志、context 用量及错误的一致性。金额缺失留 null，不从 list/allowance推算余额。非零退出、无返回码、无结果/损坏日志、超时/取消应保留错误证据；清理仅针对本轮拥有资源，主错/清理错分别记录。
- 日志读取有界且拒绝链接/重复key/非有限值；核对固定结果的typed用量、原instruction及最终输出与trace一致。真实Harbor trajectory必须实际生成并通过类型校验；其总用量来自全部已结算请求的run_result，不能只累加缺少工具轮usage的step记录而漏算，缓存/费用未知仍留null。预演driver不得吞掉与预期主错无关的恢复/清理异常，须单独核验finish、结果持久化及owned资源不存在。
- 需要新增接线时限于自有适配器、配套启动/运行说明、独立依赖安装和测试。复用 run_chi、SDK、ChiGuard/ChiJournal、工具契约、请求反馈、患者与角色门禁；不增加生产测试后门、自动重试或静默回退。原 evaluation_entry live 拒绝保持。

## Harbor 最小新增与隔离复现

新增仅用于宿主控制侧的真实 Harbor 组件，不升级 runner 依赖。首个已固定下载是官方 uv.lock 的 harbor==0.20.0 wheel，SHA256=4b7e48223aea2384cdb8c9eff35eaebd482fc9b1ec09f8193a121c47356ff19a。先在 Docker 内下载并按该 hash 验证、只读检查导入图，不安装其全部可选服务栈。缺少的传递导入只取必要项，优先同一官方 uv.lock 版本；实施安装前将准确版本/hash及范围补入本节/锁文件。完整 CLI/Trial 确需更多依赖时同样先固定再安装，不能静默解析最新依赖。

Docker只读导入图确认首批额外依赖如下，全部取自同一官方 uv.lock；使用 --no-deps/hash 校验，不解析最新版。已有 pydantic/httpx 等从只读原环境复用。平台范围为 Linux arm64/Python3.12；其他平台未验证。

| distribution | version | wheel SHA256 |
| --- | --- | --- |
| shortuuid | 1.0.13 | a482a497300b49b4953e15108a7913244e1bb0d41f9d332f5e9925dba33a3c5a |
| toml | 0.10.2 | 806143ae5bfb6a3c6e736a764057db0e6a0e05e338b5630894a5f779cabb4f9b |
| Jinja2 | 3.1.6 | 85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67 |
| MarkupSafe | 3.0.3 | 3a7e8ae81ae39e62a41ec302f972ba6ae23a5c5396c8e60113e9066ef893da0d |
| pathspec | 1.1.1 | a00ce642f577bf7f473932318056212bc4f8bfdf53128c78bbd5af0b9b20b189 |
| dirhash | 0.5.0 | 523dfd6b058c64f45b31604376926c6e2bd2ea301d0df23095d4055674e38b09 |
| scantree | 0.0.4 | 7616ab65aa6b7f16fcf8e6fa1d9afaa99a27ab72bba05c61b691853b96763174 |

pathspec 为真实 Trial → job.lock → publisher.packager 的必要导入；不使用发布能力、不上传运行产物。
dirhash 为真实 Trial._init_result → Task.checksum 的必要导入；scantree为该包的固定传递依赖，复用已有attrs/pathspec。

固定官方 Docker environment 调用 docker CLI，而既有dev/controller及核对的两个工具镜像无该可执行物。控制侧另用 Docker 官方静态 `docker-28.5.2.tgz`（Linux aarch64，来源 `https://download.docker.com/linux/static/stable/aarch64/docker-28.5.2.tgz`），Docker内下载的归档SHA256为 `9e4f82996ab790724094475ebed33a736434bfe5d45231b676fef22ffb80044d`。仅提取 `docker/docker` 客户端到本轮隔离目录并按归档hash门禁；不安装归档内daemon，不修改已有镜像或依赖。此hash是固定下载字节的身份记录，不声称独立签名认证。仅控制侧挂本机既有engine socket执行本轮生命周期；runner没有socket/CLI。

使用新的本轮 Harbor 目录或专用卷；旧 model/PDF 卷只读挂载。记录 Python3.12、平台、镜像、发行版/源码与依赖身份；隔离重建这一新增 overlay，不能称重做 G/H 或完整重新安装已通过 SDK。开发/自测/下载/安装/运行一律 Docker；源码与文档可在宿主编辑。所有成功与失败安装/探测日志保留在忽略的 runs/harbor-launch-coverage-root/。

## 本轮模型调用清单与停止规则

当前固定清单为 **真实模型请求 0、真实业务任务 0、Claude 0、Go 付费临床评审 0**。真实组件启动预演使用合成 HTTP 响应与合成公开说明，明确测试 seam；真实 MCP 至多进行无副作用只读访问，不重演 t012/t014/t017，不称真实任务通过。此层证据可直接验证类型和加载，无需为接线变更重做一次临床任务。

启动演练固定三个真实 `SingleStepTrial` 场景，均 `verifier.disable=true`：provider真实独立runner合成模型只读工具闭环正常退出；合成非零runner退出；成功码但缺失/损坏日志的失败传播。复用现有t018镜像的全新临时世界、合成外部instruction，仅为启动组件演练，不解题/写业务/产生成绩。payer/cm在本轮拥有的同一世界进行真实角色MCP只读schema/工具核对，不另选业务题。必要coding-B由实际入口/守卫和合成HTTP自然生成收据，不能伪造。实现者开发尝试与主代理固定候选后的独立复验各保留全部记录；主代理复验重建本轮拥有资源，不复用已变世界。HTTP mock/进程启动测试shim仅在测试侧，不能加入生产包或解除门禁。

真实Trial使用本地测试衍生镜像：FROM固定原world（`000ca5096533`对应完整digest见T报告），只加入干净独立包、固定vendor git checkout、原只读model/PDF源的快照及test-only Python/HTTP shim，不安装/升级依赖。实现者tag为 `chi-agent-harbor-synthetic:rehearsal` / `:with-b`；后者仅把实际合成coding-B生成的测试账目/收据作为同候选场景起点，每个Trial仍创建自己的新容器。主代理独立构建另名镜像并重新自然生成B，不使用实现者已变世界。原镜像tag不覆盖；含受限原资产的所有测试镜像均只留本地，不作配送/发布产物。

Key仅从控制器运行时进程环境安全注入，不把它放在 `AgentConfig.extra_env` / `--ae KEY=value` / TrialConfig，因为Harbor会持久保存配置。metadata可经extra_env传入，适配器暴露给Trial执行作用域的extra_env须为空；无关调用方执行环境污染需在派发前拒绝。演练使用专用合成值并检查配置/异常/debug/trajectory不存在该值；不读取真实.env。

若独立审核发现合成验证确实不能覆盖的模型协议缺口，主代理须在任何新请求前按用户既有 Go 开发授权修订本节，固定唯一必要用途、任务/次数、候选/包/条件和停止规则。未修订前不调用；不因额度充足扩张。新身份所需 B 最多一个 coding 工具闭环、6请求/1024，不与任务50请求/主8192/确认32768/最多2确认混用。当前没有授权执行清单中的 C，不通过重跑三题补启动证据。

实际 Go 模型继续 deepseek-v4.1-flash，base URL https://opencode.ai/inference/go/openai/v1；record_only/null cap，费用三项 USD 分列，不与旧 CNY 相加。Extra Usage 已由用户关闭，不开启。可信 tokens/结果未知、证据损坏、未清理资源、明确非 Go/余额额外实扣仍停止，零自动重试/回退，不自动留档新的未知。十一月隐私条件按实际日期人工复核；仅 DeepSeek 官方直连受既有避峰，OpenCode 可全天，无程序日历门禁或后台唤醒。

## 历史只读审计

按现有实现审计真实 Go 历史、每个 attempt/wire/seal、来源转换和唯一旧超时的完整 acknowledgement 链。T 已批准并执行的旧 s-go-v2-c-t012-1-20261029-001 第9请求保留未结算，active pending/halt=null；不能重复留档、settle、删除占位或当作新的全局阻断。不调用变更历史的命令。盘点前后保留原字节/hash，原 native/CNY 不写。任何不一致先保留诊断并调查。

## B：既有三题评分覆盖

仅使用 T 的 t-go-fee-c-t012/t014/t017-20261030-001 已留存初末 capture、resource snapshots、manifest、orchestration、工具及账目证据。输入先校验任务/资源/世界/终态/清理/hash 来源；盘点输出放新目录，旧结果只读。允许离线调用官方纯检查/构建 rubric 元数据，禁止调用模型或启动新世界。

从固定 task_runtime.collect_all_verifier_checks(include_semantic_judge=False)、适用阶段检查及 PaUmJudgeAdapter/contract_v5 rubrics/评分聚合路径建立要求映射：

- 已验证：具体程序/字段/流程/资源归属或执行证据，并写清是原版函数检查还是额外本地审计；不能从若干 checks 推出全部 rubric 已过。
- 尚未验证：材料存在不等于内容正确，临床证据/医学必要性/材料一致性等需模型评审的项；官方环境/完整 judge/聚合未执行项列明，official_reward=null。
- 不适用：由角色、任务 kind/contract、终态 action 和官方分支确定，不能把未做当不适用；保留不适用原因。标明检查项数与 rubric 数没有通用换算，不计算假通过率。

完整 rubric 及患者/隐藏内容只留操作者本地，报告只提供允许披露的 ID/类别/计数、源码路径、证据路径/hash与结论；不把该盘点脚本、expectations、原始世界或评分 workspace 放进参赛包。产出下一步需要哪些验证的明确结论，不自动选择/下载/执行后续三题。

## 验收与交付

一个 Terra/high 实现者，停止写入后主代理固定候选，按 diff/真实源码独立审核。重点测试真实加载与类型、成功/失败/异常 cleanup、最小凭据隔离、角色/MCP、日志/context、包独立性、历史链与覆盖来源；无关 G/H 不重复。必要失败及修复均写一份新阶段报告。

README 只写运行，OpenSpec 写边界/场景，学习账本记录职责/调用链/取舍及下一入口，不升级用户掌握；唯一 REVIEW_STATE 更正 PR24 已合并和本轮状态。详细环境/证据/身份/费用/限制仅写 reviews/harbor-launch-coverage-review.md。显式提交/推送 codex 分支、创建 base=main PR 附到本 chat，用户合并，不 auto-merge。
