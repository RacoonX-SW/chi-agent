# 评测专用入口：干净程序包离线运行

本包是 identified/offline preparation，实际模型 API、任务世界、真实 C 和官方判分继续暂停。它验证交付入口默认使用 evaluation record_only，金额上限为 null，不读取开发余额、prior 文件或共享 5 元账本。完整正式系统冻结与真实接入仍须后续验收；此文件不表示材料已经提交给主办方。

唯一运行入口为 `scripts/evaluation_entry.py`。plan/preflight 只读；rehearse 保留原合成演练，launch-rehearse 接受外部任务说明、MCP URL 和日志目录，仍使用固定真实 SDK/官方循环与合成 HTTP/MCP/本地工具。live 在输入、配置、manifest、认证和输出访问前拒绝。不要改用开发入口，不提供本地 budget/scope/cap 参数。轮数、输出、协议/历史/工具/usage 校验和零重试仍保留。

## 依赖和外部资源

需要既有 Python 3.12 dev 镜像、按包内哈希锁安装的独立模型依赖卷，以及有权限的固定官方源码 checkout（commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`）。安装/运行均在 Docker 内，不更改基础镜像或锁文件。没有依赖时应显示缺口，不能据策略检查成功推断整个系统可运行。

vendor、任务数据、手册、模型凭据、开发账本和旧轨迹不随包分发。下面仅在容器中只读挂载有权限的固定 vendor 源码；不挂官方任务世界、数据、手册或 `.env`。本方法验证现有镜像/当前架构上的空卷安装和独立包启动；基础镜像重建、新机器/其他架构、真实服务与完整正式启动分别验收。

从导出包目录设置一个尚不存在的卷名，先用 `docker volume inspect` 确认不存在，再创建并安装（该 inspect 预期非零；如已存在则换新名字）：

```sh
f_model_volume=chi-model-clean-example-001
docker volume inspect "$f_model_volume"
docker volume create "$f_model_volume"
docker run --rm --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD:/workspace:ro" -v "$f_model_volume:/model-deps:rw" \
  -w /workspace chi-agent-dev:latest sh -ec \
  'test -z "$(ls -A /model-deps)"; sh scripts/install_model_dependencies.sh /model-deps'
```

只有安装需要包下载网络；下方运行禁网。安装不读取模型凭据，不代表模型已认证或获准调用。

## 从独立目录启动

从导出包根目录执行，先按本机实际位置设置外部源码路径和新的合成输出目录。输出放在包目录之外：

```sh
f_vendor_dir=/absolute/path/to/authorized/chi-bench
f_output_dir=/absolute/path/to/new/synthetic-output
mkdir -p "$f_output_dir"
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/package/vendor/chi-bench/src \
  -v "$f_model_volume:/model-deps:ro" \
  -v "$PWD:/package:ro" \
  -v "$f_vendor_dir:/package/vendor/chi-bench:ro" \
  -v "$f_output_dir:/output:rw" \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/evaluation_entry.py rehearse \
  --output-root /output --evaluation-id package-check \
  --task-id task-a --attempt-id attempt-1 --run-id package-task-a \
  --scenario evaluation-over-five
```

这里不传选择 record_only 的开关；它是入口的默认且固定策略。该合成链路有三次合法请求，按文档峰值价估算超过 5 元；所有真实 usage/cost/reward 仍为 null。保持 evaluation-id，换成 task-b、独立 run-id 后，应使用同一包/配置继续演练，不能受第一题的开发预算影响。相同 task/attempt 换 run-id 会拒绝；失败/unknown 也不清零、不自动重跑。

将子命令改为 plan 或 preflight 可检查包、配置、SDK/source、认证和暂停状态；检查时不需要输出目录。没有子命令时按只读计划处理。live 固定拒绝，不能靠本文件、参数或环境解除暂停。

## 官方启动接点的合成复现

官方 harness 将 task instruction 写成文件，并从 task 配置取得 MCP URL；runner 将日志/结果写入 logs-dir。这里用独立合成 instruction 验证相同接点，URL 从调用方位置明确提供。provider 常见 `http://localhost:8020/mcp` 的 localhost 指官方任务容器；payer/CM 分别用 8100/8200，8023 是 health 服务。本模式只把 URL 传到合成 MCP factory，不测试网络可达性，也不启动官方世界。

准备 `/absolute/path/to/synthetic-input/instruction.md`，内容可为 `Use the supplied synthetic tools to look up sample and format the result.`。input 只读挂载，logs 与 accounting 输出分开，日志目标必须尚不存在。文件必须为有界 UTF-8 普通文件，不允许 symlink、父目录跳转或 verifier fixtures 路径；MCP URL 使用带显式端口的 HTTP(S) `/mcp`，不含凭据、query 或 fragment。

```sh
f_input_dir=/absolute/path/to/synthetic-input
f_logs_dir=/absolute/path/to/new/synthetic-logs-root
mkdir -p "$f_logs_dir"
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/package/vendor/chi-bench/src \
  -v "$f_model_volume:/model-deps:ro" \
  -v "$PWD:/package:ro" \
  -v "$f_vendor_dir:/package/vendor/chi-bench:ro" \
  -v "$f_input_dir:/input:ro" \
  -v "$f_output_dir:/output:rw" -v "$f_logs_dir:/runner-logs:rw" \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/evaluation_entry.py launch-rehearse \
  --instruction-file /input/instruction.md --mcp-url http://localhost:8020/mcp \
  --logs-dir /runner-logs/task-c \
  --output-root /output --evaluation-id package-check \
  --task-id task-c --attempt-id attempt-1 --run-id package-task-c \
  --scenario evaluation-over-five
```

独立日志保留官方 runner 的 `run_result.json`、成功时的 `run_output.txt`/`trace.jsonl` 和捕获 stdout/stderr 的 `run_log.txt`；accounting 中记录输入身份、日志归属与合成来源。失败后保留已产生的日志和 attempt claim；更换 run-id、输入或日志目录不能重跑同一 task/attempt。合成产物不代表真实 provider 用量、费用、业务成功或官方 reward。

包 manifest 记录固定允许文件的内容身份，不是签名或执行许可。文件/配置不匹配时拒绝；同一 evaluation 不能悄悄更换已登记的包/配置。正式交付前仍需核对主办方当前要求、固定最终模型/资源/启动配置，并完成真实接入与复现验收。
