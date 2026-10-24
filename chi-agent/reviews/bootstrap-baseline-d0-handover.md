# bootstrap-baseline/D0 交付报告

日期：2026-10-25（Asia/Shanghai）。状态：ready_for_review；表示实现写入已停止，等待主代理独立复验，不代表 D0 通过。

## 身份与范围

- 方式：Codex 主代理协调两个 Luna High 子代理；不再由用户手工转交 Gemini。
- 子代理请求设置均为 `model=gpt-6-luna`、`reasoning_effort=high`；任务身份 `/root/luna_budget_reward` 与 `/root/luna_gate_policy`，无下级代理。
- 实际本轮开工点：`35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9` / main，工作区起始干净。
- 协作文档单独提交：`83f3a8b425276cd7e987aeeb77c6a194bb79ec87`；当前实现候选将由主代理在此后显式提交，完整 SHA 以提交结果及审核记录为准，避免自引用提交。
- 上次已审实现：`c4b410a954bde9dbef64671a1c8079d90b68b79e`，未通过，R2/R3/R5 为本轮实现范围；已关闭项作受影响回归。
- 所有子代理现已停止写入。只恢复 D0；A/B/C、参赛模型 API、真实 trial 与官方判分继续暂停。

## 实现与关键入口

| 问题 | 主要文件/入口 | 本轮行为 |
| --- | --- | --- |
| R2 | scripts/run_baseline.py::evaluate_budget/main | 用累计 CNY 成本、版本化输入/输出价格、最大请求输入/输出与汇率来源计算下一请求保留，比较总额与轮数；未知或非法数据停止；main 使用真实决策作启动门禁 |
| R3 | scripts/run_baseline.py::extract_reward/结果收集 | 元数据有明确身份时禁止目录名覆盖；缺元数据才用精确名称/双下划线后缀；歧义拒绝，0/1 类型严格，超大整数/损坏结果安全落无有效判分终态 |
| R5 | scripts/d0_gate_policy.py::evaluate_gate | 两入口共享所选领域/任务/provider、任务文件来源清单、手册声明版本、完整清单 size/hash、模式支持及凭据配置状态 |
| R5 入口 | scripts/check_readiness.py、scripts/run_baseline.py | readiness 增加 domain/task/model/provider 选择参数；整体 ready 服从预算检查，local_configuration_ready 与整体执行准备区分；offline 不检查引擎或真实模式资料 |
| 配置说明 | project.yaml | provider 与环境变量按明确模型前缀对应；judge API key 仅表示配置，OAuth/Claude Code 维持已知但未验证路径，不宣称认证或连通性已通过 |

预算算法可用合成核算上下文验证；**当前包装入口没有可信的实际核算来源，真实执行仍在 uv/cb 启动前阻断**。没有用零值冒充已测用量，没有声称真实 harness 已识别并执行限额。ungraded 也继续按 R1 报 unsupported；后续接入须在获授权的阶段取得证据。

两份新测试分别为 tests/test_d0_budget_reward.py、tests/test_d0_gate_policy.py。旧测试更新预算接口、门禁语义与离线隔离；测试后续结果/异常分支时仍有显式预算或前提替身，不把这些分支测试当成真实模型执行或完整预算集成证据。

## 子代理实际自测（独立审核前）

两个子代理均复用 `chi-agent-d0-review:c4b410a` 的既有开发依赖环境；本轮 Dockerfile/lock 未改变。项目只读挂载 /workspace，容器 --network none，无 socket、无传入真实模型凭据；合成证据目录单独可写。宿主机未安装或执行项目 Python 依赖。

| 执行者 | 命令与结果 | 本机忽略证据 |
| --- | --- | --- |
| Luna 一 | python3 -m unittest discover -s tests -v，66 项通过，退出 0 | .coordination/luna-d0-r2-r3/d0-r2-r3-combined-tests.log |
| Luna 二（合并后） | 同上，80 项通过，退出 0；git diff --check 退出 0 | .coordination/luna-d0-r5/logs/full-unittest.log |
| Luna 二 | 容器内 offline readiness CLI 退出 0；scored 本地检查按缺少真实依赖/核算输入预期退出 1 | .coordination/luna-d0-r5/logs/ |

Luna 二另对本机已有下载清单作本地完整性检查：pa_t018 所需已记录文件和手册 1,292 项哈希匹配，不代表完整任务世界已具备，也未传入模型 key、登录或调用 API。主代理仍须独立核对当前候选及所声称的行为。

## 限制与交接

未运行 OpenSpec CLI、官方 Python 3.12/其他架构兼容测试、官方任务世界/实时 MCP、模型连续往返、真实超时清理或官方判分。无真实 reward、模型用量或费用；所有测试 reward/成本为合成输入。

主代理只显式暂存本轮代码、测试、配置说明和本报告，先形成稳定候选，再独立复验；后续审核/学习状态另行提交。原始日志、下载资料、vendor、凭据和本地环境不上传，GitHub 备份不代替验收。
