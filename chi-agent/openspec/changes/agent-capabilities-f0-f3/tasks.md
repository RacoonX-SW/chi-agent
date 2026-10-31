# F0–F3 执行清单

当前：F0–F3 契约与实现候选已完成离线自测，等待外部 Gemini 审查与用户合并决定。证据见 [阶段报告](../../../reviews/f0-f3-agent-capabilities-review.md)；状态只查 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md)。

## 0. 现场与基线

- [x] 刷新 `origin`，核对 PR31 已合并、main 位于 `443257c`，从最新 main 继续实现分支。
- [x] 记录 Gemini 3.8 Flash 子代理启动失败（账户资金不足），停止 OpenCode 内 Gemini 派发，改用外部订阅 Gemini 审阅。
- [x] Docker 基线：382 tests，2 个环境性 import 错误（缺 `anthropic`），8 skipped。
- [x] 外部 Gemini 审阅契约与实现候选；首轮发现 3 阻断+3 建议，返工后复审通过（限离线静态/契约/Docker 合成）。

## 1. F0 任务家族矩阵

- [x] 从公开索引/工具目录建立首版 provider/payer/CM 家族矩阵。
- [x] 每个家族写正常/缺证/失败分支、必要能力、工具、完成证据与当前状态。
- [ ] 用公开 `instruction.md`/`tool_reference.md` 抽样核对 3 个角色各 1 个家族，修正矩阵措辞。
- [x] 明确列出 `unsupported`/`official_dependency`（marathon、e2e、官方 CM 模拟器）。

## 2. F1 业务状态

- [x] 新增 `go_chi_state.py`：schema、目标/来源/版本校验、原子持久化、版本快照、大小上限。
- [x] 新增 `local-task-state` / `local-state-update` 工具；可纠正错误返回 REFUSED，持久化失败终止。
- [x] 程序登记 MCP/本地工具 observation；读/写/neutral 分类按冻结表。
- [x] 未知写效果登记与 resolve（同目标、更晚只读观察）。
- [x] 接入 `run_chi`/`MCPBridge`/`local_tools`；`capabilities=None` 保持旧行为。
- [x] 单测：错 case、未观察/未来来源、旧覆盖新、推断充事实、unknown 改写、超限、持久化失败、旧版本保留。

## 3. F2 角色阶段指导

- [x] 新增 `go_chi_guidance.py`：`chi-role-guidance-v1`，三角色阶段/不变量/停止条件。
- [x] 新增 `local-role-guidance` 工具，返回版本、阶段与当前 state 的 next candidates。
- [x] 单测：payer 无强制 MD、provider 可停止、CM STOP、无 task ID/答案泄露。
- [x] 记录指导版本/hash 到 run 日志；不改官方系统提示。

## 4. F3 规则/证据定位

- [x] 新增 `go_chi_search.py` + `local-fs-search`：handbook/角色 workspace/固定文件范围。
- [x] 限制：文件数、单文件/累计字节、结果数、片段长度、截断标记。
- [x] 拒绝隐藏/跨 case/符号链接/URL；不建持久索引。
- [x] 单测：命中、无匹配、越界、隐藏、符号链接、同名文件、超大/损坏、截断。
- [x] 搜索结果登记 observation；原文回读走 `local-fs-read`。

## 5. claim 门禁（F5 最小部分）

- [x] open unknown → 拒绝并返回 id。
- [x] mutation 晚于最新业务回读 → 拒绝并返回 call_id。
- [x] 同批中 claim 之后仍有待执行工具 → 拒绝，避免先 claim 后写。
- [x] 无 mutation 时保持原 claim；claim 记录 state version/target/来源。
- [x] 单测：未知阻断、写后未回读阻断、同批待处理阻断、回读后可 claim、旧行为不变。

## 6. 集成与回归

- [x] `go_chi_entry.py` 显式传 `capabilities="f0-f3-v1"`；`run_chi(..., capabilities=None)` 保留基线。
- [x] 全量离线套件：414 tests，2 个环境性错误，8 skipped；新增 32 个测试。
- [x] 合成 SDK/MCP 端到端：状态读取/更新、搜索、claim 拒绝/通过、unknown 登记各一次。
- [x] 记录候选 SHA、命令、退出码、证据路径与未验证项。
- [x] 更新 README 运行方法和 REVIEW_STATE 短状态。

## 7. 明确不做（本包）

- [x] 不实现 F4 自动压缩、F5 完整证据分级、F6 停滞重规划（仅保留接口/门禁）。
- [x] 不新增真实模型/判分调用、不提高额度、不改官方世界/提示/评分器。
- [x] 不上传手册、数据、vendor、凭据、真实轨迹或派生索引。

## 8. 外部 Gemini 返工（2026-11-01）

- [x] claim 后跨轮写：拒绝执行、标记 claim_violation、run 以 `chi_claim_violation` incomplete；journal claim 不回写。
- [x] workspace 检索必须匹配 target case；无 target 或跨 case 拒绝。
- [x] 单文件/PDF 不可读返回 `ERROR: search_unreadable`；目录内失败计入 unreadable/skipped。
- [x] target 未设定时 case scope 事实/状态返回 `chi_state_target_required`。
- [x] 写失败 observation 解析 `case:<ID>` scope。
- [x] run_log 增加 `task_state_sha256` 与 `task_state_claim_violation`。
- [x] 定向 38 tests + 全量 424 tests（2 个既有环境错误、8 skipped）通过。
- [x] 外部 Gemini 复审返工候选 `5c1fa51`：通过（限离线静态/契约/Docker 合成；无真实模型/判分/未见题）。
