# bootstrap-baseline/A 独立审核

日期：2026-10-25（Asia/Shanghai）。仅 A：官方环境与不触发模型的只读工具接入；B/C、参赛模型 API 与官方判分暂停。

## 身份与范围

- 起点：`d1c9f991eda9548974838f72578078f9f9b05757` / `origin/main`；工作分支 `codex/bootstrap-baseline-a`。
- 接手时仅学习文档未提交。其补丁完整保存于 `a1b505d`，主代理用 `cmp` 核对与原补丁一致；该提交同时定义 A 规格。
- 固定实现候选：`a173409416cf111ec2f2cc45247aa592b5ddd77e`；前候选 `71d8cdd` 的真实构建预检又暴露流式/时限问题，`6ca0e7b` 修复流式/取消后又发现构建静默下载需要单独等待策略，均已形成独立修复提交。下列最终离线检查来自新候选的 `git archive`，不混入后续审核/学习文档。
- 两个子代理请求设置均为 `gpt-6-luna` / `high`，任务身份 `/root/a_environment`、`/root/a_probe`。分别负责环境/调度与探针/协议；实现写入串行，停止后由主代理固定候选并复验。未创建下级代理，开发模型用量不归入参赛 API 预算。
- 官方源码：`4444a07fa68a4f1623f841a292a54e284fc8e7f7`；公开数据：`5ce88104df2a91e057619eb70fb51f56fc5949eb`，仅选定任务及两个共享世界，共 7 个运行文件，不是全量数据集。手册沿用批准的固定版本 `f1210b294904792541116852f6074df8b84d89dd` / 1,292 文件。

## 当前结论

**A 在本次授权范围内通过独立验收**：固定官方环境、真实 MCP 发现与脚本只读查询、挂载/网络/解释器身份、清理及证据持久化均有实际证据。代码身份为 `a173409416cf111ec2f2cc45247aa592b5ddd77e`。没有 Agent trial、模型工具往返或官方 verdict；官方 reward 与实测模型用量/费用均未产生。用户完整验收与 PR 合并由用户另行决定。

## 生产入口与边界

`scripts/a_environment.py` 负责固定资源、官方 Docker 上下文与镜像、任务启动、实际挂载/网络/解释器身份、限时执行、日志及清理。仅 A controller 通过 SDK 复用已有引擎；默认 D0 `compose.yaml` 不挂 socket。官方任务只挂结果目录与只读探针单文件，使用 internal network、不发布宿主机端口，不转发模型、judge、HF 或外部 FHIR 配置。

`scripts/a_tools_probe.py` 在任务容器内执行：`ClientSession.initialize()` → `list_tools()` → 核对完整名称与参数契约 → 单次 `call_tool('cases.list_cases', arguments={})` → 检查响应。只接受任务内 provider endpoint 与 `/logs/artifacts/probe`；未知名称/不兼容 schema 在调用前拒绝，超时不重试。初始化、发现、调用、响应校验、嵌套异常、调用/响应/效果未知分别记录。

固定官方调用链已由主代理核查：`cb serve` → `WorldService.from_env` / `ServiceContext.build_from_env` → `build_provider_mcp` 注册角色工具 → `CasesService.list_cases` → SQLite 读取及工作流摘要计算。查询不改变申请业务状态、不调用模型；`ctx.audit('pa_queue', 'list_cases')` 会写一条读取审计。工具发起者是脚本，成功也不能证明模型会选择工具或自主完成业务任务。源码与[官方任务容器入口](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/docker/entrypoint.sh)分别核对。

## 离线独立证据

所有安装、下载、测试和调试在 Docker。快照检查无网络、无 socket、无真实凭据。主代理独立执行结果：

| 环境 | 项目测试 | 独立补充方法 | 结果 |
| --- | --- | --- | --- |
| Python 3.13.17 / aarch64，D0 开发镜像 | 115 + 19 subtests | 6 | 均退出 0 |
| Python 3.12.15 / aarch64，单独离线审查镜像 | 115 + 19 subtests | 6 | 均退出 0 |

