# 官方启动接点与独立安装复现审核

日期：2026-10-27。结论：**H 官方启动接点与独立安装复现离线验收通过**，通过候选为 `f562f60a1ecb1f35d716c7e06cede89083b6ad10`。首审 R1 已返工并独立复验关闭；G 的通过身份和历史范围保留在 [G 审核](evaluation-entry-bundle-review.md)，本轮不宣称 F.5 完整正式冻结或真实执行通过。

## 授权与基线

已通过 GitHub API 核对 [PR #11](https://github.com/xsw932187210-cell/chi-agent/pull/11) `merged=true`，合并提交为 `0ca299b8856a5d385b330569c49c0be6e213e32a`；fetch 后从该最新 `origin/main` 建 `codex/official-launch-reproduction`，写入前工作区干净。按用户要求，一个 `gpt-6-luna` / `high` 实现，主代理独占规格、教学、独立审核和 GitHub。

本轮只恢复启动接点代码、锁定依赖安装和合成离线复现。正式入口 record_only/null cap、本地 B/C 共享 5 元均保留。无真实模型 API、真实 C、官方任务世界或判分；F.5 完整正式冻结仍未完成。不重做 G，不修改固定 vendor、依赖锁、基础镜像、旧 C 或 baseline 门禁。

## 固定官方启动契约

核对本地干净 vendor commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，以下均为已读源码，未运行官方任务世界：

| 接点 | 固定源码行为 | 本轮接入含义 |
| --- | --- | --- |
| task instruction | harness 将传入 instruction 写入 `/tmp/instruction.md`；runner 从 `--instruction-file` 读文本 | 接受外部有界 UTF-8 普通文件，实际传到原 run_agent 与 SDK 输入 |
| MCP URL | harness 选择 task 中首个有 URL 的 MCP server | URL 显式传递，不用 health 地址或另一个容器的 localhost 冒充端点 |
| role endpoint | 本地固定 provider task.toml 为 `http://localhost:8020/mcp`；entrypoint 分别等待 8020/8100/8200 `/mcp`；8023 为 HTTP health | 离线验证 URL 流转，合成 MCP factory 不建立网络连接 |
| result/logs | `--logs-dir` 默认 `/logs/agent`，可用 `OPENAI_AGENTS_LOGS_DIR`；runner 写 `run_result.json`，有结果时写 `run_output.txt`/`trace.jsonl` | 使用新的独占外部日志目录并保留实际 runner 产物；stdout/stderr 保存为 `run_log.txt` |
| status | runner 捕获执行异常写 error，再以非零退出；无 judge reward | 合成失败如实保存，真实 usage/cost/reward 为 null；不能把进程或 fixture 成功称为官方通过 |

固定源码链接：[harness](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/agents/openai_agents_harness.py)、[runner](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/agents/openai_agents_runner.py)、[entrypoint](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/docker/entrypoint.sh)。实际读取的 Git blob 分别为 `929c2946ffe7b51c7d8d9e6313c613f8a7424c1d`、`87657b79b535f340714542a745c1354b4e54dad0`、`8fa904c908558760060fdbea7d5ba4b9c83d9542`。仅读取公开 Agent 输入配置，没有向 Agent 提供评分 fixtures。

## 独立空卷安装

复用镜像 `chi-agent-dev:latest`，ID `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，实际 Python 3.12.15/Linux aarch64、uv 0.6.14。Docker Desktop 最初未运行，由主代理启动已有应用；未安装宿主 Python 包或重建镜像。

主代理先确认 `chi-h-root-model-deps-20261027-v1` 不存在（inspect 退出 1），再创建带本轮 owner 标签的新卷。安装前容器检查目标目录为空；只挂载从基线 Git archive 提取的原锁/安装脚本，没有旧 SDK 卷、模型凭据或项目目录挂载。使用 `UV_NO_CACHE=1`，包下载实际发生；40 个包按 `--require-hashes` 安装成功，进程退出 0。

- 原锁 SHA256：`47e00d40985e682e40c3e36cf7f74c0a10886935ff4c4e6d25fe8d3aaa08927d`。
- 原安装脚本 SHA256：`ba3283e557bd79fd6e7aa5907761b7923f5f86e4864f4bee6538e40b5008c987`。
- 关键版本：openai-agents 0.13.6、openai 2.36.0、httpx 0.28.1、mcp 1.30.0。
- 主代理另以 `importlib.metadata.distributions(path=['/model-deps'])` 逐一比较全部 40 个锁定包，检查 68 条当前平台/默认 extras 下适用的依赖约束；全部通过。agents/openai/httpx/mcp/pydantic 实际导入路径均位于新卷。
- `uv pip check --python /opt/venv/bin/python` 只检查基础环境的 12 个包，不能证明 target 卷完整性；上述独立检查是对新卷的实证补充。

安装核心命令在复用镜像内执行：

```sh
test -z "$(ls -A /model-deps)"
sh scripts/install_model_dependencies.sh /model-deps
```

完整命令与退出结果在本地工具记录；原始输出位于忽略目录 `runs/official-launch-reproduction/root/evidence/clean-install.log` 与 `clean-dependency-check.json`，核对脚本为同一 root 目录的 `check_clean_dependencies.py`。后续最终候选再次核对锁/脚本未变，运行使用 `/usr/local/bin/python -S` 和此新卷，屏蔽基础开发 venv/site-packages。

## 固定候选与独立复验

首候选 `8c2e92919c37f9ad3dc45dd5f3f593876e1e5133` 由主代理在实现停写后提交；包输入 runbook 同时固定，其余主代理规格/审核文档不参与被测包内容。主代理从该提交 Git archive 导出只读快照，不复用子代理构建包。

首审全项目 Docker 回归为 235 passed / 120 subtests。使用新依赖卷、`/usr/local/bin/python -S`、只读独立包、外部只读 vendor/input 和分别可写的 accounting/logs，工作目录为 `/tmp`；没有原仓库或旧 SDK 卷挂载。独立实际 CLI 的前 20 项检查通过，包括不同 instruction/role URL、多个超 5 元 trial、unknown 后另一合法任务、重复 attempt、只读日志失败保留 claim、已有/重叠日志、缺文件、错误 URL/health、编码/长度/symlink/fixture 路径及 live 最先拒绝。

**首审 R1 未通过**：第 21 项将普通文件路径替换为无 writer 的 FIFO，读入函数在 `os.open(O_RDONLY)` 阻塞，尚未执行 fstat 的普通文件检查。主代理以 3 秒子进程超时实际复现并终止，没有 model/client/claim 活动。证据为 `root/evidence/cli-cases.json` 与 `candidate-1-cli.log`。已交回同一实现代理，要求非普通文件打开不阻塞，并用真实 FIFO 回归；自测/前 20 项通过不能覆盖此缺陷。

### R1 修复与最终候选

修复候选为 `f562f60a1ecb1f35d716c7e06cede89083b6ad10`。公共有界读 helper 先 lstat 拒绝非普通文件/超限大小，再以 `O_NOFOLLOW | O_NONBLOCK` 打开并比较 dev/ino，保留打开后的类型/大小、读取上限和读后身份核对。真实 FIFO 子进程回归有超时保护，目录与 Unix socket 也被拒绝。主代理读差异及调用者后，从该提交再次导出只读 Git archive 和新包，不复用首审输出/claim。

包仍为 13 个允许文件，没有添加 vendor/data/账本/凭据。最终 manifest SHA256 为 `e4723b5048cae849cfdda05f232f329db0dea6701f6bafc7867a567564ac7404`，entry config SHA256 为 `3b55775ee22ec4cf67e463805aa429a803cdd550d059242c7da5409a0c61b413`。最终包内锁/安装脚本与空卷安装输入的 SHA256 完全相同；未重新解析或升级依赖。

| 主代理独立检查 | 实际结果 |
| --- | --- |
| 最终固定快照全项目，使用新 SDK 卷 | 236 passed / 120 subtests，退出 0；包含本地 5 元、G/F、C、接入层和新 helper 的适用回归 |
| 实际干净包 CLI，`python -S`、不同 cwd、禁网、无基础 venv | 21 项通过，退出 0；先前 FIFO 现在迅速返回 `evaluation_instruction_invalid`，未创建日志/claim；R1 关闭 |
| 外部说明/角色 URL/独占日志 | 四条合法 trial 各 3 次请求、各合成估算 6.196608 CNY；含不同 instruction 和 provider/payer/CM 形态 URL；均固定 record_only/null cap，无开发余额回退 |
| unknown/失败与 replay | unknown 仅影响该 trial，另一合法 task 可继续；同 attempt 换 run-id 拒绝且不新建日志；只读日志目录失败保留 claim，发送数为 0，之后不能重跑 |
| 实际参数与 SDK wire 观测 | 三个独立诊断场景共观测 9 次真实 SDK 序列化请求；每次 body 中的 user instruction 等于外部文件，run_agent 收到的 URL/logs-dir 与参数相同；MCP/HTTP 边界仍固定 synthetic |
| runner 产物故障注入 | 保留实际 run_result/run_output/trace/run_log；注入 trace 写入失败返回 `official_runner_artifacts_missing`，注入 run_log 写入失败返回 `official_logs_persist_failed`，均退出 1，未把已有最终文本误报为完整启动成功 |
| SDK/vendor 缺失 | 不挂可选依赖/源码时，实际 plan 退出 0、preflight 退出 1，identity unavailable，均只读；没有误称完整运行就绪 |
| 参数/路径/暂停 | 缺文件、非法 URL/health、UTF-8/长度、symlink/fixture、重叠或已存在日志拒绝；live 携无效输入仍最先拒绝，各 read/create 标记为 false |

主代理实际核心命令（详细挂载及每次 argv 见本地工具记录与证据）：

```sh
git archive f562f60a1ecb1f35d716c7e06cede89083b6ad10 chi-agent | tar -x -C chi-agent/runs/official-launch-reproduction/root/candidate-2
# 在复用 Docker 内，固定快照挂 /workspace:ro，包导出挂 /exports:rw
/opt/venv/bin/python scripts/evaluation_bundle.py build --target /exports/candidate-2
# 新依赖卷 /model-deps:ro，固定快照/vendor 分别只读挂载；禁网
/opt/venv/bin/python -m pytest -q -p no:cacheprovider
# 只读独立包 /package，vendor/input 单独只读，accounting/logs/evidence 分开可写，cwd=/tmp
/usr/local/bin/python -S /checks/check.py
```

最后一条分别运行主代理编写的 `check_launch_cli.py` 和 `check_runner_faults.py`；脚本自身只读挂载，不在包 allowlist 中。前者驱动实际 CLI 的 21 项检查，后者只作内存观测与合成故障注入，不修改包/上游源码。两者均不挂原仓库、旧依赖卷、数据、手册、凭据或 Docker socket；运行参数与公开使用方式见包内 runbook。全项目测试使用基础 venv 提供 pytest；独立包实际启动使用 `-S` 屏蔽 site-packages，只从新卷加载 SDK 依赖，两类检查不可混称。

本地证据均在忽略的 `runs/official-launch-reproduction/root/`：

- `final-evidence/build.json`、`pytest.log`、`cli.log`、`cli-cases.json`：固定包身份、全量及 21 项 CLI 结果。
- `final-evidence/runner-diagnostics.json` / `.log`：参数、实际序列化请求及日志故障检查。
- `final-evidence/no-optional-runtime.json`：缺可选运行时的只读结果。
- `final-accounting/`、`final-logs/` 与 `diagnostic-accounting/`、`diagnostic-logs/`：独立 claim、journal 与实际 runner 产物，保留未决与失败。
- `candidate-1/`、`candidate-2/`、`exports/`：固定快照及包；首审失败证据保留，未覆盖或伪装为最终通过。

原始输入、轨迹、包、脚本与日志只留本地，不上传 GitHub。最终独立复验全部退出 0；场景中预期失败/拒绝的退出 1/2 已由驱动逐项核对。实现子代理自测仅作定位参考，以上结果由主代理重新执行。

## 通过范围与限制

空卷安装结果只证明该既有镜像/当前平台上的哈希锁复现；基础镜像、其系统依赖与基础锁没有重新构建。干净包仍须独立挂载有权限的固定 vendor；不称完整自包含系统或其他架构通过。真实认证/服务连通、计量/账单、官方世界/C、判分、完整数据/资源、正式配送以及主办方最新限制下的 F.5 最终冻结仍须单独验收。无后台轮询、自动唤醒或 Antigravity 操作。
