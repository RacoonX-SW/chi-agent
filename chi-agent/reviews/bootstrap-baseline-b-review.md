# B 离线模型工具往返独立审核

2026-10-26（Asia/Shanghai）。基线 `e888377e428f5cdb9030b15ffb4325deb57e8365`；GitHub 已核对 PR #4 `merged=true`，其合并提交即本基线。工作分支为 `codex/bootstrap-baseline-b-offline`，开工时工作区干净。

结论：**B 规格与离线实现通过内部独立验收**。最终已审/已通过实现为 `6f9e9fadb89f9972f4483666489d83c9b371f67f`。真实模型 API、官方 runner 集成、C、自主任务与官方判分未运行；真实 provider usage/cost 和 official reward 均为 null。文档及后续存储提交不替代这一实现身份；用户审核/合并仍由用户决定。

## 变更与固定身份

一个 `gpt-6-luna` / `high` 子代理实现和 Docker 自测，主代理负责规格、教学、Git 和独立复验；没有第二个实现代理或外部执行器。子代理每次停止写入后，主代理显式提交并另取 `git archive` 快照审核。

| 入口 | 行为 |
| --- | --- |
| `scripts/b_model_adapter.py` | 构造候选 Chat Completions 离线配置封套；保留历史；整批校验合成工具名称、类型、参数、reasoning 字段及唯一调用 ID |
| `scripts/b_model_probe.py::run_probe` | 每请求预算/输入门禁；记录返回用量；校验响应、派发合成工具并匹配结果；区分最终完成、拒绝、超时及用量未知 |
| `scripts/b_model_probe.py::main` | 固定合成 scenario，拒绝 live；限制参数/run-id，独占创建本地输出目录，重复身份不覆盖 |
| `tests/test_b_model_probe.py` | 历史/关联、批次拒绝、重复 ID、未知用量、完成条件、异常和配置回归 |
| 既有 OpenSpec / README | 补充 B 离线契约、参考 runner 缺口及实际可执行的最小挂载命令 |

`run_baseline.py`、D0 gate、官方源码、Dockerfile 和依赖锁没有修改，真实任务入口的预算/无评分门禁保持原行为。

## 首审问题与返工

首候选 `6ce606539c454bceb5df321a936119e38c64b46f` 独立运行原测试通过，但主代理补充的 8 个场景有 6 项暴露缺口，未验收：

- 最终响应缺 usage 仍标完成；首轮缺 usage 的累计摘要仍写成零。
- 没有工具往返即结束、或 `finish_reason=length` 的截断响应，仍标完成。
- 合法最终 `tool_calls=null` 被拒绝；反而不支持的工具调用 type 仍被执行。

这些问题直接交回同一子代理。另补充配置限额拒绝 bool/非整数、核算被拒消息的有效用量，以及两次调用同处一个响应不等于两轮往返。最终候选重新固定后，主代理独立重跑原失败场景和受影响行为，全部通过；没有采用子代理重跑主代理脚本的结果替代独立复验。

## 实际环境与命令

复用现有 `chi-agent-dev:latest`，实际镜像为 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，Linux arm64/aarch64、Python 3.12.15。使用 `/opt/venv/bin/python`，既有 PyYAML 6.0.3、pytest 9.1.1 可导入；没有安装、重建、下载官方资源或浏览器。

独立容器均为 `--network none`，源码只读，临时目录可写；仅实际 CLI 检查另挂本轮输出目录。无 `.env`、模型/judge 凭据、手册、数据、vendor 或 Docker socket。下列为实际检查命令的路径变量写法，从 `chi-agent/` 执行，快照已解包到相应目录。

