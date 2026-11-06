# Go CHI 独立程序包运行说明

本说明随新的 Go CHI 包分发。正式最终配送及 F.5 冻结由项目审核状态另行管理；主办方原 stock harness 不会自动选择本包，调用方须将本包入口作为自有 runner 接入。旧 evaluation_entry 的离线入口和拒绝行为分别保留。

## 运行环境与外部输入

使用 Python 3.12 和包内锁定的 SDK/PDF 依赖；安装、调试和运行在 Docker 中。当前目标平台为 Linux arm64，其他架构须单独核对锁与安装。已有 `chi-agent-dev:latest`、SDK/PDF 卷可直接复用，无需重做 G/H 空卷安装。包只含允许分发的自有源码、配置、依赖锁和本说明，不包含 `.env`、vendor checkout、任务数据、手册、开发账本或运行轨迹。

调用方在包外提供固定官方源码、公开 instruction 文件、所选角色的 Streamable HTTP MCP URL、授权资源和可写日志/持久状态目录。provider、payer/UM、CM 的默认 MCP 端口分别为 8020、8100、8200，8023 是 health 服务；跨容器调用时传实际可达的主机名，不能把另一个容器的 localhost 当本地端点。每次只连接选择的一个角色，不汇集三方工具。

Agent 可见资源只包括公开 instruction/工具参考、已授权的 managed-care handbook，以及当前角色/shared workspace。fixture、expectations、完整原始 world、评分材料和开发评审目录不挂给参赛程序的文件工具。凭据只注入需要发请求的进程环境，Go 使用 `OPENCODE_API_KEY`；原 `DEEPSEEK_API_KEY` 保留在本地配置，不转发给 Go 运行进程。

## 固定协议、停止和账目

运行模型固定 `deepseek-v4.1-flash`，SDK base URL 为 `https://opencode.ai/inference/go/openai/v1`，thinking/high，不追加 `[1m]`。文档标称上下文不等于实测百万 token；自有 User-Agent、每对话稳定 session、TLS、禁用代理/redirect/自动重试均是接点的一部分。

自主任务的 SDK turns 上限为 50；main、患者确认、summary 与 continuation 共享最多 50 次 provider 请求，患者模拟保持原独立计数。患者确认最多两次。主请求及 continuation 输出上限 8192，确认 32768。可信剩余次数按实际已发送数刷新；一次 SDK 模型步可能包含摘要子请求或受控 continuation，工具次数也不等于模型请求数。coding B 仍是独立固定探针合约，最多 6 次/1024 输出，不进入恢复器，不作为临床业务成功证据。

可选输入摘要默认关闭。包内 `live --input-summary chi-input-summary-v1` 保留旧单次生成上限 8192；显式 `chi-input-summary-v2` 的单次 summary 生成上限为 32768，thinking/high、选区、候选结构和时间窗口不变。两版本都每 run 最多一次 summary，计入共享50且须留后继 main；仍与输出恢复/Y shadow互斥。较大生成上限包含reasoning，不要求最终摘要变长：完整候选JSON仍最多32768 UTF-8 bytes（不是32768 tokens）。length、无效候选或未知按原规则停止，不续写或重试。较大窗口可能增加耗时/费用，不保证模型真实生成成功或摘要忠实。

两版本的请求/响应上限、输出预留和严格历史检查均按 launch 版本绑定，旧v1记录不按v2重解释。新包须使用自己的identity和适用B收据，不能复用旧包收据。正式 `GoChiHarness` 当前仍不透传摘要开关，保持默认off；上述是包内CLI能力，正式采用需调用方后续接线/具体授权，不能凭本说明直接发真实请求。

