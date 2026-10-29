# Go CHI 独立程序包运行说明

本说明随新的 Go CHI 包分发。正式最终配送及 F.5 冻结由项目审核状态另行管理；主办方原 stock harness 不会自动选择本包，调用方须将本包入口作为自有 runner 接入。旧 evaluation_entry 的离线入口和拒绝行为分别保留。

## 运行环境与外部输入

使用 Python 3.12 和包内锁定的 SDK/PDF 依赖；安装、调试和运行在 Docker 中。当前目标平台为 Linux arm64，其他架构须单独核对锁与安装。已有 `chi-agent-dev:latest`、SDK/PDF 卷可直接复用，无需重做 G/H 空卷安装。包只含允许分发的自有源码、配置、依赖锁和本说明，不包含 `.env`、vendor checkout、任务数据、手册、开发账本或运行轨迹。

调用方在包外提供固定官方源码、公开 instruction 文件、所选角色的 Streamable HTTP MCP URL、授权资源和可写日志/持久状态目录。provider、payer/UM、CM 的默认 MCP 端口分别为 8020、8100、8200，8023 是 health 服务；跨容器调用时传实际可达的主机名，不能把另一个容器的 localhost 当本地端点。每次只连接选择的一个角色，不汇集三方工具。

Agent 可见资源只包括公开 instruction/工具参考、已授权的 managed-care handbook，以及当前角色/shared workspace。fixture、expectations、完整原始 world、评分材料和开发评审目录不挂给参赛程序的文件工具。凭据只注入需要发请求的进程环境，Go 使用 `OPENCODE_API_KEY`；原 `DEEPSEEK_API_KEY` 保留在本地配置，不转发给 Go 运行进程。

## 固定协议、停止和账目

运行模型固定 `deepseek-v4.1-flash`，SDK base URL 为 `https://opencode.ai/inference/go/openai/v1`，thinking/high，不追加 `[1m]`。文档标称上下文不等于实测百万 token；自有 User-Agent、每对话稳定 session、TLS、禁用代理/redirect/自动重试均是接点的一部分。

自主任务的 SDK turns 和共享 provider 请求上限均为 50；患者确认最多两次，也消耗这 50 次。主请求输出上限 8192，确认 32768。可信剩余次数由程序根据已发送数生成，确认后刷新；工具调用次数不等于模型请求数。coding B 是独立固定探针合约，最多 6 次/1024 输出，不显示 50 次任务反馈，不作为临床业务成功证据。

默认 evaluation 策略是 `record_only`、金额 cap=null；不继承本机开发期人民币限额。每 evaluation/task/attempt/run 有独占身份，失败也保留；不能换 run-id 绕过同一 attempt 或删除 pending/旧账重跑。未知用量、账源异常、持久化不明都阻止后续请求；已知用量先结算，再判断模型响应/业务是否有效。包/源码变化不能自动冒用旧 B 收据或覆盖旧记录。

美元账目分别列 Go 余额实扣、模型价目价值、套餐消耗；三者不可相加，也不与旧 CNY 相加。独立 evaluation 目录表示隔离运行状态，不表示本项目或账户历史清零。订阅固定费另计，余额扣费为零仍会消耗套餐额度。Extra Usage 已由用户确认关闭；程序不自动开启或回退到 balance/native。

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

## 操作者单次调度

`scripts/go_chi_operator.py` 位于项目源码侧，**不在参赛包内**。它接收一份受审 JSON 配置及其 SHA-256：`--config /audit/config.json --config-sha256 <hash>`。配置字段为 `kind`（`b` 或 `c`）、`run_id`、`evaluation_id`、`task_id`、`attempt_id`、`bundle_relative`、`bundle_sha256`、`runtime_identity`、`runner_image_id`、`world_image_id`、`resource_relative`、`resource_manifest_sha256`、`resource_identity_relative`、`resource_identity_sha256`、`output_relative` 和 `timeout_seconds`。相对路径从控制容器 `/workspace` 起；B 的四个 resource 字段为 null。C 的资源路径指资源根，支持 R 单题和 S 多题清单；单独的只含身份及哈希的 resource identity 必须提供 `task_id`、`world_id`、`world_sha256` 和所选任务完整 `files`。输出目录必须不存在，一次配置只执行一个 B 或 C。

控制器使用 `/opt/a-venv`，只读挂载 SDK、PDF、固定官方源码和候选包；候选先在独立禁网、无凭据容器中预检身份。C 在 world ready 后先捕获并核验初始世界，再保存 provider/payer 的只读资源快照，成功后才读取 Go Key 并启动 runner。runner 静止后再捕获终态和后快照，运行无语义模型的确定性检查，最后清理本次资源。结果分开记录主错误、捕获错误、清理错误和容器 ID；捕获缺失不表示业务无变化。前后 `*-resources.json` 只保存在操作者侧，需要另行逐资源比对并关联患者/案件，不能仅凭目标过滤的 export 判断非目标未变化。official_reward 保持 null。

payer/UM 与 CM 分别使用 `--role payer` / `--role cm` 和相应角色 MCP；文件工具只允许该角色/shared workspace，provider 的患者确认门禁不误套到其他角色。三角色协议测试与三赛道真实业务验证分别记录。

## 官方 harness 适配

`scripts/go_chi_harness.py` 是包内薄适配器，接收官方 Harbor 的 instruction 和 MCP 配置，再启动本 runner。它不修改 vendor registry，也不会被原 stock `openai-agents` 自动选用；接入方须明确提供自有 harness import path、包路径、固定身份及外部状态/日志/资源挂载。完整 Harbor 安装/类型和最终配送仍需 F.5 验证；现有离线适配检查不能替代该步骤。

适配器读取 `OPENCODE_API_KEY` 和以下调用方配置：`CHI_GO_BUNDLE_ROOT`、`CHI_GO_STATE_ROOT`、`CHI_GO_ROLE`、`CHI_GO_EVALUATION_ID`、`CHI_GO_TASK_ID`、`CHI_GO_ATTEMPT_ID`、`CHI_GO_RUN_ID`、`CHI_GO_BUNDLE_SHA256`、`CHI_GO_HISTORY_MODE`；local 模式另需 `CHI_GO_Q_ROOT`。它只将必要 Go Key 注入新的 runner 进程，并要求 runner 的非零退出向上报错；包、固定依赖和资源须由接入方预先提供，`install()` 不自动联网安装。
