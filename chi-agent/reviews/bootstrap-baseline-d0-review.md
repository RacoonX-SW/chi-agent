# bootstrap-baseline/D0 独立验收：双 Luna 候选

日期：2026-10-25（Asia/Shanghai）。审核者：Codex 主代理。

**候选 `b7f894130df93ded69496576b83e6dcdcab7e56b` 通过当前 Python 3.13/aarch64 开发目标下的 D0 离线代码验收。** 本轮关闭 R2/R3/R5，R1/R4/R6/R7/R8 的相关行为保持通过。无未关闭的本轮代码问题；OpenSpec CLI、官方 Python 3.12/其他架构和真实接入仍未验证，不扩大结论。用户完整验收尚未记录，A/B/C、参赛模型 API、真实任务和官方判分继续暂停。

## 身份与协作

| 项目 | 已核对身份 |
| --- | --- |
| Git 根目录 / 分支 | `/Users/asaki/Documents/ChatGPT/Kaggle` / main |
| 本轮开工点 | `35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9`，开始切换时工作区干净 |
| 协作方式文档提交 | `83f3a8b425276cd7e987aeeb77c6a194bb79ec87`，仅 14 份协作/教学/接续文档 |
| 上次已审实现 | `c4b410a954bde9dbef64671a1c8079d90b68b79e`，未通过，R2/R3/R5 未关闭 |
| 本次候选 / 直接父提交 | `b7f894130df93ded69496576b83e6dcdcab7e56b` / `83f3a8b425276cd7e987aeeb77c6a194bb79ec87` |
| 初始规划基线 | `c660e2699b8b972c9aa1d114a3e4d63510b8985e`，累计 D0 目标继续核对 |
| 实现方 | 两个子代理，派发均显式请求 gpt-6-luna / high；任务 `/root/luna_budget_reward` 与 `/root/luna_gate_policy`，未创建下级代理 |
| 主代理动作 | 分规格/写入权、维护文档/Git、读取相关差异/调用代码、固定候选、独立 Docker 检查；未代写实现算法 |