Python 3.12 离线镜像不含官方 fixtures，也未启动官方服务；其通过只证明本项目离线代码兼容，不代替官方任务镜像验证。

镜像身份：

- 开发：`sha256:e0cd3bb32b0f48c2b20b566b7635ddd6dcce44ae040f9f0615f2e032b95b3997`。
- A controller：`sha256:33b2f2b1d00a41441f85a4d7719fb0603fe7af07b61cb80550796bdae856d9f9`；独立 `/opt/a-venv`，20 个锁定依赖。
- Python 3.12 离线审查：`sha256:85e05a6324777601e3e7ceaa5069109cbb283b1993d994159305650cc5db6b0e`。

实际快照检查先 `git archive a173409…`，在各镜像内解包至 `/candidate`，然后执行：

```sh
cd /candidate/chi-agent
python -m pytest -q
# 独立容器，使用相同快照
python /evidence/independent_checks.py
```

Docker 参数为 `--rm --network none`，只挂忽略的 `runs/a-review` 证据目录。最终日志以 `a173409-` 为前缀：`python313-tests.log`、`python312-tests.log`、`python313-independent.log`、`python312-independent.log`；独立脚本与候选 tar 同目录保存，不上传。前候选 Python 3.12 首次检查命令因预建 WORKDIR 与 `mkdir` 冲突而未运行测试；改为 `mkdir -p` 后通过，未因此修改候选。新增 5 项构建生命周期/等待策略测试，最终数量为上表所列。

主代理预检曾复现并交回修复：重复 run-id 拒绝后误删旧容器/网络；`required:null` 或 `minProperties:1` 时仍发送工具调用；布尔退出码被当作整数成功。最终 6 项独立方法覆盖上述反例、外来资源保护及凭据不继承。子代理额外验证直接 `pytest` 与 `python -m pytest` 均可收集全套测试；这些自测与主代理结果分别记录。

## 官方环境授权与实际接入

官方初始化固定读取 `fixtures/expectations.json`。首次 `prepare_build_context` 被自动审批拒绝，理由为该文件可能向 Agent 暴露 verifier 内容；当时停止且没有绕行。用户随后明确答复“允许，仅供隔离官方服务初始化”，仅允许它供无 Agent、无模型、无判分的官方服务使用。探针不读或输出评分内容，GitHub 不上传 fixtures/手册/原始响应。后续实际结果在此记录，不沿用拒绝前的未执行状态冒充证据。

首次官方镜像构建约 11 分钟未返回，主代理读取 controller 中 Docker SDK 7.1 实现后确认：高层 `ImageCollection.build()` 在返回前会内部消费全部构建事件，因此候选的外层总 deadline 不能及时运行，且无法在构建过程中读取进度。只中断这一次请求，退出 130；指定 run-id 的 controller、world/network、最终镜像均未留存，没有执行全局清理或启动任务。改用同一 Engine API 的低级流式接口并固定 `6ca0e7b` 后，主代理取得上表全量独立回归；原始事件即时保存、每轮检查 deadline，取消也记录为 cancelled 并传播中断，不伪造 success。前候选离线结果不自动覆盖新差异。

第二次构建（`a-luna-20261025-02`）留下 209 个事件后以 `ReadTimeoutError` 失败；最后公开输出是官方 Step 10/37 中的 Debian 系统库下载，没有上游 error 事件，没有 world/probe。新候选将首次 `build-image` 与任务等待分开：构建总预算 1800 秒、单次无日志读取最多 300 秒；事件间检查总时限，不声称精确切断正在进行的读取。普通 Docker API 仍 30 秒，`run-probe` 仍 900 秒；没有扩大 Agent 运行/费用范围。原始构建事件、取消/失败状态均留在忽略目录 `runs/a-environment/builds/`。

最终真实接入：

