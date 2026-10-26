# 评测专用入口：干净程序包离线运行

本包是 identified/offline preparation，实际模型 API、任务世界、真实 C 和官方判分继续暂停。它验证交付入口默认使用 evaluation record_only，金额上限为 null，不读取开发余额、prior 文件或共享 5 元账本。完整正式系统冻结与真实接入仍须后续验收；此文件不表示材料已经提交给主办方。

唯一运行入口为 `scripts/evaluation_entry.py`。plan/preflight 只读；rehearse 使用固定真实 SDK/官方循环及合成 HTTP/工具；live 在配置、manifest、认证和输出访问前拒绝。不要改用开发入口，不提供本地 budget/scope/cap 参数。轮数、输出、协议/历史/工具/usage 校验和零重试仍保留。

## 依赖和外部资源

本次离线验收复用 Python 3.12 dev 镜像、既有 `chi-model-deps` 模型依赖卷及固定官方源码 checkout。包内依赖锁与安装脚本用于复现说明，安装/运行均应在 Docker 内；本轮没有重新安装或下载。没有这些依赖时应显示缺口，不能据策略检查成功推断整个系统可运行。

vendor、任务数据、手册、模型凭据、开发账本和旧轨迹不随包分发。下面仅在容器中只读挂载有权限的固定 vendor 源码，SDK 使用现有只读依赖卷；不挂官方任务世界、数据、手册或 `.env`。新机器的依赖安装与完整正式启动仍在最终复现验收范围。

## 从独立目录启动

从导出包根目录执行，先按本机实际位置设置外部源码路径和新的合成输出目录。输出放在包目录之外：

```sh
f_vendor_dir=/absolute/path/to/authorized/chi-bench
f_output_dir=/absolute/path/to/new/synthetic-output
mkdir -p "$f_output_dir"
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/package/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro \
  -v "$PWD:/package:ro" \
  -v "$f_vendor_dir:/package/vendor/chi-bench:ro" \
  -v "$f_output_dir:/output:rw" \
  -w /tmp chi-agent-dev:latest /opt/venv/bin/python \
  /package/scripts/evaluation_entry.py rehearse \
  --output-root /output --evaluation-id package-check \
  --task-id task-a --attempt-id attempt-1 --run-id package-task-a \
  --scenario evaluation-over-five
```

这里不传选择 record_only 的开关；它是入口的默认且固定策略。该合成链路有三次合法请求，按文档峰值价估算超过 5 元；所有真实 usage/cost/reward 仍为 null。保持 evaluation-id，换成 task-b、独立 run-id 后，应使用同一包/配置继续演练，不能受第一题的开发预算影响。相同 task/attempt 换 run-id 会拒绝；失败/unknown 也不清零、不自动重跑。

将子命令改为 plan 或 preflight 可检查包、配置、SDK/source、认证和暂停状态；检查时不需要输出目录。没有子命令时按只读计划处理。live 固定拒绝，不能靠本文件、参数或环境解除暂停。

包 manifest 记录固定允许文件的内容身份，不是签名或执行许可。文件/配置不匹配时拒绝；同一 evaluation 不能悄悄更换已登记的包/配置。正式交付前仍需核对主办方当前要求、固定最终模型/资源/启动配置，并完成真实接入与复现验收。