HTTP 连接/写入/连接池等待分别为 30/60/60 秒；主请求及 continuation 读取超时 240 秒，确认 360 秒。Guard 对完整发送与读取再施加主请求及 continuation 300 秒、确认 420 秒绝对上限。B 的新请求只在开始后 180 秒内准入，C 为 1800 秒（2026-11-06 按官方 submission 默认 2× 从 900 上调；task.toml 基础仍为 900）；恢复不重置起点或总截止。窗口内已发出的请求可以继续至其自身上限。控制器配置 `timeout_seconds` 的范围为 B 360–3600 秒、C 2040–3600 秒（role_runner 1900，operator 2040）。这里沿用现有 TIME_POLICY 数值；超时不触发自动重试，未知用量仍阻断后续调用。

输入按最终实际发送的完整 JSON 计量，覆盖 reasoning、工具定义、参数、结果、中文及结构，记录原始 wire 字节；`chi-context-v2` 的 UTF-8 字节估算不是精确 tokenizer，容量依据仍标为 configured_unverified。本次输出预留取配置基础预留与实际 max_tokens 的较大值，未知容量、坏配置和超限在发送前拒绝。

输入摘要默认关闭，仅 CHI `live` 可显式选择 `--input-summary chi-input-summary-v1`；不可同时启用输出恢复或 payer evidence shadow。摘要每 run 最多一次，计入共享 50，保留后续 main 额度；固定保留最近两个完整工具批次。SDK 历史仍完整，程序仅对实际 wire 构造检查点，保护状态以程序记录为准。摘要请求无工具通道，失败、未知用量或持久化异常停止，不自动重发；真实端点兼容性和摘要语义忠实度尚未验证，启用仍须对应真实请求授权及新候选准入。

输出恢复默认关闭。仅 CHI `live` 入口支持显式选项 `--output-recovery chi-output-recovery-v1`，版本写入 launch；启用必须另有对应真实请求授权及新候选准入。可信 length 先留证结算，程序再消耗一次性许可；每链最多一次、每运行最多两次追加，全部计入共享 50。无工具的 length 精确保留同源部分正文/reasoning 后接续；含工具的 length 整批零执行，从最后合法历史重新生成。新工具仍经过原批次、实体、角色、路径、claim 门禁及已完成写指纹检查。不拼接工具参数、不造 tool 结果；再次 length、取消、网络、未知或持久化失败停止，不跨进程自动续发。

HTTP/SDK 通用自动重试仍为零；显式开启本策略会产生上述有界 length 追加请求。`wire-trace.jsonl` 每次实际派发一行；`recovery-trace.jsonl` 记录许可消耗及未发送/结算/未知结果。`run_log.txt` 分列物理用途次数和 SDK 逻辑步；当前运行已知 token 与整账累计 `journal_usage` 分开，费用/未知不补零。原 SDK trace 只反映返回 Runner 的完整响应，应结合 wire 证据审计。

工具响应的 `reasoning_content` 缺失或为 null 时，按 SDK 实际历史表示不附加该字段；字符串（包括空串）按原值回放，其他类型仍拒绝。原始 HTTP 响应证据保持不变，后续历史仍须与已验证结果严格一致。

默认 evaluation 策略是 `record_only`、金额 cap=null；不继承本机开发期人民币限额。每 evaluation/task/attempt/run 有独占身份，失败也保留；不能换 run-id 绕过同一 attempt 或删除 pending/旧账重跑。未知用量、账源异常、持久化不明都阻止后续请求；已知用量先结算，再判断模型响应/业务是否有效。包/源码变化不能自动冒用旧 B 收据或覆盖旧记录。

美元账目分别列 Go 余额实扣、模型价目价值、套餐消耗；三者不可相加，也不与旧 CNY 相加。独立 evaluation 目录表示隔离运行状态，不表示本项目或账户历史清零。订阅固定费另计，余额扣费为零仍会消耗套餐额度。Extra Usage 已由用户确认关闭；程序不自动开启或回退到 balance/native。

新来源的 `go-chi-record-incomplete-fees-v1` 仅将缺失或 null 的费用明细记录为警告；实际 token 仍须完整有效。原 `billing_error` 与 null 均保留，汇总标识费用不完整；明确非 Go 来源或已知正数实扣仍停止。旧来源按其原费用规则审计。

