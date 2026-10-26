# 模型与官方 runner 接入层独立审核

2026-10-26（Asia/Shanghai）。基线 `4fe5092c74508ca1a96e6d27c53bd76ee384b9de`；已通过 GitHub 核对 PR #6 `merged=true`，fetch 后从最新 `origin/main` 建立 `codex/model-runner-integration`，写入前工作区干净。

结论：**模型/官方 runner 接入层代码通过内部离线独立验收**。最终已审/已通过实现为 `b5f60ddd744a4f60497bd1e19f4fec01f76fd2dc`；首审和第二轮返工保留在下节。这里验证固定真实包和官方循环中的合成边界，不证明真实模型决策或任务完成。真实模型 API、真实 C 尝试及官方判分继续暂停；依赖安装与合成测试不消耗或重置真实 B/C 的 5 元预算。

## 范围与固定契约

一个显式 `gpt-6-luna` / `high` 子代理负责实现和 Docker 自测，主代理负责规格、独立审核、教学、文档与 GitHub；没有第二个代理或外部执行器。

固定上游 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，主代理读取时工作区干净。关键 Git blob：

| 固定文件 | blob |
| --- | --- |
| `openai_agents_runner.py` | `87657b79b535f340714542a745c1354b4e54dad0` |
| `openai_agents_local_tools.py` | `2783c35f7732f5eff73a022b16d2885e17c4dbde` |
| `nemotron_tool_protocol.py` | `d6fcab0173ab6c4df9f4a00e0c00ce4982c8ad15` |

官方 harness 固定安装 `openai-agents==0.13.6`、`openai==2.36.0`。本轮直接调用该官方 runner 的 `run_agent()` 和真实 SDK 循环，在模型 HTTP 与工具边界注入合成替身；不进入 `cb experiment run`/Harbor verifier，不创建官方任务世界，不改 vendor 或 grader。原 B/C/baseline 的真实入口继续拒绝。

请求依据为 [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) 与 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：thinking 经 SDK `extra_body` 提供，带 tools 的后续请求需回传历史 `reasoning_content`。工具调用与结果关联的通用说明见 [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)。账号可用性、真实模型响应及账单不由文档建立。

## 实际环境

复用原开发镜像 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，Linux arm64/aarch64、Python 3.12.15、解释器 `/opt/venv/bin/python`。初次标签 inspect 短暂报未找到，随后只读 context/image 核对确认缓存仍在；使用固定镜像 ID，没有 pull/重建基础镜像。

可选 SDK 依赖在 Docker 内准备到独立 `chi-model-deps` 卷，使用 `requirements-model.in/.lock` 的完整 hashed pins：openai-agents 0.13.6、openai 2.36.0、httpx 0.28.1、mcp 1.30.0、pydantic 2.14.1。基础镜像和原两份锁不升级，宿主不安装项目依赖。探索缓存 `/private/tmp/chi-model-deps` 保留，正式独立检查使用上述卷；未下载官方资源或浏览器。离线验收容器禁网，不挂 `.env`、模型/judge 凭据、Docker socket、手册、病例或评分数据。

| 接点 | 已验收行为 |
| --- | --- |
| 安装入口与可选锁 | 在 Docker 独立依赖层安装/审计固定包，原 dev 与 controller 保留 |
| `BudgetedMockTransport` | 接收真实 SDK 序列化，检查每次发送的预算/输入/输出/轮数后才调用 MockTransport；返回 usage 先核算再验证协议 |
| SDK converter 的局部包装 | 补齐原 SDK 丢失的空 content/reasoning；保留非空/None，附带模型/endpoint 来源，scope 退出恢复 |
| 官方 `run_agent()` | 使用官方 SDK 循环及系统提示，注入无 MCP 工具的 stub 和允许列表合成本地工具，不执行原 shell/file 工具 |
| 输出与错误 | runner 前独占 run-id 并 fsync 保留占位；主错与清理错分栏，未知用量总量为 null，已知前缀和合成价目另存 |

上游临时 `run_result.json` 在错误路径可能写零，未被当作用量依据或保留为官方证据；接入层以实际请求边界账本生成新 evidence。客户端固定占位 key，只作 SDK 参数，不读取或记录真实凭据。三轮/128 输出 token 的上限及价目是本层合成 fixture 配置，不是已冻结的真实 B/C profile。

## 独立审核与证据

主代理固定首候选 `07d32d7`，从 Git archive 只读快照在禁网 Docker 中运行全量 pytest：166 passed、53 subtests，退出 0；可选 SDK 已加载，没有以 skip 替代集成。首次挂载缺空目录导致容器未启动；补齐快照的空挂载点后成功，候选源码未改，该设置错误不记作任务失败。

主代理补充检查 7/7 暴露缺口，退出 1，首审未通过：

- 非法/已有 run-id 在跑完 runner 后才拒绝，已有文件还抛未捕获 FileExistsError。
- 用量标未知的账本仍可到达一次下层传输。
- 客户端构造失败后 SDK converter 补丁未恢复。
- not-found 查询未记录调用，下一轮同一 ID 被漏过并完成；含控制字符的 ID 也能执行。
- 最终响应缺 thinking profile 的 reasoning 字段仍称完成。

