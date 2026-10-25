# C 离线单次执行控制独立审核

2026-10-26（Asia/Shanghai）。基线 `4726444d21ba404e02d8fa1005b44b2f547c9a0f`，即用户合并 PR #5 后的实际主线；未写入的 C 分支先快进到该基线再开始开发。分支 `codex/bootstrap-baseline-c-offline`。

结论：**C 离线执行控制通过内部独立验收**。最终已审/已通过实现为 `6afd14af71dbbff43404490b0ba7c3e943f93e94`。这不是正式 C 任务执行验收；真实模型 API、官方 runner 接入、真实 C 尝试和官方判分未运行，真实 usage/cost/reward 为 null，任务结果 unknown。文档/存储提交不替代实现身份，用户审核和合并仍由用户决定。

## 实现及边界

一个显式 `gpt-6-luna` / `high` 子代理实现与 Docker 自测，主代理负责规格、独立复验、教学、文档和 Git。没有第二个实现代理；每轮停写后主代理固定提交并导出 Git 快照。

只新增两个实现文件：`scripts/c_run_control.py` 和 `tests/test_c_run_control.py`。控制器复用已有 `build_experiment_config()` 与 `evaluate_budget()`，没有修改原 baseline/D0 gate、B 实现、官方源码、Dockerfile 或依赖锁。

| 入口/机制 | 已实现行为 |
| --- | --- |
| `RunSpec` / `plan()` | 单题、单次、并发一、无重试和严格类型校验；纯预览不写文件、不取得 claim、不调用 backend |
| `BudgetEvidence` | B 已知花费纳入同一 5 元规划，来源/价格/换算缺失则阻断；合成账目与真实 null 结果分开 |
| `rehearse()` | 取得持久 claim 后创建新的合成 handle，调用 runner 一次，再 finally 清理；没有模型工具循环 |
| 独占 claim | campaign/task/upstream 固定作用域，run-id 改变不重置资格；O_EXCL 创建、写入并 fsync 后才进入 backend |
| 资源与结果 | 校验 handle 类型、严格 owned、run/campaign/synthetic namespace 和安全资源 ID；记录部分创建、主错、清理错及证据错 |
| CLI | `plan`/完成演练退出 0，受控阻断/冲突/失败退出 1，非法输入/重复输出身份/live 拒绝退出 2 |

CLI 的 backend 只进行纯 Python 内存操作。候选 harness、模型轮数和时限标为 `configured_unverified`，没有官方任务世界、MCP、Docker API、凭据加载或 SDK/HTTP 传输。共享实际预算没有被演练消费，真正 C 尝试 namespace 也未被占用。

## 独立审核与返工

首候选 `62dd7e7d3b0fcb96fc0552c1aae6467bc5c54046` 独立全量回归通过，但主代理补充复现发现七项缺口，未验收：外来资源自称 owned 就被执行/清理；坏 handle 导致 finally 再抛异常而无终态；B 花费缺来源仍放行；attempts 浮点数被接受；返回合成总成本超 cap 仍称完成；usage 附加字段原样落盘；清理开始前写日志失败会跳过清理。

交回同一子代理后，候选 `6f520344a7f9797363791c23993dfb586f0c668f` 修复上述问题并统一 CLI 非成功退出码。主代理独立全量及 CLI 通过，26 个补充边界中仍有一项失败：合法的 64 字符 run-id 生成更长资源 ID，被错误复用的长度约束拒绝。最终候选区分 run-id/资源 ID 校验，同时保留严格归属检查，并补充正常/部分创建及非法资源路径回归。

最终结果由主代理从新快照独立取得，不使用子代理自测替代。

## 实际环境与检查

复用原开发镜像 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，Linux arm64/aarch64、Python 3.12.15；解释器 `/opt/venv/bin/python`，原 PyYAML 6.0.3 与 pytest 9.1.1 可导入。没有安装/下载依赖、重建镜像、下载官方资源或浏览器。

独立容器均使用 `--network none --read-only --tmpfs /tmp`，源码快照只读，审核目录/合成输出另挂可写；没有 `.env`、模型/judge 凭据、data、vendor、手册或 Docker socket。实际命令按项目目录写法如下，快照已解包：

