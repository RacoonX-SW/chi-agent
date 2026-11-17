# 兼容评测程序包

`scripts/evaluation_entry.py` 提供 `plan`、`preflight`、`rehearse` 和 `launch-rehearse`，固定使用 `record_only`。当前 `live` 返回 `real_execution_paused`。合成演练结果的 `official_reward` 为 `null`。

## 导出

在源码根目录构建 Python 3.12 开发镜像，再导出到尚不存在的目录。

```sh
docker compose build dev
docker compose run --rm --no-deps dev python -m chi_agent.evaluation_bundle build --target /workspace/build
```

## 隔离预检

在导出的包目录运行。将 vendor 设为固定到 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 的 CHI-Bench 源码路径，模型卷按包内 `requirements-model.lock` 准备，可从已挂到 `/workspace` 的包目录执行 `sh scripts/install_model_dependencies.sh /model-deps`。

```sh
evaluation_vendor_dir=/absolute/path/to/pinned/chi-bench
evaluation_model_volume=chi-h-root-model-deps-20261027-v1
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/package/vendor/chi-bench/src \
  -v "$PWD:/package:ro" -v "$evaluation_vendor_dir:/package/vendor/chi-bench:ro" \
  -v "$evaluation_model_volume:/model-deps:ro" \
  -w /tmp chi-agent-dev:latest /usr/local/bin/python -S \
  /package/scripts/evaluation_entry.py preflight
```

预检成功时 `technical_ready=true`。运行 `rehearse` 时，将包外可写目录挂到 `/output`，传入 `--output-root /output --evaluation-id`、`--task-id`、`--attempt-id` 和 `--run-id`。使用 `launch-rehearse` 时另传外部合成 `--instruction-file`、`--mcp-url` 和新的 `--logs-dir`。两个模式使用合成 HTTP 与工具，保留独立的运行记录。

当前导出使用 v3 清单：`scripts/chi_agent/` 按职责子包组织，并包含运行所需的子包初始化文件。校验器仍按各自冻结清单验证 v1 和 v2 历史包。