相关协议补查 15 项，13 通过；纯空白最终文本被接受、超大 usage 整数导致核算溢出两项纳入原 R2/R5，未扩大实现范围。问题按 R1–R5 交回同一子代理，另要求保留可重算的合成价目/换算元数据。

第二候选 `b3493c7fdac4c22976fad68ebf103b93d78ef477` 独立全量 174 passed、72 subtests；原 7 项和协议 15 项全部通过。补充 14 组实际 CLI/预算/状态检查，13 通过：两个真实 CLI 进程共用输出身份仅一个运行；首请求核算后第二请求预算不足，确实只发出一次请求并保留首个工具结果。最后一项发现清理错误覆盖原 HTTP 错误，交回同一子代理作 R3 的小范围记录修复，要求两类错误分别保留。

独立安装入口在禁网且 `UV_OFFLINE=1` 条件下审计现有独立依赖卷的 40 个锁定包，退出 0，无重复下载；基础镜像、`requirements.lock` 与 controller 锁未改。

最终候选只新增清理错误字段及相应回归，主代理重新导出 Git 快照独立复验：

| 最终主代理检查 | 实际结果 |
| --- | --- |
| 可选 SDK 加载的全量 pytest | 175 passed、72 subtests，退出 0；未跳过模型集成 |
| 首审身份/预算/setup/历史 7 项 | 7/7 通过，退出 0 |
| 协议补查 15 项 | 15/15 通过，退出 0 |
| 实际 CLI、进程争抢、第二请求预算与状态/清理 14 组 | 14/14 通过，退出 0 |
| 原基础镜像的 offline readiness 与单题 dry-run | 退出 0；不挂 SDK/凭据/vendor/data，未启动任务/创建 manifest |
| README 最小挂载离线命令 | 退出 0，实际三次合成发送、证据退出后可读 |
| 差异与上传范围 | 仅自有实现、合成测试、声明依赖与必要文档；vendor、锁定基础环境、真实 gate 与 judge 未改 |

36 个补充检查包括实际两个 CLI 进程争抢、重复文件不覆盖、非法身份不创建目录、HTTP/网络错误不重试、第二发送前预算停止、空/None 历史、无效批次零执行、缺失/超大用量、构造失败恢复，以及 HTTP 主错与清理错共存。SDK 的 HTTP/Agents 重试均实际设零并以 mock 响应发送次数复验；MCP 为无工具 stub，不把它写成真实 MCP 故障恢复已验证。

实际独立命令的项目目录写法如下。快照解包后只补空的 `vendor/chi-bench` 挂载点，不修改归档源码；检查脚本及输出均在忽略目录：

```sh
model_review_root="$PWD/runs/model-runner/review"
model_snapshot_root="$model_review_root/snapshot-final/chi-agent"
git -C .. archive --format=tar b5f60ddd744a4f60497bd1e19f4fec01f76fd2dc chi-agent > "$model_review_root/candidate-final.tar"

docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e MODEL_REVIEW_LABEL=b5f60dd \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro \
  -v "$model_snapshot_root:/workspace:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$model_review_root:/review:rw" -w /workspace \
  sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3 \
  /opt/venv/bin/python -m pytest -q -p no:cacheprovider
```

同一容器布局分别执行 `/review/independent-07d32d7.py`、`/review/protocol-boundaries.py`、`/review/final-boundaries.py`；最后一项实际以 subprocess 启动 CLI 及并发进程。原入口检查去掉依赖卷和 vendor 挂载，显式运行 `/opt/venv/bin/python scripts/check_readiness.py --mode offline` 及 README 原 dry-run 命令。安装脚本独立审计另用 `--network none -e UV_OFFLINE=1` 和可写依赖卷；不存在模型传输网络。

原始结果保存在忽略的 `runs/model-runner/review/`：前两轮 `candidate-<SHA>.tar` / `snapshot-<SHA>/`、`candidate-final.tar` / `snapshot-final/`、各轮 pytest/补充检查日志和按候选命名的结果，另有 `helper-07d32d7.log`、`legacy-entry-b5f60dd.log`、`readme-b5f60dd.log` / `readme-evidence/` 及 SDK 原转换核对脚本。首审失败输出仍在原日志/结果中；复验脚本只调整过输出结果文件名，未改原七项判定。子代理自测不代替本节独立证据，原始记录不上传 GitHub。

## 未验证边界

真实 provider 传输/认证、tokenizer/服务端 framing、真实价格与 usage/账单、官方世界中的 B/C、官方 reward、其他架构、OpenSpec CLI 与阻塞调用硬取消未验证。字节计数与合成价目不能成为付费入口或精确账单上限的证明。新直接 runner 路径只作离线验证；原 `cb experiment run` 的无评分 gate 保持 unsupported，不能由新路径推断 Harbor 跳过评分已接通。

同一 Python 进程内只串行调用临时适配，不提供并发全局补丁隔离。本地 run-id 排他不是 C 的 campaign/task/upstream 尝试资格，也不提供跨目录/分布式幂等。异常进程退出保留占位身份，但不承诺最终 evidence 的原子替换、主机断电持久性或完整中断轨迹。没有真实任务/reward/费用或完整用户验收的证据。