```sh
c_review_root="$PWD/runs/c-offline/review"
c_snapshot_root="$c_review_root/snapshot-accepted/chi-agent"
git -C .. archive --format=tar 6afd14af71dbbff43404490b0ba7c3e943f93e94 chi-agent > "$c_review_root/candidate-accepted.tar"

docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$c_snapshot_root:/workspace:ro" -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python -m pytest -q -p no:cacheprovider

# 独立边界；CLI 检查使用相同挂载和 cli-accepted-check.py
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$c_snapshot_root:/workspace:ro" \
  -v "$c_review_root:/review:rw" -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python /review/independent-final.py
```

实际复验命令直接使用上列固定镜像 ID；示例标签与该 ID 相同。首次标签查询短暂失败，随后的 context/ID 核查确认缓存仍存在，未 pull/重建。审核 CLI 的一次证据导出目录复用冲突通过新输出目录重试解决，候选源码未变；未把这些设置失败记为模型或任务失败。

| 主代理实际独立检查 | 最终结果 |
| --- | --- |
| 固定快照 pytest | 151 passed、38 subtests，退出 0；其中新增 C 专项 20 个测试方法 |
| 独立合成边界 | 26/26，退出 0 |
| 实际 CLI 场景、跨 run-id 重演拒绝及证据不覆盖 | 22/22，检查脚本退出 0；各子进程退出码按约定核对 |
| 最小挂载 README 演练命令 | 退出 0，manifest 与 claim 在退出后可读 |
| 原 offline readiness / 单题 dry-run | 退出 0；dry-run 未启动任务或创建 manifest |
| 差异/上传范围/格式及文档路径引用 | 仅代码、合成测试与必要文档；原始证据不暂存 |

26 个独立边界包括当前/外来/坏 handle、严格 bool 所有权、部分创建、来源类型、非整数限额、超预算结果、usage 字段白名单、主错与清理错并存、清理开始及持续写盘失败、预算精确预留边界、计划零写入、坏旧 claim、跨进程争抢、进程直接退出和最大合法身份。

跨进程检查实际启动两个隔离子进程，共享同一合成账本，只有一个进入 runner。中断检查在 create 边界中调用 `os._exit(17)`，不执行 finally；随后换 run-id 仍被旧 started claim 阻断。写盘错误注入时清理仍尝试，返回 `evidence_write_failed`；持续写盘失败下只保证保留原 claim 和尽力清理，不承诺完整终态已经写入磁盘。

实际 CLI 在只读快照验证 plan/live；各 rehearsal 场景使用固定代码的独立临时副本，核对脚本哈希后运行，并把合成输出导出。这样不同测试场景拥有独立账本，不能把测试隔离当作真实重试或计费记录。

## 证据与后续缺口

原始证据集中在忽略的 `runs/c-offline/review/`：三个固定候选 tar/快照、`runtime.log`、各轮 pytest/独立检查日志和结果、`independent-initial.py`、`independent-final.py`、`cli-accepted-check.py`/结果、`cli-artifacts-accepted-6afd14a/`、README 与原入口日志。首审及第二轮失败结果分别保留。子代理最终自测日志位于 `runs/c-control/review-r2-r6-20261026/`，其演练输出也保留在同一忽略区域。

该 claim 只约束同一持久账本根目录中的固定作用域，不提供跨目录/跨主机全局幂等服务。已验证的是进程退出，不是主机断电、真实 Docker 删除或网络/磁盘故障恢复。时限和模型参数只是候选约束，未实现对任意阻塞调用的硬取消，也未接入官方 runner 的逐请求预算钩子。

正式 C 仍需真实 B profile/harness 连续往返、真实序列化与计量/价目来源、重试控制及已核实无评分入口；当前没有上游 skip-judge 参数实证。本轮没有修改 judge、运行官方评分或产生业务通过率；OpenSpec CLI 与其他架构也未补验。学习理解反馈只维护在原学习账本，不因代理实现/测试通过而认定用户已实践。