```sh
# 从固定代码导出，而非读取继续写入中的实现
b_review_root="$PWD/runs/b-offline/review"
b_snapshot_root="$b_review_root/snapshot-final/chi-agent"
git -C .. archive --format=tar 6f9e9fadb89f9972f4483666489d83c9b371f67f chi-agent > "$b_review_root/candidate-final.tar"

# 主代理全量回归；源码用导出快照挂载
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$b_snapshot_root:/workspace:ro" -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python -m pytest -q -p no:cacheprovider

# 独立边界检查；只增加本轮审核脚本/结果目录
docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$b_snapshot_root:/workspace:ro" \
  -v "$b_review_root:/review:rw" -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python /review/independent_check.py
```

上述固定快照还实际执行 `scripts/check_readiness.py --mode offline` 及 README 的单题 `run_baseline.py --dry-run`。`cli_check.py` 另挂 `cli-output/` 到 `/workspace/runs/b-model`，通过 subprocess 启动真实 B CLI，检查退出码与退出后证据。README 的仅脚本/输出挂载命令也已单独运行成功。

环境排查有两处非业务失败：子代理最初用 `sh -lc` 改写 PATH，绕过已有 venv；改为明确解释器后无需重装，临时 AST 提取绕法已删除。主代理首次 CLI 容器因快照缺少被忽略的 runs 空挂载点而在启动前退出 125；补建空目录后重试成功，候选源码未变。对应日志保留，不把它们记成模型或官方任务失败。

## 独立结果

| 检查 | 结果 |
| --- | --- |
| 固定快照全量 pytest | 131 passed，23 subtests；退出 0 |
| 主代理独立合成边界 | 22/22；退出 0 |
| 实际 B CLI | 11/11；检查脚本退出 0；各场景使用预期的 0/1/2 退出码 |
| offline readiness / 单题 dry-run / README B 示例 | 均退出 0；dry-run 未启动任务或创建 manifest |
| Git 差异、上传范围、格式与文档引用 | 检查受本次变更影响的文件；原始证据不暂存 |

成功示例有三次合成请求、两轮工具执行和最终正常响应。第二/三次请求中的原 assistant 内容、不透明 reasoning 字符串、调用 ID/参数及配对结果已逐项核对。合成用量为输入 60、输出 19；仅按记录的合成价格/换算可重算示例成本，不计入真实 B/C 预算。

补充场景涵盖：最终缺用量、无往返/轮次不足/单批两调用、截断或空最终文本、null/空调用列表、结束原因不一致、非法 type/参数批次、无效配置、输出用量越界、历史增长后的输入界限、首/第二请求前预算不足、未知价格。拒绝和超时发生在工具之后时，只保留一次已执行效果，不自动重试或重放；缺 usage 时累计总量/成本为 null，已知部分另列。

实际 CLI 还验证 live 拒绝、轮数/输入/输出限额、重复 run-id 的证据哈希不变以及路径穿越 ID 被拒绝。用户理解小题尚无回答，学习账本没有升级其掌握状态。

## 证据与限制

主代理原始证据留在忽略的 `runs/b-offline/review/`：两份候选 tar/快照、`runtime.log`、`pytest.log`/`pytest-final.log`、`independent_check-initial.py` 与初审结果、`independent_check.py` 与最终 22 项结果、`cli_check.py`/结果、`cli-output/`、`entrypoints-final.log`、`readme-command.log`、挂载失败日志。实现者的合成 CLI 证据在 `runs/b-model/offline-b-20261026-01..09/`；早期与最终结果分别保留，不冒充同一候选。

本轮是独立的协议逻辑探针，不是官方 runner 的 Agent 循环。request 包含路由元数据，不能直接作为 SDK 参数或 HTTP body；UTF-8 序列化字节界限也没有验证真实 tokenizer/服务端 framing。后续真实 B 还须按 design 的接入缺口核对 SDK 序列化、思考历史、逐请求预算回调、重试设置、真实返回模型和价格/用量来源。本轮没有验证真实传输中断、服务商账单或账户硬限额，不产生官方任务成功率或 reward。OpenSpec CLI 及其他架构未验证。