Luna 一先修预算/判分，Luna 二先只读分析、收到交接后修门禁；共享实现文件没有并发写入。两个实现者均停止写入后才提交候选和开展独立检查。原始 Gemini 交付及未通过报告保留于 [首审 ff2e23d](https://github.com/xsw932187210-cell/chi-agent/blob/ff2e23d72fe1ae37b41872fbae655a1498c592e0/chi-agent/reviews/bootstrap-baseline-d0-review.md) 和 [复审 35370ab](https://github.com/xsw932187210-cell/chi-agent/blob/35370ab5d9d20f03b1cb8e4fab60e2e220a24dd9/chi-agent/reviews/bootstrap-baseline-d0-review.md)。更换实现者没有清空旧缺陷。

## 关闭依据

| 要求 | 结论与证据 |
| --- | --- |
| R1 未验证 ungraded | D0 关闭保持：真实入口仍在 uv/cb 前明确 unsupported，写 blocked_before_execution/null reward；干运行保留 |
| R2 预算决策 | 本轮关闭：累计 CNY 与保守下一请求预留实际比较，轮数耗尽/缺输入/非法数值停止，生产入口依据决策阻断 |
| R3 trial 身份/二元判分 | 本轮关闭：相反/损坏/冲突元数据不得由目录名覆盖，缺元数据才接受精确目录或非空双下划线后缀；唯一性、0/1、巨大整数与终态得到验证 |
| R4 D0 socket | 关闭保持：Dockerfile/Compose 未改回 socket 或 Docker CLI，真实 offline CLI 无 socket/模型凭据仍退出 0，offline 不检查引擎/完整资料 |
| R5 所选配置/资料/模式 | 本轮关闭：两入口共用 d0_gate_policy；核对领域/唯一任务/provider 对应 key、所需任务文件、手册版本与完整清单哈希、模式支持；整体 ready 服从预算缺证阻断 |
| R6 可复现依赖 | 当前开发目标关闭保持：Dockerfile/lock/pyproject 与已核对 c4b410a 无差异；本轮正常缓存构建成功，11 个锁版本匹配、uv pip check 通过。前轮无缓存构建证据保留，不重复宣称本轮冷构建 |
| R7 有限正数 | 关闭保持：budget/timeout-multiplier/outer-timeout 的 NaN/Inf/-Inf 在写配置/manifest 和外部执行前被拒绝，正常回归通过 |
| R8 env-file | 关闭保持（基本 KEY=VALUE 范围）：相对路径含空格生成同一物理文件的绝对路径，文件空值覆盖进程 key；原有路径/argv 回归保持 |

### R2：预算记录已经成为停止判断

真实入口 [run_baseline.py](../scripts/run_baseline.py) 第 106 行的 evaluate_budget，接收累计 CNY、已用轮数、最大输入/输出 token、版本化 USD 单价和带来源的换算率，用 Decimal 计算下一请求预留。独立输入总额 5、预留 0.4，已用 4.0/4.6 允许，4.8 停止，1000 明确超额；缺少/非有限/负数/布尔输入不会被当成零。

第 637–650 行的 main 读取该真实决策，非 within_budget 加入阻断原因。独立检查在其他所选配置/资料前提全部满足的合成场景中，没有替换预算算法或前提策略；因缺运行核算来源退出 2，唯一阻断原因是预算，manifest 有 finished_at，无 uv/cb 启动。

**当前生产入口没有可信核算来源，所以真实执行仍被阻断。** D0 验证的是离线算法和缺证停止；未宣称逐请求用量计量、harness 限额或账户扣费硬限制已经接通，后者留到获授权的 B。

### R3：身份与异常结果

第 185 行的 extract_reward 不再以目录名覆盖 config.json 的相反/损坏身份；多条匹配拒绝。独立检查包括截断目录但完整元数据、真实 reward 路径、有效 0、字符串/布尔/非二元/非有限值、401 位与 5000 位整数，以及单下划线前缀碰撞。

第 820 行后的结果收集安全完成 manifest。独立终态检查使用明确命名的合成核算数据适配器：让**原 evaluate_budget 算法**接收测试核算数据以进入结果收集，外部 uv/cb 以合成进程替身返回巨大整数；最终 incomplete_no_verdict/null reward/finished_at 均正确，后置用量仍 unknown。这一检查不代表真实预算来源或模型调用已建立。

### R5：共用门禁与准备层次

[d0_gate_policy.py](../scripts/d0_gate_policy.py) 第 146 行的 evaluate_gate 同时被真实入口和 readiness 使用。错误领域/缺任务文件、无关 provider key、未知前缀/显式 provider 冲突、手册版本不符、缺所需 reference、内容篡改、清单数量不符/重复来源/非完整快照和异常 JSON 均阻断。使用合成清单验证，不重新下载手册。

[check_readiness.py](../scripts/check_readiness.py) 第 281 行的 evaluate_modes 区分 local_configuration_ready 与整体 ready；即便替身 engine/vendor 及合成所选资料/配置完整，未知预算也不能将 scored 整体标为 ready。ungraded 维持 unsupported。API key 存在只表示配置，connectivity_verified/authentication_verified 保持 false；Claude Code/OAuth 明确为已知但未验证路径，不实际认证，也不把它说成技术上不存在。

## 独立运行证据

候选通过 git archive 导出到 `/private/tmp/chi-d0-luna-b7f8941/candidate/`，测试只读挂载该快照。所有项目 Python/uv 均在 Docker 内运行，容器 --network none、无 socket、无真实凭据，只有合成证据目录可写。宿主机未新增项目依赖。

| 检查 | 实际结果 |
| --- | --- |
| 正常缓存构建 | docker build --tag chi-agent-d0-review:b7f8941，退出 0；未重跑不变的无缓存依赖安装 |
| 全部项目 unittest | 80/80 通过，0.594 秒，退出 0；独立于子代理自测日志 |
| 主代理补充契约检查 | 21/21 方法通过，0.100 秒，0 failures/0 errors，退出 0；包含多组子例 |
| 解释器/依赖/真实 offline CLI | Python 3.13.17，aarch64，uv 0.6.14；11 个锁版本匹配；uv pip check 检查 12 包通过；offline --json 退出 0 |
| 审核镜像身份 | chi-agent-d0-review:b7f8941；sha256:d40310582a6b0b71f686c93ef9deba153aea6b77384aae689a2f2e84eb7883a9 |
| Git 差异格式 | c4b410a 至 b7f8941 的 git diff --check 退出 0；Dockerfile/Compose/lock/pyproject 无变化 |
| 协作文档引用 | Docker 内只读核对本轮 15 份文档，本地链接目标无缺失；不等于 OpenSpec CLI 校验 |

主要命令（Git 根目录）：

```bash
docker build --progress=plain --tag chi-agent-d0-review:b7f8941 \
  /private/tmp/chi-d0-luna-b7f8941/candidate/chi-agent

docker run --rm --network none --env PYTHONDONTWRITEBYTECODE=1 \
  --mount type=bind,source=/private/tmp/chi-d0-luna-b7f8941/candidate/chi-agent,target=/workspace,readonly \
  --workdir /workspace chi-agent-d0-review:b7f8941 \
  python3 -m unittest discover -s tests -v
```

补充检查在同样的只读源码挂载上，增加 probes 只读挂载和 logs 到 /evidence 的可写挂载，执行 `python3 /probes/review_checks.py`；环境元数据执行 `python3 /probes/environment_check.py`。生产预算/判分/门禁算法均按真实代码运行；结果收集那一项的核算数据适配明确如上，不把分支隔离测试冒充真实集成。

本机原始证据在忽略目录 `/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.coordination/luna-d0-final-review/`，包括 build.log、unittest.log、review-checks.log、review-summary.json、environment.json/log 与 probes；不上传 GitHub。两个子代理自测证据另外保留于 luna-d0-r2-r3 与 luna-d0-r5，见 [交付报告](bootstrap-baseline-d0-handover.md)。

## 限制、教学与下一步

尚未运行 OpenSpec CLI、官方 Python 3.12/其他架构兼容测试、官方任务/实时 MCP、模型连续往返、真实超时清理或官方判分。无真实 reward、模型用量或费用。D0 通过只说明上述离线工程行为；当前真实执行仍阻断，A/B/C 不自动启动。用户完整验收尚无单独记录。

本轮教学为主代理/子代理的职责和共享文件写入顺序。用户回答“避免覆盖彼此改动，交接后再继续修改”，可判断该具体风险；未扩大为已掌握任务调度、worktree 或完整实现。双 Luna 的实际一轮闭环已有候选和检查证据，但不由此推断更省总 token 或未来不会返工。

审核/学习文档单独存储并备份；已审与 D0 离线通过的实现身份均推进为 b7f8941。当前阶段无代码返工待办，后续阶段等用户明确恢复；普通问答不默认启动子代理，结束后无后台轮询或自动唤醒。
