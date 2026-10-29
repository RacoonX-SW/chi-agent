# R：Go CHI 正式入口与独立包审核

日期：2026-10-29（Asia/Shanghai）。新入口的离线技术审核及真实 B 通过；唯一真实 CHI 尝试因确认工具混批而中止，业务验收未通过，操作者还遗漏了该次世界终态捕获。下面分别记录证据及限制，不将接线完成写成任务成功。

## 基线、授权与事实核对

GitHub connector 实际核对 PR #21 为 closed/merged，合并提交为 `d5fa0508618ced14aae012dbf6f47143090d041e`。fetch 后最新 `origin/main` 与之相同；本地原 `codex/opencode-go-provider` 无未提交改动，写入前从最新主线新建 `codex/chi-go-evaluation-entry`。没有向已合并分支追加开发，没有 merge/auto-merge。

本轮 [有界规格](../openspec/changes/chi-go-evaluation-entry/design.md) 恢复正式技术接线及必要 B/一次冻结 C；t013 收束、t019 例行付费复测暂停、原版 Claude/F.5 最终配送仍暂停，official_reward=null。用户明确知道 Go 的非编码用途支持未确认，决定按实际开发用途继续使用；该决定不写成官方许可。Extra Usage 沿用用户已确认关闭，程序不修改服务设置。

已读固定上游 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 的 harness/runner、本地工具、角色 catalog、custom harness 说明及 submission/runner 接点：官方 harness 从任务配置取 MCP URL、写公开 instruction 文件，再启动 runner；默认原 harness 不会自动选中本项目 Go guard。正式包必须明确外部输入/资源与自有入口的运行方法；本机 K 开发世界调度成功不等于正式包可运行。

