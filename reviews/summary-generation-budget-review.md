# 摘要专用生成预算 v2：实现与独立离线审核

日期：2026-11-05（Asia/Shanghai）。结论：实现候选 `62a871f96154652d5666a0e3ffc64b08aeeff014` 在本报告限定离线范围通过，可 push / 开 base=main PR。真实 Go 摘要兼容、触发后成功、忠实度、净费用收益及官方成绩均未通过本轮证明。

## 1. 范围、协作与固定候选

- 基线为已合并 PR56 的 `origin/main=6702cf2eb39b98a2ea39f5f6f60f042d460c9e10`；收尾前再次 fetch，主线未变化。独立分支 `codex/summary-generation-budget`，未复用 PR57 的未合并规划作代码基线。
- 用户要求撤下 PR57 原 E 摘要接续卡，改由 GPT 主代理 + 一个显式 `gpt-6.1-terra` / `high` 子代理完成摘要生成预算修正。PR57 当前 head `c10484fb1ca374dfa8d11f6ebdba467f4bd795e2`，只剩 A–D 规划；未合并，未实现其他卡。
- 主代理冻结[有界契约](../openspec/changes/summary-generation-budget/proposal.md)，子代理串行写生产和测试并 Docker 自测，停止后主代理补包内 runbook、提交固定候选，再从 `git archive` 导出快照独立检查。最终存储提交仅追加本报告、短状态及任务勾选，不改变被审生产/包成员。
- 不读 Key / `.env`，不做真实模型、摘要、continuation、coding-B、业务 C、患者请求、world / Trial / judge 或发布；不核销、重发、迁移旧 pending，不读取隐藏 expectations / solution / verifier 调参。

## 2. 最终行为与调用链

新增精确显式版本 `chi-input-summary-v2`，summary 单次生成 `max_tokens=32768`；旧 v1 保持 8192，缺省仍关闭。`role_operator` 配置透传 → entry parser / launch 版本 → runtime / guard → `summary_request` → 请求校验 / journal reserve → usage settle / 上限校验 → 原候选检查与 checkpoint → 后继 main。journal 严格历史校验按每个 run 自身 launch 版本重建 summary body，不能把旧 v1 请求解释成 v2。

| 用途 | 上限 / 本次变化 |
| --- | --- |
| summary v1 / v2 | 8192 / 32768；只有显式 v2 使用新值 |
| main / 主恢复 continuation / patient | 各 8192，未扩大 |
| confirmation / coding-B | 32768 / 1024，未扩大 |
| 摘要候选 JSON | 原 32768 UTF-8 bytes、原 schema / 来源 / 保护校验，未扩大 |
| 请求计数 | 每 run 最多一次 summary，仍占共享 50，须留后继 main 名额；辅助 10 不变 |

模型、端点、thinking enabled / high、任务提示、选区与阈值、时间窗口不变；无第二摘要、summary continuation、额外请求或自动重试。摘要与输出恢复 / Y 仍互斥。context 原算法会按实际请求 `max_tokens` 预留，新摘要多占 24576 生成 token 余量；上下文不足仍在派发前停止。

`GoChiHarness` 当前仍不透传摘要开关、默认关闭；正式配置采用由后续 A–D/C 单独核定。本 PR 只提供新版本能力，不把能力写入 launch 等同于已经触发或完成。

## 3. 独立环境与测试

固定快照：`/private/tmp/chi-summary-budget-review-20261105/snapshot/chi-agent`。项目源码只读；单独挂载 `runs-main` / `runs-controller` 为可写测试资源；官方 vendor 与依赖卷只读。没有挂入凭据、真实输出目录或 Docker socket；`--pull never --network none --read-only`，仅 `/tmp` tmpfs 及指定输出可写。

- dev image：`sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，`/opt/venv/bin/python`，Python 3.12。
- controller：`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，`/opt/a-venv/bin/python`，Python 3.12。
- 原卷 `chi-h-root-model-deps-20261027-v1` / `chi-k-pdf-deps-20261027-v1`；无安装 / 升级。

主代理实际独立执行（不是引用子代理自测结果）：

| 检查 | 实测结果 |
| --- | --- |
| 适用 pytest：`-m pytest tests --ignore=tests/test_dev_patient_adapter.py --ignore=tests/test_dev_patient_network.py -q` | **899 passed、13 skipped、293 subtests passed**，26.44s；一条只读源码无法写 pytest cache 的 warning |
| controller：`-m unittest tests.test_role_operator_config tests.test_role_validation_wiring -v` | **12 tests OK** |
| 实际 SDK + MockTransport | v1 原成功路径保留；v2 合成上报 output 9000 / 32768 可 settle、安装 checkpoint、发后继 main，并严格 inspect；v1 的 9000、v2 的 32769 先结算再拒绝，绝不安装 |
| v2 错请求 max / context 边界 | 错 8192 在派发前拒绝；实际 reserve 32768，精确适用及少 1 边界通过；其他用途上限保持 |
| 候选 / 生命周期回归 | 坏 JSON / 空 / 重复键、引用 / 保护变化、超 32KiB、length / tools、未知 usage / cancel、四处持久化故障停止；无第二摘要 / 隐式恢复，已知费用保留，未知 pending 不清 |
| 主代理额外构造 v2 不减小反例 | 较短可压缩前缀 + 两段各 40000 字节保留观察，合法但膨胀的候选返回后 `chi_summary_invalid`；仅 1 次合成 summary、已 settled、无 checkpoint / 后继 main，严格 inspect 通过 |

