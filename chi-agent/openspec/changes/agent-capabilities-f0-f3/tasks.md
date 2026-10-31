# F0–F3 执行清单

当前：契约已冻结，**实现尚未开始**。每项实现后先在 Docker 自测，固定候选，再由外部 Gemini 独立审查；审查意见由 DeepSeek 按证据返工。

## 0. 现场与基线

- [x] 刷新 `origin`，核对 PR31 未合并、main 位于 PR30 合并点，从最新 main 建 `codex/f0-f3-agent-capabilities`。
- [x] 记录 Gemini 3.8 Flash 子代理启动失败（账户资金不足），停止 OpenCode 内 Gemini 派发，改用外部订阅 Gemini 审阅。
- [x] Docker 基线：382 tests，2 个环境性 import 错误（缺 `anthropic`），8 skipped；错误与本次代码无关。
- [ ] 外部 Gemini 审阅本契约，记录其实际能读的 repo/diff 与能否运行 Docker。

## 1. F0 任务家族矩阵

- [x] 从公开索引/工具目录建立首版 provider/payer/CM 家族矩阵。
- [x] 每个家族写正常/缺证/失败分支、必要能力、工具、完成证据与当前状态。
- [ ] 用公开 `instruction.md`/`tool_reference.md` 抽样核对 3 个角色各 1 个家族，修正矩阵措辞。
- [ ] 明确列出 `unsupported`/`official_dependency`（marathon、e2e、官方 CM 模拟器）。

## 2. F1 业务状态

- [ ] 新增 `go_chi_state.py`：schema、目标/来源/版本校验、原子持久化、版本快照、大小上限。
- [ ] 新增 `local-task-state` / `local-state-update` 工具；可纠正错误返回 REFUSED，持久化失败终止。
- [ ] 程序登记 MCP/本地工具 observation；读/写/neutral 分类按冻结表。
- [ ] 未知写效果登记与 resolve（同目标、更晚只读观察）。
- [ ] 接入 `run_chi`/`MCPBridge`/`local_tools`；`capabilities=None` 保持旧行为。
- [ ] 单测：错 case、未观察/未来来源、旧覆盖新、推断充事实、unknown 改写、超限、持久化失败、旧版本保留。

## 3. F2 角色阶段指导

- [ ] 新增 `go_chi_guidance.py`：`chi-role-guidance-v1`，三角色阶段/不变量/停止条件。
- [ ] 新增 `local-role-guidance` 工具，返回版本、阶段与当前 state 的 next candidates。
- [ ] 单测：payer 无强制 MD、provider 可停止、CM STOP、无 task ID/答案泄露。
- [ ] 记录指导版本/hash 到 run 日志；不改官方系统提示。

## 4. F3 规则/证据定位

- [ ] 新增 `go_chi_search.py` + `local-fs-search`：handbook/角色 workspace/固定文件范围。
- [ ] 限制：文件数、单文件/累计字节、结果数、片段长度、截断标记。
- [ ] 拒绝隐藏/跨 case/符号链接/URL；不建持久索引。
- [ ] 单测：命中、无匹配、越界、隐藏、符号链接、同名文件、超大/损坏、截断。
- [ ] 搜索结果登记 observation；原文回读走 `local-fs-read`。

## 5. claim 门禁（F5 最小部分）

- [ ] open unknown → 拒绝并返回 id。
- [ ] mutation 晚于最新业务回读 → 拒绝并返回 call_id。
- [ ] 无 mutation 时保持原 claim；claim 记录 state version/target/来源。
- [ ] 单测：未知阻断、写后未回读阻断、回读后可 claim、旧行为不变。

## 6. 集成与回归

- [ ] `role_runner.py` / `go_chi_entry.py` 显式传 capabilities 与 state 目录。
- [ ] 全量离线套件：新测试 + 既有 382 tests（记录 2 个环境性错误）。
- [ ] 合成 SDK/MCP 端到端：状态读取/更新、搜索、claim 拒绝/通过各一次。
- [ ] 记录候选 SHA、命令、退出码、证据路径与未验证项。
- [ ] 更新 README 运行方法和 REVIEW_STATE 短状态（待外部审查后）。

## 7. 明确不做

- [ ] 不实现 F4 自动压缩、F5 完整证据分级、F6 停滞重规划（仅保留接口）。
- [ ] 不新增真实模型/判分调用、不提高额度、不改官方世界/提示/评分器。
- [ ] 不上传手册、数据、vendor、凭据、真实轨迹或派生索引。