| 项目 | 子代理自测 | 主代理独立复验 |
| --- | --- | --- |
| 新世界 run-id | `a-luna-20261025-03` | `a-review-20261025-01` |
| 官方镜像 ID | `sha256:2486582544e49e190598bb4815460dffecba860ae3fee4f0b1ff29c2b3e0d3fb` | `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50` |
| 实测运行环境 | Python 3.12.15 / linux arm64 | Python 3.12.15 / linux arm64 |
| 官方 MCP 启动完成 | 5.583 秒 | 6.713 秒 |
| 探针协议全过程 | 106 毫秒，success/valid | 106 毫秒，success/valid |
| 查询及结果 | `cases.list_cases({})`，`items=[]` | 同一合法查询，`items=[]` |
| 清理及回读 | 容器/网络删除，status 为 absent | 独立 status 退出 0，容器/网络均 absent |

主代理执行的真实入口（项目目录 `chi-agent/`）：

```sh
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py build-image --run-id a-review-20261025-01
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py run-probe --run-id a-review-20261025-01 --probe-script /workspace/scripts/a_tools_probe.py
docker compose -f compose.a.yaml run --rm a-control python scripts/a_environment.py status --run-id a-review-20261025-01
```

三条命令均退出 0。主代理从同一固定源码/资源重新准备上下文并构建，利用已有依赖层缓存；镜像带各自 run-id 标签，因此 ID 不同。210 个实际上游构建文件的 tree SHA-256 为 `de994338d93c283a59590da1d9c679fd11f27e3ea2db957a37924d161f57a796`；7 个数据文件逐项散列核验，手册 1,292 文件共 32,881,348 字节通过既有清单校验。

主代理实际核查：任务网络 `Internal=true`、仅连接自己的网络、不发布端口；挂载目标只有 `/logs/artifacts` 与只读 `/tmp/a_tools_probe.py`；宿主/容器日志标记与探针哈希一致；实际环境键无模型/judge/HF/FHIR 凭据。探针脚本 SHA-256 为 `5bf4d5586ae8c3d1e805dc34334b2fd2ad0b8eef4718d11d304c41c9b0c30c39`。

实时 MCP 协议为 `2025-11-25`，serverInfo 为 `chi_bench` / SDK `1.27.1`；发现 30 个角色工具。选定工具只有可选 `status` 字段，无必填参数，现场契约核验后实际发送 `{}`。两次查询均记录 `call_invoked=true`、`call_response_received=true`、`call_result_status=valid`、`model_calls=0`、`tool_retries=0`；这只证明合法读取往返，空列表不等于取得病例或推进业务。

两次输入 schema SHA-256 均为 `0b05d4603b306efa08fff0c92239f04212597b2401cfe2e8ba5965028d8a170d`，原始响应文件 SHA-256 均为 `85e7283382d4670afc25e61e13cf02a288d3a79a92472232aa1db693d71142fd`。审计效果记为成功 handler 预期产生，未额外读取数据库证明审计落库；没有声称业务写入或模型选择工具。

官方构建日志分别在忽略的 `runs/a-environment/builds/a-luna-20261025-03-db92f4fc9cc34352a71c5a8874db65c0.jsonl`（819 个事件）及 `a-review-20261025-01-47fa4acb0a6647faaa3c4b078def97dc.jsonl`。每个 run 目录的 `probe/`、`run-identity.json`、`stage-result.json`、服务日志和 stdout/stderr 在容器清理后仍可读取；主代理只提取元数据/数量/哈希，没有读取或输出病例响应或评分内容。上述 raw 文件及含手册的本地任务镜像均不上传。

## 保留边界

不运行 B/C、模型 API、模拟对话或官方判分，不生成 scorecard，不消耗或扩大 5 元参赛运行预算。OpenSpec CLI、其他架构、模型限额/账单、无评分 Agent 入口与正式任务能力仍需各自阶段验证。PR 由用户审核并决定合并；主代理不合并、不启用 auto-merge。
