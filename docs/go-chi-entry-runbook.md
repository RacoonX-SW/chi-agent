# Go CHI 程序包

## 准备

使用 Docker 和 Python 3.12。调用方在包外提供固定到 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 的 CHI-Bench 源码，以及按包内 `requirements-model.lock`、`requirements-pdf.lock` 安装的模型和 PDF 依赖。将导出包挂载到开发镜像的 `/workspace`，从包根执行 `sh scripts/install_model_dependencies.sh /model-deps` 和 `uv pip install --target /pdf-deps --require-hashes -r requirements-pdf.lock`，将依赖安装到各自的挂载卷。

## 导出与预检

在源码根目录执行下列命令。目标目录须尚不存在，输出中的 `manifest_sha256` 用于随后预检。

```sh
docker compose build dev
docker compose run --rm --no-deps dev python -m chi_agent.bundle build --target /workspace/dist
```

在导出的包目录执行以下预检。将卷名和 vendor 路径替换为调用方已准备的资源，`go_bundle_sha256` 设为导出时的值。

```sh
go_bundle_sha256='<manifest_sha256>'
go_vendor_dir=/absolute/path/to/pinned/chi-bench
go_model_volume=chi-h-root-model-deps-20261027-v1
go_pdf_volume=chi-k-pdf-deps-20261027-v1
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src \
  -v "$PWD:/package:ro" -v "$go_vendor_dir:/package/vendor/chi-bench:ro" \
  -v "$go_model_volume:/model-deps:ro" -v "$go_pdf_volume:/pdf-deps:ro" \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/go_chi_entry.py preflight --bundle-sha256 "$go_bundle_sha256"
```

成功时返回 `identity_verified`。源码仓库的常规离线检查入口为 `CHI_VENDOR_DIR=/absolute/path/to/pinned/chi-bench bash scripts/tools/verify_offline.sh`，使用已准备的开发、controller 镜像和依赖卷。

## 运行

任务容器提供公开 instruction、普通文件形式的工具参考、授权手册、角色 workspace 和可写的外部状态及日志。Provider、Payer、CM 分别连接端口 8020、8100、8200 的单一 `/mcp` 服务。需要调用模型时，调用方仅向相应运行进程注入 `OPENCODE_API_KEY`。

每个包身份先取得自己的 coding B 收据。B 和任务使用同一个 evaluation 及状态根，日志目标分别新建。下列参数用于获准的外部状态模式，值由调用方提供。

```sh
python /package/scripts/go_chi_entry.py coding-b \
  --bundle-sha256 "$go_bundle_sha256" \
  --evaluation-id evaluation-001 --task-id synthetic-coding-b \
  --attempt-id attempt-1 --run-id coding-b-001 \
  --output-root /state --logs-dir /runner-logs/b --history-mode external

python /package/scripts/go_chi_entry.py live \
  --bundle-sha256 "$go_bundle_sha256" \
  --evaluation-id evaluation-001 --task-id "$go_task_id" \
  --attempt-id attempt-1 --run-id task-001 \
  --output-root /state --logs-dir /runner-logs/task --history-mode external \
  --role provider --instruction-file /input/instruction.md \
  --mcp-url http://official-world:8020/mcp \
  --tool-reference /input/tool_reference.md
```

工作区和手册的默认路径为 `/logs/artifacts/workspaces` 和 `/workspace/skills/managed-care-operations-handbook`。本地接续模式使用 `--history-mode local --local-q-root /prior-go --output-root /prior-go/chi-evaluation`。复核历史时，用该次运行的冻结包及依赖执行 `inspect-history`，核对原身份和主账摘要。新包准入、旧账接续和真实调用按各自审批执行。

Go 默认使用 `deepseek-v4.1-flash`、`record_only` 和零自动重试。主请求默认输出上限 8192，可用 `--main-max-tokens` 明确覆盖。摘要和输出恢复默认关闭。保留所有已结算用量和未知状态，出现新未知时停止后续调用。开发结果的 `official_reward` 为 `null`。

## Harbor 接入

在控制侧设置 `PYTHONDONTWRITEBYTECODE=1`，将包的 `scripts/`、固定 vendor 源码和控制侧依赖放入 Python 模块路径，指定 `go_chi_harness:GoChiHarness`。使用 `CHI_GO_BUNDLE_ROOT`、`CHI_GO_STATE_ROOT`、`CHI_GO_BUNDLE_SHA256`、`CHI_GO_ROLE`、`CHI_GO_EVALUATION_ID`、`CHI_GO_TASK_ID`、`CHI_GO_ATTEMPT_ID`、`CHI_GO_RUN_ID` 和 `CHI_GO_HISTORY_MODE` 提供调用信息。本地接续另需 `CHI_GO_Q_ROOT`。Key 通过控制器运行时环境注入，预检成功后才进入 runner。调用方负责世界镜像、依赖、输入资源和持久化状态，`install()` 由此保持空操作。

当前导出使用 v3 清单：`scripts/chi_agent/` 按 agent、context、tools、models、accounting、roles 和 evaluation 子包组织，包含各子包初始化文件。校验器仍按各自冻结清单验证 v1 和 v2 历史包。