两项缺 `anthropic` 的模块显式排除，13 skips 保留其原义；这不是完整环境 / unittest 全绿声明。SDK 测试的 token 数是合成响应上报值，不是实际生成了相应长度的正文，也不证明模型或 Go 接受新值。

本轮第一次独立容器因 archive 中无空 `runs` 挂载点而未启动（exit 125）；补齐空挂载目录后执行上述测试。独立脚本最初误用账本 error 字段和候选异常类型，已修正夹具；另一过大保留窗口先被 context 拒绝，缩至可用窗口才到达候选拒绝点。没有因此改变生产代码或放宽 guard。子代理自测期间曾因错写镜像 ID 发起未成功的镜像查询并中断；后续固定 ID / `--pull never`，未下载或替换镜像，无真实模型请求。

独立日志 / 可复现脚本最初写在 `/private/tmp/chi-summary-budget-review-20261105/`，之后连同新导出包保存到新的忽略目录 `runs/summary-generation-budget-20261105/`：`pytest.log`、`controller.log`、`build.log`、`preflight.log`、`check.log`、`independent/build.py`、`independent/check.py`。只复制新产物，没有覆盖任何旧运行；未上传原始轨迹 / 账本 / 任务载荷。

## 4. 当前树重建的交付身份

在同一只读快照内分别调用 `go_chi_bundle.build_bundle`、`evaluation_bundle.build_bundle`、`go_chi_release.build_release` 并验证；release 明确绑定上述实现提交，不隐称绑定后续文档存储提交。

| 项目 | 实测身份 |
| --- | --- |
| 新 Go canonical bundle manifest | `76be66204dcbc10d5fee35e2669fff598555423ba65e84ef9669cec00e5d3bd0` |
| 新 runtime identity | `5baa57c280645e6c83af0d1574cece73acdcc2d5ad4bdc1b0ab558f5b93410b5` |
| 新 release manifest（raw SHA256） | `e139fa998766b76973510502ed2b114a823ed197ccb396a9efd317238116aa2c` |
| release source_commit | `62a871f96154652d5666a0e3ffc64b08aeeff014` |
| 旧 evaluation canonical manifest | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，不变 |

导出为上述证据根的 `exports/go`、`exports/evaluation`、`exports/release`；Go 与 release 内包相同，release verifier valid。与原冻结 Go manifest 逐成员比较，41 成员中只有 8 项变化：`RUN_CHI_GO.md`、`profiles/go-chi-entry.json`、`scripts/go_chi_{entry,guard,journal,policy,runtime,summary}.py`；其余 33 项一致。`RUN_CHI_GO.md` 是包成员，本次说明调整有意纳入新身份，不再声称只改包外。

独立 release/package 挂为 `/package:ro`，外部 vendor / 依赖卷只读、禁网无 Key，用 `/usr/local/bin/python -S /package/scripts/go_chi_entry.py preflight --bundle-sha256 <上表新 manifest>` 实际得到 `identity_verified`、upstream clean、`official_reward=null`。真实 profile 与内存常量未打桩。preflight 只证明离线身份 / 导入，不证明业务 / MCP / 模型或执行许可。

新身份没有真实 B 收据，旧 B 不能证明新包已实跑。将来任何真实使用先按新包重绑新 B，并单独获准；不得套用已耗尽的 B / S 许可或剩余次数。

## 5. 历史保留与审核边界

主代理只读挂载原 `runs/validation-live-20261104/state`，用新 reader 对原 identity / 同一 raw SHA 严格 inspect：`inspected`；120 个文件前后 hash 全同，清单保存在本地 `old-s-inventory.json`。accounting 仍为 `91412a231c2407fc5a32663376bd1cd2226325b18e02b4c78ba6bc4fde872c41`。

`vprep-s-001` 仍是 `failed / chi_summary_invalid`，19 main + 1 summary 全部 settled，v1 summary max 8192，pending / halted null，candidate / checkpoint null、projections 空。原失败、旧 unknown / payer-010 pending 和旧候选包没有被本轮新通过覆盖。未重新创建旧 attempt、未重发请求或换账根；原 S [失败诊断](summary-failure-diagnosis.md)结论保留。

未发现阻断实现问题。非阻断剩余条件：32768 只是本轮离线候选参数；Go 是否接受、同一 large selection 能否在 high 下结束、240s / 300s 窗口是否够用、是否忠实和更省钱仍须分别取证。扩大预算仍可能遇到 length 或 timeout；当前正确行为继续停止，不能自动续写、加额度或重试。方案 B 选区上限、层级摘要、重要性过滤均未实现，也不作为本次成功前提。

用户合并本 PR 后，其他修改交 DeepSeek 按 [PR57](https://github.com/xsw932187210-cell/chi-agent/pull/57) A–D 的最新规划处理（须核实该规划已合并及最新 main）；不恢复已撤下的 E。完成后仍须独立复审及重建身份，再准备新 B 与最小真实验证审批；九题未见集、正式 Harbor、Writeup / 报告各自验收边界保持。
