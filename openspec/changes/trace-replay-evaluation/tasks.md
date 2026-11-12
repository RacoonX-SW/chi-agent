# Trace/Replay 离线评测实施清单

## 1. 用例集与执行入口

- [x] 1.1 实现版本化合成用例集的读取、校验与 SHA-256 绑定。测试覆盖重复 ID、未知版本、缺少事件字段，以及摘要与解析使用同一输入快照。
- [x] 1.2 通过 `run_chi` 的 `lower` 和 `server_factory` 运行合成事件。测试实际 SDK 和 MCP 桥接路径、各用例隔离目录、预期外工具或参数、提前结束，以及对齐失败后首个分歧的保留。

## 2. 执行规则用例

- [x] 2.1 登记截断工具批次和未知写入两个场景。对照账本及模拟 MCP 的实际接收记录，断言截断批次零派发、结算证据保留，以及未知写入后的第二次写入未派发。
- [x] 2.2 登记 Payer 写后回查的正反例。验证缺少回查时的拒绝码，并验证同一案件在写入后成功回查才能接受完成声明。通过实际运行的工具事件和任务状态断言结果。

## 3. 报告、对照与使用入口

- [x] 3.1 实现 `run` 的用例结果、稳定事件摘要和首个分歧，保留计划分母及用例集、源码、评测器和运行环境身份。测试通过、失败、未执行和已有输出目录拒绝，核对原目录的字节。
- [x] 3.2 实现只读 `compare`。验证相同报告、受控事件差异、失败断言差异及用例集或评测条件不一致，核对输出能定位最早分歧。
- [x] 3.3 在 README 增加简短的离线回放入口和合成证据口径。在禁网 Docker 内执行文档给出的 `run` 与 `compare` 命令，核对退出码和产物。

## 4. 候选验收

- [x] 4.1 Terra 在 Docker/Python 3.12 中执行回放套件及相关 SDK 恢复、工具和完成门禁回归。记录镜像、命令、退出码、通过与跳过项、用例分母、报告哈希和真实外部调用数。
- [ ] 4.2 主代理审阅代码和实际执行接缝，从固定源码快照独立运行两次，用 `compare` 验证稳定结果并检查受控分歧。核对正式入口、运行包成员和历史账本的兼容边界，按实际改动补跑仓库既有验证。

## Workflow follow-up

- 完成独立复验后同步规格并按仓库流程归档，提交以 `main` 为目标的 PR 供用户验收。
- 用验收报告中的实际用例和观测值改写简历的评估与可观测性要点。记录合成回放的分母与覆盖范围。

## Terra 自测记录（2026-11-12）

- 镜像 `chi-agent-dev:latest`，容器 Python 3.12.15；`--pull=never --network none --read-only --tmpfs /tmp`，只读挂载源码、CHI-Bench `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 与 `chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`，`PYTHONDONTWRITEBYTECODE=1`；`PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/src:/workspace:/workspace/tests`。
- 容器内 `python -m pytest -q -p no:cacheprovider tests/test_trace_replay.py tests/test_go_chi_recovery_sdk.py tests/test_go_chi_capabilities_runtime.py tests/test_go_chi_tools.py tests/test_completion_gate.py`：退出 0，77 passed，0 skipped。
- 按 README 命令运行两次 `run` 与一次 `compare`，输出分别为 `/out/trace-replay-final-e` 和 `/out/trace-replay-final-f`：三条命令均退出 0；合成用例 4/4，compare `differences: []`。两份 `report.json` SHA-256 均为 `135881986189d659ce96050016d5410e0dcbcd9d38f0db463218978bdcf4d3b6`。
- 用例集 SHA-256 `1f770c4b4c8f222dc1fdb644ca0a15377e9cad55a7db2fae27d943fda6d78ef1`；源码身份 `95c26d5c0d1f89700868ab6f557cdab9b999044e2db9833e30ec08716d52be7c`；评测器身份 `2db7e1dc32144e8c7b4738ed1d36c9673e403f9bc4e29c4b6f2e814ac58badfd`。
- 截断响应及恢复均 settled，只有 `fresh` 派发；未知写入记录 open，第二写入 refused；缺少回查拒绝码 `completion_readback_required:c4`；回查正例 `c5` 之后接受声明。回归测试覆盖受控事件、断言分歧与不兼容条件。真实外部调用 0（禁网且两个 I/O 接缝均为模拟）。
- 以上为实现者自测，不替代 4.2 独立验收；规格同步、归档及 PR 待主代理。

### 独立复审问题修复后自测

- 同一镜像、挂载、禁网设置和上述 pytest 命令，退出 0：85 passed，0 skipped；新增 JSON 布尔/数字区分、非有限值拒绝、原始参数、失败/未执行计数和账本关闭测试。
- 两次 `run` 与 `compare` 均退出 0：4 planned、4 passed、0 failed、0 not_executed；对照无差异，真实外部调用 0。两份报告 `/out/trace-replay-review-{a,b}/report.json` 的 SHA-256 均为 `d678745ae6f98ef19e3717385c11f87e9d584a8af894c4ac92fba5377da8de1d`。
- 用例集 SHA-256 `1f770c4b4c8f222dc1fdb644ca0a15377e9cad55a7db2fae27d943fda6d78ef1`；源码身份 `95c26d5c0d1f89700868ab6f557cdab9b999044e2db9833e30ec08716d52be7c`；评测器身份 `ec9e5e0e6df76c50815d38cc196704ffce0f28a2579e931434f2124e4578d14f`。此前报告属于修复前的历史自测，不代表当前评测器身份。