2026-10-28 至 29 读取官方 [Go 文档](https://opencode.ai/v2/docs/console/go/)、[Inference usage](https://opencode.ai/v2/docs/console/api/inference/) 和 [服务条款](https://opencode.ai/legal/terms-of-service)：路由/ID/客户端会话头及三项 USD 含义已明确；文档仍要求典型 coding agent 流量，没有找到非编码 CHI 支持确认。DeepSeek ZDR 按月续期，当前只明确到 2026-10-31，十一月条件仍需运行前人工复核。不伪装业务请求，不修改模型 ID、不加 `[1m]`，没有百万 token 实测。

## 实现与实验条件

一个 `gpt-6.1-terra / high` 实现子代理。首次启动返回 Codex 用量限制，尚无写入；用户要求继续后，接续同一代理成功，未静默换模型。主代理维护规格、独立审核、教学和 GitHub；同一目录只由该代理写实现。

未见验收题在查看详细业务输入前，按固定索引兼容字段及字典序规则选定 `pa_t012_t012_o001_p01_new_referral_provider`，排除八个既有开发/已读任务。它是当前 submit 路径兼容子集的一题，不是随机总体样本；候选、提示、依赖及运行条件详见规格，不因结果换题。选择元数据与必要五文件 hash 保存在忽略目录 `runs/chi-go-entry-root/evidence/{task-selection,frozen-resources}.json`；只下载该题必要文件，不下载整套任务，不向实现代理/运行模型提供隐藏评分内容。

使用已有 Python 3.12 镜像与 SDK/PDF 卷，不重做 G/H 安装，不重建镜像或改锁。禁网 Docker 已核对 `OPENCODE_API_KEY` 和 `DEEPSEEK_API_KEY` 均存在，只输出布尔值；保存了本轮开始时 **48,347** 个既有 data/runs 文件的 SHA-256 清单，供结束时核对旧证据未改。

## 全部尝试与工程故障

以下为环境/准备失败，不能记成业务失败、C 失败或模型请求：

- 首次普通 sandbox 的 `git fetch origin` 因 `.git/FETCH_HEAD` 写权限失败；按既有 Git 授权提升后 fetch 成功，未丢弃改动。
- Docker 起初可读到已有镜像/卷，随后 Desktop 引擎关闭；实现者首次自测及主代理检查因 socket 不存在失败。主代理启动已安装 Docker Desktop 后引擎就绪（29.5.3），无安装/重配置，后续继续容器内验证。
- 必要资源下载第一次选了 controller 中的 dev 解释器 `/opt/venv/bin/python`，缺少 `huggingface_hub`，在 import 处终止，没有下载/API。读取 Dockerfile 后使用既有 `/opt/a-venv/bin/python` 成功取得五个固定文件，未新增依赖。
- 几次只读源码定位命令命中不存在路径或 shell glob 无匹配，改用 `rg --files`/实际路径后读取；未改变源码或环境，也没有运行任务。

具体离线候选、独立检查和真实 B/C 结果见下文；这些准备故障没有产生 provider 用量。

## 首个固定候选的独立审核

实现者停止写入后，主代理显式暂存 28 份代码/配置/测试/规格/runbook 并固定候选 `8015badebfa1deefda7424530a4e26d27749ca43`。旧 Q/native 源码未改。主代理阅读新增入口、Guard、账目、完整历史契约、MCP/本地工具、运行循环、角色路径和 harness；包构造器与既有 G/H 构造器的差异仅为固定允许文件及包身份，不重新安装或重复 G/H 历史验收。

`git archive` 只读快照、空 tmpfs data/runs、禁网、无 Key/socket、外部固定 vendor/SDK/PDF 的全量检查为 **389 passed / 146 subtests passed，20.56 秒**。第一次容器初始化缺少快照中的空 vendor 挂载点，退出 125、没有执行 Python/API；补齐空挂载点后上述检查通过，两份日志均保留于 `runs/chi-go-entry-root/evidence/pytest-8015bad*.log`。

测试通过仍未验收：独立合成脚本复现了两项应在真实 API 前修复的问题，证据 `first-findings-8015bad.json`：

1. 已知费用的非法模型响应正确先结算再拒绝，但只留下 request hash、token 和三项 USD，缺少安全请求/响应正文、response hash、原 usage 和逐请求耗时；SDK 失败时也没有完整 trace，不能离线复现该协议故障。工具记录只有成功返回 hash，不能完整说明开始/拒绝/失败。
2. 一次有明确 `CallToolResult(isError=True)` 返回的业务错误被提升为 `chi_mcp_tool_failed` 并 poison 患者绑定，模型收不到错误、没有工具返回记录。它与网络失败/未知副作用需要分别处理；可信业务错误应回到 Agent 自主决策，不能自动重发，也不更新患者关系。

已交回同一实现者按 R1/R2 返工：安全且有界的逐请求/工具证据与完整性审计、标准安全日志，以及可信业务错误回传。该候选仅通过上述全量测试，独立审核未通过；尚未发起真实 B/C，费用为零。

同一候选的追加合成检查 `more-findings-8015bad.json` 确认：第 51 次确实没有派发，但被归类为 `chi_request_invalid`，应明确为请求耗尽；确认子请求的可信 `length` 响应虽已结算，却在 Guard 被当作协议错误中止，使本地截断处理不可达。这两项以 R3/R4 窄修，不放开上限、不自动重试、不绑定未确认患者。

主代理另外在禁网容器内用真实 loopback Streamable HTTP 完成初始化、list_tools 和一次合成工具调用，provider 请求为 0。前两次检查错误地要求返回必须有 `structuredContent`，实际 SDK 合法返回 text content；保留失败并修正检查后通过，未因此修改生产代码。证据 `streamable-loopback-8015bad{-shape,-pass}.log` 与 JSON；它是协议证据，不是官方业务世界或三赛道能力验证。

主代理还将 Q 首次真实尝试留存的三份响应，通过该候选的 `ChiGuard` 和锁定 SDK 禁网回放：两个纯工具完成、三份序列化后请求 JSON 与原发送记录逐项一致，缺失可选终态 reasoning 的响应可接受；没有新增 provider 请求。证据 `q-replay-8015bad.{json,log}`。这证明兼容旧真实响应的范围，不抵消 R1–R4，也不替代新源码的真实 B。

实现者自测的全部失败另保留：一次 Docker 内探测语法错误、两次 SDK UA 不符、一次 reasoning route 不符；一次误用 unittest 收集 pytest 文件得到 0 tests/退出 5，改 pytest 后 25 passed。首个全量自测的只读 runs 使四项旧 mock 测试 EROFS（385 passed），提供空可写 tmpfs 后才得到完整通过。它们都是离线工程检查，不是业务 trial。

R1/R2 返工曾被 Codex 用量限制中断；用户明确要求继续后，沿用同一 Terra/high 接续，已写改动保留，没有换模型、宿主运行或后台等待。随后实现者一次 Docker 自测自动审批因 usage limit 无法完成，命令未执行；这不是安全拒绝。主代理已用同一授权 Docker 工具完成只读引擎检查，并通知实现者继续；不绕过安全审批。初候选的自测日志已复制到 `evidence/selftest-8015bad/`，避免接续时被新日志覆盖。

## 返工候选的独立通过范围

同一实现者完成 R1–R4 后停止写入，主代理显式提交为 `5b60b3122bf8c689b47750c5681a7a5a188d8443`。主代理阅读新证据模块、账目与 Guard 完整性/中断流程及受影响入口/工具差异，确认旧 Q/native 源码保持原字节。实现者一度因新增条件括号错误有五项测试收集错误，修复后才完成自测；失败日志与最终自测已保存在 `evidence/selftest-5b60b31/`。

主代理从该 Git archive、禁网、无 Key/socket、只读源码/依赖及空 tmpfs 状态独立得到 **404 passed / 150 subtests passed，17.84 秒**。新增独立检查也通过：

- 已知用量但内容拒绝：先结算，安全请求/响应、原 cache/reasoning usage 和耗时保留；改写响应证据后阻断。
- 明文及 JSON 转义秘密回显均整段红删；取消/缺用量只派发一次且阻断下一 attempt。
- 50 次可发送，第 51 次诊断明确为 `chi_request_limit`；确认的可信截断返回本地处理，未伪造完成。
- 真实 MCP 错误 DTO 经真实 SDK 循环进入下一次模型观察，后端只调用一次，最终回答明确未完成；没有自动重发。
- 三份旧 Q 响应再经新 Guard/SDK 回放，请求 JSON 仍逐项一致，缺失可选 final reasoning 可接受。

证据为 `pytest-5b60b31.log`、`guard-boundaries-final.json`、`sdk-error-final.json`、`q-replay-5b60b31.{json,log}`。这些都是合成或已保存响应回放，provider 新请求为 0。

主代理另从固定源码重新导出 **29 个允许文件及 manifest**，manifest SHA-256 `a98144980f9a20a3ad920ce5a19b883d36dc00f9259da9d9fece708e8e86f406`；完整运行身份 `35c1eced6ca6d2121b125296ccbc7a56187a69da516f8b9ecc71b539bd867434` 绑定包、SDK 版本/源码、固定上游与 PDF。包在原工作区不可见、cwd=/tmp、`/usr/local/bin/python -S`、包只读、外部 vendor/SDK/PDF 的环境中独立预检通过。十项实际入口检查验证错误包身份、fixture、编码、链接、FIFO、health URL、已有日志、缺 B/Key 和重复 attempt 在适当阶段拒绝；对 Key 读取做了观察，缺 B 之前没有读取凭据，重复身份没有覆盖账目。见 `preflight-5b60b31.json`、`entry-boundaries-final.json`。

证据正文独立文件有界保存并以 hash 引用；无法解析/超限或包含秘密时只保存 hash、原因及可信安全元数据。CHI 汇总账目使用独立 32 MiB 读取上限，并有超过旧 1 MiB 的合成历史回归；达到上限保守阻断，不删账。源码身份改变当前只拒绝，不自动迁移；完整 Harbor 类型/配送仍未验证。

## 真实验证前置与新 B

真实执行前禁网审计 1,323 份包/公开输入/授权手册/固定初始世界资源，共 35,613,485 bytes，两个配置秘密均不在这些内容及 B 固定请求样例中；只输出 Key 存在性。五份 t012 必要资源全部 hash 复核，Go 旧账副本完整审计通过，各旧 pending=null。新 CHI 本地目录此前不存在，使用固定 `Q/chi-evaluation` 子目录并在整个运行持旧 Q 锁；原账不清零。证据 `prepaid-b.json`、`frozen-candidate.json`。

唯一新 B `r-go-b-20261029-001` 从上述只读导出包、cwd=/tmp、Python -S 启动，接收 Go Key，不接收任务/手册、native Key、`.env` 或 socket。运行成功，3 请求、2 次纯工具、input 1,398 / output 126；从操作者建立本次记录到 runner 清理完成 **7.277 秒**。provider 返回余额实扣 **0 USD**、价目价值 **0.0001724 USD**、套餐消耗 **0.00012931 USD**，三者不相加。B 收据、证据/seal 和无 pending/halt 已在 C 前独立复核；runner 已删除。该 B 不证明 CHI 业务能力。

## 唯一真实 C：已接通，但业务验收失败

`r-go-c-t012-20261029-001` 使用同一只读独立包和运行身份，在新建原版世界执行预先冻结的 t012，运行期间无人选择业务动作。主程序实际发送 **4** 次请求，input **249,955** / output **1,518**；确认子请求 **0**，`claim_done=false`，无最终输出，退出 1，诊断为 `chi_confirmation_batch_invalid`。从操作者建立记录到 runner/world/network 全部清理为 **35.716 秒**，其中世界 readiness **5.575 秒**；四个 HTTP 往返耗时依次为 5,074 / 6,363 / 7,312 / 8,287 ms（不含 Guard 后处理）。

前三轮完成 **11** 次工具调用：`local-fs-read` 4、`chart.search_patients` 2、`chart.get_patient_chart_by_patient` 5，均有 started/returned 及完整证据。第四轮模型在一个批次同时提出 `local-confirm-patient` 和两个 `local-fs-list`，完整批校验拒绝了整批，三个调用均未派发，没有部分副作用或自动重试。已执行的工具均为读取，轨迹没有业务写入调用；但缺少世界终态，不能把这句话升级为对完整世界非目标写入的权威核验。

主代理回读旧 `live_development._validate_live_response()`：患者确认混批本来就整体中止；`patient_identity_binding.CONFIRM_DESCRIPTION` 已明确要求 call this tool alone。新 `go_chi_runtime.run_chi()` 保留该门禁。因此这是模型违反既有调用约束的失败，不是新接线回归；没有删除门禁、改题、补选动作或为求成功追加 C。t012 从本次之后属于已见开发材料，后续不能再把它作为干净的未见题证据。

该次余额实扣 **0 USD**、价目价值 **0.03825352 USD**、套餐消耗 **0.02869014 USD**，四份请求均可信结算。`post-run-audit.json` 已按运行身份完整验证新账目、wire/tool 证据、诊断、run seal 和 B receipt，旧 Q 副本完整审计通过；CHI/Q pending 与 halt 均为 null，native 两本旧账 pending=null。原失败 attempt/claim、费用和证据保留，不换目录绕过。

操作者捕获另有独立工程故障：控制镜像的 `/opt/a-venv` 有 Docker 调度依赖，但 `_capture_review_input()` 延迟导入的 `b_provider_transport` 需要 `httpx`。首次 C 控制容器未挂 SDK 卷，runner 停止后捕获在 import 处抛 `ModuleNotFoundError`，清理前未保存权威终态；外层只保留异常类型，不能据此覆盖 runner 已明确记录的混批诊断。世界已经删除，本轮没有伪造或补写原终态，适用确定性业务检查及完整非目标检查均记为 **未执行/证据不足**，没有调用开发评审或 Claude。

主代理复用已有 SDK/PDF 卷修正操作者环境，先禁网导入捕获完整依赖，再在**另一个全新初始世界**验证真实 export/fixtures/shared-world 捕获及 hash 绑定，**6.174 秒通过**（readiness 5.553 秒），世界/网络已清理；无 Agent、无 Key、无模型/判分请求。这只证明修正后的捕获流程可用，不能恢复原 C 终态或改写它的结果。证据 `capture-check/result.json`、`evidence/capture-only-check.log`；原操作者脚本及冻结 hash 不覆盖，新检查脚本单独保留。核查时一次未挂 SDK 的禁网账目审计也在 `import httpx` 处终止，补齐既有卷后完整审计才通过；无新增调用。

## 环境、包与用量口径

实际复用 Python **3.12.15 / Linux arm64**。dev 镜像 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，controller `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，world `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`。世界初始资源 SHA-256 `7d77133c451396332bc8df08e957bbf57d0132acd4941c850c89e3a02fd1aa2b`。controller 使用 `/opt/a-venv/bin/python`，独立 runner 使用 `/usr/local/bin/python -S` 和只读外部依赖。

已有 SDK 卷 `chi-h-root-model-deps-20261027-v1`：openai-agents 0.13.6、openai 2.36.0、httpx 0.28.1、mcp 1.30.0、jsonschema 4.26.0、pydantic 2.14.1、pydantic-core 2.50.1、httpcore 1.0.9；PDF 卷 `chi-k-pdf-deps-20261027-v1`，pypdf 6.20.1。完整 SDK 源码/PDF hash 在预检身份内。没有安装/下载新依赖、改锁或重建镜像；完整 Harbor 包在现有镜像中未安装，薄适配器仅以 stub 验证接口，不能写成完整官方 harness 配送实测。

独立复验命令使用 `docker run --rm --network none --read-only`、只读 `git archive`、空 tmpfs data/runs、`PYTHONDONTWRITEBYTECODE=1` 和外部 vendor/SDK/PDF；全量入口为 `/opt/venv/bin/python -m pytest -q /workspace/tests`。包导出/预检/运行参数见 [runbook](../docs/go-chi-entry-runbook.md)，实际 B/C 的完整无秘密命令、mount 目的路径、凭据变量名和清理记录保存在 `evidence/actual-config-{b,c}.json` 与 `actual/<run-id>/orchestration.json`。runner 只收到 Go Key；不挂 `.env`、socket、native Key、fixtures、expectations 或完整 world，MCP 只选 provider。控制端与参赛 Agent 的材料可见性分别审查。

| 范围 | 请求 | input / output tokens | 余额实扣 USD | 价目价值 USD | 套餐消耗 USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| R 新 B（成功） | 3 | 1,398 / 126 | 0 | 0.00017240 | 0.00012931 |
| R 唯一 C（失败） | 4 | 249,955 / 1,518 | 0 | 0.03825352 | 0.02869014 |
| R 合计 | 7 | 251,353 / 1,644 | 0 | 0.03842592 | 0.02881945 |
| 原 Q 两次尝试（含失败，保留） | 6 | 2,744 / 214 | 0 | 0.00031420 | 0.00023565 |
| 项目已留证 Go 合计 | 13 | 254,097 / 1,858 | 0 | 0.03874012 | 0.02905510 |

三项 USD 是不同口径，不相加；`input_tokens` 是 Chat Completions prompt 总量，不冒作缓存未命中量，原 provider cache/reasoning usage 在 wire evidence 保留。订阅固定费与账户其他消费不包含在表中，未查询控制台剩余额度或据此推断套餐余额。旧 native 开发账 **119.990746 CNY**、评审账 **1.569062 CNY** 及先前 **0.011664 CNY** 证据保留，历史保守累计 **121.571472 CNY**；不与 USD 换算相加。Codex 开发代理用量与订阅固定费不计入模型运行 API 表。零自动重试、无 fallback、无 Extra Usage 修改。

## 交付结论与接续限制

当前 `5b60b31` 通过的是独立包/新入口离线技术范围和该身份真实 B；真实 C 证明包能读取外部公开输入、连接原版 MCP、经 Go 完成模型与读取工具往返，也明确留下模型混批失败。它没有完成患者确认、业务提交、正常最终回复或业务验收；不能声称通用能力改善、三角色真实业务通过、完整正式配送或竞赛成功。Go 开发评审没有切换，旧 `evaluation_entry.py live` 拒绝继续保留。

本轮必要 B/C 已按界限执行，不追加第二个付费尝试。后续若研究混批恢复，应作为独立通用改进先制定规格并离线验证，不在本轮直接移除门禁；源码变化还需显式审计的 CHI 身份接续机制和对应新 B，当前 journal 对新身份保守拒绝。独立外部 evaluation 的声明也不能证明账户历史清零。

十一月 DeepSeek ZDR 条件、非编码用途确认、完整 Harbor/F.5、跨任务/三赛道迁移、真实硬取消/daemon 故障与官方评分仍未验证；t013/t019/Claude 暂停保持。原始 trace、五文件资源、捕获与本地包只在忽略目录，不上传；最终旧文件完整性、包归档及上传检查在下节记录。

## 最终完整性与存储检查

Docker 结束审计逐一复核开始时 **48,347** 份旧 data/runs 文件，全部原字节不变；秘密检查覆盖本轮新资源、证据、包、操作者脚本和待上传自有文件，**235 files / 16,255,699 bytes** 通过，两个 Key 只确认存在、不输出值。全部新请求结算，费用汇总与上表一致。首次审计把仓库相对路径误当容器绝对路径，文件存在断言失败；修正操作者路径映射后完整通过，保留 `final-integrity.log` 和 `final-integrity-final.log` / JSON。带 R 所有权标签的 Docker 容器与网络最终查询均为空。

本地交付归档为 `runs/chi-go-entry-root/exports/chi-go-entry-5b60b31-bundle.tar.gz`，**119,594 bytes**，SHA-256 `133c8adb48ee84d72ffdd08fc679b4dade8b0483508d5871d820e07ead9e531a`。它包含 29 份允许文件、manifest 和必要空挂载目录，Docker 解包后 manifest 校验通过，与真实 B/C 的包身份相同。首次归档遗漏空 `vendor/chi-bench` 挂载目录，解包树校验失败；保留该首个未交付归档 `chi-go-entry-5b60b31.tar.gz`，随后只修正操作者归档过程，未改源码/包身份/候选或重跑 B/C。交付归档不含 vendor 内容、数据、手册、凭据、账目或原始轨迹；外部依赖/资源仍须按 runbook 挂载，不能当完整 F.5 自包含镜像。

操作者审计脚本与两次实际命令在忽略的 `operator-audit/` 保留；没有另建交接文件。仅显式暂存自有代码/测试/规格/runbook/README/学习账本及唯一状态与本报告，最终 **34** 份待上传文件的路径允许范围、UTF-8 与配置秘密缺席检查通过，`git diff --check` 通过。推送前再次 fetch，`origin/main` 仍为本轮基线；存储提交不替代受审实现或改变包身份。PR 创建结果只维护在 REVIEW_STATE，用户决定合并。