## 提供方条件和结果解释

用户已知悉 [Go 官方文档](https://opencode.ai/v2/docs/console/go/) 尚未明确非编码 CHI 支持，决定按真实开发用途继续使用；不得声称官方已许可，也不伪装请求为 coding。当前 DeepSeek ZDR 月度协议只明确到 2026-10-31，十一月运行前人工复核，程序没有时钟门禁或后台等待。

OpenCode 路径可全天安排已授权工作，不受 DeepSeek 官方 API 直连的避峰约定限制。未知用量及有限实验条件仍然适用。正式 trial 由参赛 Agent 自主执行，不人工代选业务动作或修结果；隐藏评分材料只在运行结束后的操作者检查侧使用。模型声称完成、程序正常退出、部分确定性检查与官方得分分别解释，原版 Claude 判分暂停，official_reward=null。

## 导出和只读预检

在项目目录内导出到一个尚不存在的目标。构建输出的 `manifest_sha256` 是后续命令必须提供的期望包身份；它不是签名或调用授权。

```sh
mkdir -p runs/go-chi-exports
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD:/source:ro" -v "$PWD/runs/go-chi-exports:/exports:rw" \
  -w /tmp chi-agent-dev:latest /opt/venv/bin/python \
  /source/scripts/go_chi_bundle.py build --target /exports/go-chi-001
```

以下从包目录执行，将 `go_bundle_sha256` 填为上述输出值。官方 checkout 是包外资源，固定到 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 并保持干净；依赖卷已有时直接复用。预检不注入 Key、不访问网络、不创建账目或任务世界。

```sh
go_bundle_sha256='<构建输出的 manifest_sha256>'
go_vendor_dir=/absolute/path/to/pinned/chi-bench
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src \
  -v "$PWD:/package:ro" \
  -v "$go_vendor_dir:/package/vendor/chi-bench:ro" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/go_chi_entry.py preflight --bundle-sha256 "$go_bundle_sha256"
```

## B 和自主任务

每个包/源码身份在实际任务前取得自己的 coding B 成功收据；失败不能通过修改收据或更换日志目录伪装成功。B 与任务使用同一个外部持久状态目录及 evaluation-id。需要新的源码身份时，不要覆盖旧包、删账或直接重用旧收据，先完成独立审核与明确的接续安排。

下面是 runner 参数的完整形态，由调用方在已核对的容器中执行。Key 只通过必要的进程环境注入；不要把实际值写在命令正文或日志。`/state` 和 `/runner-logs` 分别是外部可写持久状态与日志父目录，`/runner-logs/b`、`/runner-logs/task` 必须尚不存在。

```sh
# 固定自造 coding B，不连接业务世界
python /package/scripts/go_chi_entry.py coding-b \
  --bundle-sha256 "$go_bundle_sha256" \
  --evaluation-id evaluation-001 --task-id synthetic-coding-b \
  --attempt-id attempt-1 --run-id coding-b-001 \
  --output-root /state --logs-dir /runner-logs/b --history-mode external

# 由所选任务配置提供公开 instruction 和实际 MCP URL
python /package/scripts/go_chi_entry.py live \
  --bundle-sha256 "$go_bundle_sha256" \
  --evaluation-id evaluation-001 --task-id '<调用方任务ID>' \
  --attempt-id attempt-1 --run-id task-001 \
  --output-root /state --logs-dir /runner-logs/task --history-mode external \
  --role provider --instruction-file /input/instruction.md \
  --mcp-url http://official-world:8020/mcp \
  --workspace-root /logs/artifacts/workspaces \
  --handbook-root /workspace/skills/managed-care-operations-handbook \
  --tool-reference /input/tool_reference.md \
  --tool-reference /opt/healthverse-task-assets/tool_reference.md \
  --tool-reference /opt/chi-bench-task-assets/tool_reference.md
```

独立外部 evaluation 使用 `--history-mode external`，它声明该 evaluation 与本机开发账目分离，不证明账户此前消费为零。在本项目本地继续 Go 开发时，改用 `--history-mode local --local-q-root /prior-go --output-root /prior-go/chi-evaluation`，只将已核对的既有 Go 账目挂到 `/prior-go`；本地 CHI 状态固定在该子目录，不能另选目录。程序审计并持锁，不允许借新的 evaluation 目录绕过旧 pending/halt。Q 原有文件保持原字节，新增 CHI 子目录另行核算；两个模式都不改写 native CNY 历史。

## 显式本地账目接续

候选包预检取得新运行身份后，在已审核旧账副本上先使用 `audit-history`，再用 `rebind-history`。两者都需要 `--bundle-sha256`、`--history-mode local`、`--local-q-root /prior-go`、`--output-root /prior-go/chi-evaluation`、`--expected-old-identity` 和 `--expected-accounting-sha256`；迁移另需 `--migration-reason`。新身份只能由所选包预检计算，不能作为任意 CLI 值传入。两者不读取 Key、不发模型请求；按 Q 再 CHI 顺序锁定并检查证据。迁移归档旧账原字节，保留旧 seal、receipt 和其他证据的原路径；中断标记或缺件需要人工调查，不应删除标记绕过。旧 B 收据不授权新身份，须取得该候选自己的 B。

`inspect-history` 使用相同的本地根、期望旧身份与主账 SHA，可只读检查含 pending/halt 的历史；可选同时提供 `--provider-record` 和 `--provider-record-sha256` 检查 Console 导出。可读取的旧请求正文只输出字节数，并与导出的 content-length 核对；字节数一致不证明唯一关联。输出只报告验证状态、费用字段缺口及有限关联信息，不输出原账户、会话或地理信息。Console cost 保留原始意义，不能推算余额实扣、价目价值或套餐消耗；检查成功不解除 pending、授权运行或修改旧证据。

用户已明确允许当前旧超时保留未结算记录后继续新独立试次。`acknowledge-unsettled` 使用相同本地身份与主账 SHA 参数，另须指定 `--target-run`、`--target-round`、`--expected-request-sha256`、`--provider-record`、`--provider-record-sha256` 和 `--acknowledgement-reason`。入口只接受无 dispatch、无响应、诊断为超时且已失败封存的旧请求，审计后归档旧主账原字节、提供方记录和决定事件，解除该请求对新试次的有效准入阻断；原请求仍未结算，Console token/费用不并入账目，原失败、seal 与证据不变。事件不是运行授权，也不会自动重发或放行未来未知请求。中断标记及异常文件需人工调查，不能删除后绕过检查。

## 操作者单次调度

`scripts/go_chi_operator.py` 位于项目源码侧，**不在参赛包内**。它接收一份受审 JSON 配置及其 SHA-256：`--config /audit/config.json --config-sha256 <hash>`。配置字段为 `kind`（`b` 或 `c`）、`run_id`、`evaluation_id`、`task_id`、`attempt_id`、`bundle_relative`、`bundle_sha256`、`runtime_identity`、`runner_image_id`、`world_image_id`、`resource_relative`、`resource_manifest_sha256`、`resource_identity_relative`、`resource_identity_sha256`、`output_relative` 和 `timeout_seconds`。相对路径从控制容器 `/workspace` 起；B 的四个 resource 字段为 null。C 的资源路径指资源根，支持 R 单题和 S 多题清单；单独的只含身份及哈希的 resource identity 必须提供 `task_id`、`world_id`、`world_sha256` 和所选任务完整 `files`。输出目录必须不存在，一次配置只执行一个 B 或 C。

控制器使用 `/opt/a-venv`，只读挂载 SDK、PDF、固定官方源码和候选包；候选先在独立禁网、无凭据容器中预检身份。C 在 world ready 后先捕获并核验初始世界，再保存 provider/payer 的只读资源快照，成功后才读取 Go Key 并启动 runner。runner 静止后再捕获终态和后快照，运行无语义模型的确定性检查，最后清理本次资源。结果分开记录主错误、捕获错误、清理错误和容器 ID；捕获缺失不表示业务无变化。前后 `*-resources.json` 只保存在操作者侧，需要另行逐资源比对并关联患者/案件，不能仅凭目标过滤的 export 判断非目标未变化。official_reward 保持 null。

payer/UM 与 CM 分别使用 `--role payer` / `--role cm` 和相应角色 MCP；文件工具只允许该角色/shared workspace，provider 的患者确认门禁不误套到其他角色。三角色协议测试与三赛道真实业务验证分别记录。

## 官方 harness 适配

`scripts/go_chi_harness.py` 接收 Harbor 的 instruction 和 MCP 配置，再启动本 runner。控制侧把包内 `scripts/`、固定官方源码和控制侧依赖放入 Python 模块路径，显式指定 `go_chi_harness:GoChiHarness`。它不修改 vendor registry，也不会被原 stock `openai-agents` 自动选用。真实组件预演、真实模型任务与最终配送分别验收；最终 F.5 和官方判分仍按项目审核状态管理。

适配器读取 `OPENCODE_API_KEY` 和以下调用方配置：`CHI_GO_BUNDLE_ROOT`、`CHI_GO_STATE_ROOT`、`CHI_GO_ROLE`、`CHI_GO_EVALUATION_ID`、`CHI_GO_TASK_ID`、`CHI_GO_ATTEMPT_ID`、`CHI_GO_RUN_ID`、`CHI_GO_BUNDLE_SHA256`、`CHI_GO_HISTORY_MODE`；local 模式另需 `CHI_GO_Q_ROOT`。metadata可通过Harbor的 `AgentConfig.env` 提供；Key仅在控制器运行时环境安全注入，**不要放进AgentConfig、extra_env、`--ae KEY=value`或其他持久配置**。Harbor会保存TrialConfig，运行时注入用于避免配置落盘。适配器无凭据执行同一解释器的包预检，之后才读取Go Key并逐次注入runner。

调用方需提供已供应包/固定SDK/PDF/vendor的世界镜像；`install()` 不自动联网安装。官方Docker环境显式使用 `host_env={}`，环境的持久/作用域执行env保持空，避免在runner启动前注入其他提供方凭据。适配器暴露给Trial的执行overlay为空；内部metadata不随之进入进程。角色MCP端点为provider 8020、payer 8100、cm 8200的单一 `/mcp`，与 `CHI_GO_ROLE` 一致。

公开资源也由调用方供应：在允许的 `/input/tool_reference.md` 提供普通文件。固定官方entrypoint可能把 `/opt/*-task-assets/tool_reference.md` 改成链接；runner仍拒绝链接，适配器只选择存在的普通候选。应按所选公开资源身份供应文件，不能盲目跟随任意链接或复制fixtures/评分材料。instruction由Harbor原样提供，适配器独占写入临时文件。

适配器保留无Key预检摘要和安全执行摘要，原stdout/stderr只保留字节数/hash及受限安全诊断，不进入Harbor父类的原输出debug日志；实际执行仍由真实环境的exec完成。非零/缺返回码、损坏结果或trace向上报错，超时/取消继续交给Harbor清理，无自动重试。下载日志后核验结果/输出/trace并填充context与trajectory；总tokens取完整已结算请求的run_result，缓存/费用未知保留null，不从部分step用量推断零缓存或金额。

`CHI_GO_STATE_ROOT` 内的账、wire、工具证据及seal需要调用方在删除世界前持久保存，单靠 `run_result.json` 不足以保全历史。仓库测试使用真实Trial hooks采集；开发操作者与官方配送侧各自负责资源供应、证据导出与清理。测试专用解释器/合成HTTP shim不在本包内，不能拿它代替真实模型运行；三角色只读协议也不证明三赛道业务能力。仓库README维护预演命令，详细通过层与限制只见阶段报告。
