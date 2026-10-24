# bootstrap-baseline/D0 独立复审

日期：2026-10-25（Asia/Shanghai）。审核者：Codex。**候选 c4b410a 未通过 D0：R1、R4、R6、R7、R8 在下述离线范围内关闭；R2、R3、R5 仍需返工。** 本轮未修改实现、原测试或 Gemini 交付报告，未调用参赛模型、官方任务或 judge。

## 审核身份

| 项目 | 实际身份 |
| --- | --- |
| Git 根目录 / 分支 | `/Users/asaki/Documents/ChatGPT/Kaggle` / `main` |
| 初始规划基线 | `c660e2699b8b972c9aa1d114a3e4d63510b8985e` |
| 上次已审候选 | `01a044fe237aff7ddcafc3332e9444d443c41999`，首审未通过 |
| 本次开工基线 | `ff2e23d72fe1ae37b41872fbae655a1498c592e0`，包含首审与学习记录 |
| 本次已审候选 | `c4b410a954bde9dbef64671a1c8079d90b68b79e`，直接父提交为上述开工基线 |
| 审核开始时工作区 | HEAD 等于候选，仅 learning-agreement.md 有此前 Codex 教学的未提交改动；已保留并保存起始 patch |
| 实现方 | 用户报告 Antigravity + Gemini 3.8 Flash (High)；Codex 未操作、调试或监控客户端 |
| 检查范围 | 对比上次已审/新候选及实际开工差异，核对初始规划的累计目标、R1–R8、相关生产函数/调用者/配置/测试及固定上游契约 |

[首审完整报告（固定在 ff2e23d）](https://github.com/xsw932187210-cell/chi-agent/blob/ff2e23d72fe1ae37b41872fbae655a1498c592e0/chi-agent/reviews/bootstrap-baseline-d0-review.md) 保留历史缺陷与证据；[Gemini 本次交付报告](bootstrap-baseline-d0-handover.md) 是执行器自测来源。本文件更新为本次复审结论，不将自测摘要视为独立通过。

## R1–R8 状态

| 要求 | 结论 | 本轮核对 |
| --- | --- | --- |
| R1 ungraded 真实执行 | 关闭（D0） | 实际生产入口在具备合成前提时仍阻断，退出 2、写 blocked_before_execution，无 uv/cb 启动；干运行保留 |
| R2 预算与限额 | 未关闭 / P1 | 未知用量标签和参数转发已有改进，累计金额、下一请求预留与有效停止决策仍缺失 |
| R3 唯一 trial 与二元判分 | 未关闭 / P1 | 正常后缀/截断元数据、歧义、类型和实际路径已有改进；元数据冲突仍可被目录名覆盖，异常大整数还能留下 started 状态 |
| R4 D0 引擎权限 | 关闭（D0） | Compose 无 socket、镜像无 docker-cli，容器内真实 offline readiness 退出 0 |
| R5 就绪与生产门禁 | 未关闭 / P1 | 授权标志不能单独通过、vendor pin 检查已补回；所选任务/provider、手册版本及模式支持仍未对齐 |
| R6 依赖锁与重建 | 关闭（当前开发目标） | 独立 --no-cache 构建成功；uv 0.6.14、11 个锁定依赖均匹配，uv pip check 通过；Python 3.12/其他架构未验证 |
| R7 有限正数 | 关闭（已测 CLI 边界） | NaN/Inf/-Inf 在写配置、manifest 或启动外部执行前被拒绝；原正常/零值回归亦通过 |
| R8 env-file 路径/优先级 | 关闭（已测基本 KEY=VALUE 配置） | 真实相对路径含空格，经 child cwd 仍定位同一文件；文件空值覆盖进程值，门禁按文件优先判断 |

关闭项指本阶段已核对的离线行为；不代表真实模型、官方任务或完整评分通过。上游 schema/命令生成函数确认 agent_kwargs 被转成 argv，只证明传递链，不证明具体模型 harness 已识别并执行这些限额，后者仍留在获授权的 B 阶段。

## 仍需返工

### R2 / P1：evaluate_budget 没有实际核算预算

位置：[run_baseline.py](../scripts/run_baseline.py) 第 89、107–134、321–325、662–665 行。

函数先将总预算与固定 0.001 元比较；之后只要 token_usage 与 cost_usd 都非 None，就返回 within_budget。max_rounds、max_tokens_per_request 没参与计算，也没有累计已用、下一请求输入/最大输出预留、价格版本或美元/人民币的统一口径。执行前得到 unverified_unknown_usage 后，真实执行路径也没有据此停止。

独立探针在预算 5 元时，分别传入 cost_usd=1000.0 和 cost_usd=Infinity，两者均返回 within_budget。这里的成本全部是合成输入，没有实际消费。固定 0.001 元与具体请求无关，不能替代保守的请求成本预留。

**D0 返工验收：** 实现可用合成数据验证的预算决策，至少覆盖总额、累计已用、下一请求保守预留、已用轮数/上限，以及缺用量、缺价格/换算依据或非法数值。先统一金额口径；不要求联网获取真实价格。以下是行为例子，不限定函数参数名称：

- 总额 5、已用 4.0、下一次预留 0.4：预算条件允许；其他条件仍独立检查。
- 总额 5、已用 4.8、下一次预留 0.4：启动下一请求前停止。
- 已用金额、必要价格或换算依据未知，或者轮数已耗尽：停止并记录原因；未知不按零处理。
- 非有限/负成本不可以得到 within_budget；不能只检查字段是否存在。

保持真实限额未验证的状态与阻断边界，不为验证此项运行模型或开启 A/B/C。修正 tasks 2.8 和交付报告中“预算决策全部落实”的声明；用生产所用决策函数测试，而不是另写测试专用算法。

### R3 / P1：目录名可覆盖相反的元数据，非法判分可能破坏终态

位置：[run_baseline.py](../scripts/run_baseline.py) 第 168–192、232、760–795 行。

本次复现：

1. 目录为 task-1__ABC，而 config.json::task.path 明确是 /synthetic/another-task，reward=1。元数据未匹配后代码继续走目录回退，仍给 task-1 返回 1.0。
2. 无元数据的另一个任务目录 task-1_other-task，只因 startswith(task_name + "_") 就被视为 task-1；固定上游说明的是双下划线 trial 后缀。
3. reward 为合法 JSON 大整数 10**400 时，float(raw) 抛 OverflowError。通过真正 main 的外部替身复现后，manifest 仍为 started、finished_at=null，没有转换成可解释的未完成终态。

**返工验收：** 明确元数据优先规则：已明确指向其他任务的记录不得靠目录名重新纳入；元数据损坏或冲突保留 unknown/invalid 原因。只有元数据确实缺失且符合已核对的旧布局，才使用无歧义的目录规则；无法唯一恢复截断身份时拒绝猜测。拒绝单下划线宽泛前缀碰撞。数值验证与结果收集须安全处理巨大整数等非法输入，最终记录未完成/无有效判分及原因，不能留下 started。保留已通过的 0/1、字符串/布尔拒绝、唯一 trial 与实际路径回归。

固定上游身份依据仍为 [runner.py 的 config.json 与 trial 后缀说明](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/runner.py#L563)。上述 fixture 均为合成数据，没有读取或提供隐藏答案。

### R5 / P1：门禁仍未绑定所选任务、模型和资料证据

位置：[check_readiness.py](../scripts/check_readiness.py) 第 189–241、310–337 行；[run_baseline.py](../scripts/run_baseline.py) 第 302–318 行。

本次复现：

- 生产门禁固定检查 prior_auth_provider/tasks 是否非空，没有接收所选 domain/task。fixture 只有一个 provider 输入说明，选择不存在的 cm/missing-cm-task 后仍启动 uv/cb 替身，生成的实际 dataset 路径并不存在。
- 选择 deepseek/synthetic，只设置无关的 OPENAI_API_KEY 和合成 judge key，仍被放行；任意 provider key 存在不能证明所选 provider 配置完整。
- 仅有一个非空 SKILL.md，缺少 references 与版本/清单证据，check_handbook 仍称 verified。原先“授权标志单独通过”虽已修复，但文件存在仍被扩大为完整资料已验证。
- 在模拟 engine/pin 可用的条件下，readiness 报 ungraded ready，实际入口却按 R1 永久阻断该模式，两个入口对同一模式的支持结论不一致。

**返工验收：** 让报告和生产入口共享同一份所选配置及模式支持判断，至少包括领域、唯一任务、provider/凭据类型、资料版本与所需文件。缺失/不支持/未知明确记录并阻断真实执行；offline 继续无需完整资料、模型或 socket。复用已有 data/source-downloads.json 及下载/版本证据，使用合成清单测试缺文件、版本不符等分支，不重新申请或下载已验证的手册。判分侧保留已有 [Claude Code/OAuth 取舍](../docs/judge-access-options-2026-10-21.md)：可报告未验证的认证路径，不再用 key-only 分支代表所有技术可能；不做真实认证或判分。

## 独立运行与证据

所有 Python/uv 执行均在 Docker 内。候选由 git archive 导出，只读挂载；测试容器无网络、无 socket、无真实凭据。仅合成证据目录可写。原始日志日期使用 UTC，本报告使用上海日期。

| 独立检查 | 结果 |
| --- | --- |
| Docker 构建 | docker build --no-cache，退出 0；开发依赖层重新执行，固定基础镜像按摘要复用 |
| 原有 unittest | 51/51 通过，0.296 秒，退出 0 |
| 补充探针 | 18 个测试方法，10 个通过、8 个方法失败；预算含两个子例，共 9 条失败断言，0 errors，退出 1 |
| 依赖与真实 offline CLI | 11 个 lock 版本全部匹配；uv pip check 检查 12 个包（含本项目）通过；offline --json 退出 0 |
| 环境 | Python 3.13.17，/opt/venv/bin/python3，aarch64，uv 0.6.14；无 docker CLI/socket |
| 独立审核镜像 | chi-agent-d0-review:c4b410a；sha256:92d7eca90bbe001c729cd7f9881fa20921e48a57f3ee5ccfafb664af30bbbdec |
| Git 格式 | 实际开工基线至候选的 git diff --check 通过 |

主要执行命令如下（工作目录为 Git 根目录）：

```bash
docker build --no-cache --progress=plain --tag chi-agent-d0-review:c4b410a \
  /private/tmp/chi-d0-review-c4b410a/candidate/chi-agent

docker run --rm --network none \
  --mount type=bind,source=/private/tmp/chi-d0-review-c4b410a/candidate/chi-agent,target=/workspace,readonly \
  --workdir /workspace chi-agent-d0-review:c4b410a \
  python3 -m unittest discover -s tests -v
```

补充探针通过同样的只读源码挂载，另挂载 probes/reference 为只读、logs 为 /evidence 可写，执行 python3 /probes/review_probes.py；环境和锁文件检查执行 python3 /probes/environment_check.py。没有替换生产预算、判分或门禁函数，只替换外部进程和 fixture 路径。固定上游配置/argv 检查只执行 schema 与命令构造函数，未启动 Harbor。

全部原始证据保存在本机忽略目录 `/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.coordination/d0-review-c4b410a/`：logs 中的 build.log、unittest.log、probes.log、observations.json、environment.json/log，以及 probes 和只读 reference。起始学习文档 patch 也已留存，原有教学记录继续保留。首次探针误清 PATH 的原始日志标为 probes-initial-invalid-env.log，不计入上述有效结果；修正探针运行环境后复跑已确认 R4 通过。原始文件不进入 GitHub。

Gemini 自测与本次独立结果分开记录。未运行 OpenSpec CLI（镜像未提供）、官方 Python 3.12/其他架构兼容测试、任务容器/实时 MCP、真实模型往返、正式 trial、官方判分及真实超时清理。没有官方 reward、实测模型用量或费用；合成 fixture 的 reward 和成本不是竞赛证据。

## 接续与教学

用户只需把本报告 R2、R3、R5 转交 Gemini，在当前 main 上继续 D0；不重做已关闭项，除非返工影响它们的相关行为。修正 README/tasks/交付报告中的无证据完成声明，继续使用一份交付报告与稳定本地候选，停止修改后由用户通知 Codex。Codex 不自动派发、不自行改实现、不轮询；A/B/C、参赛模型 API 和官方判分继续暂停。

下次先比较本次已审 c4b410a 与新候选，再核对初始规划累计目标及未决问题。已通过的完整 D0 实现提交仍为无。首审记录已保存在固定提交，REVIEW_STATE 保留两次审核索引。

本轮用真实元数据回退代码讲解身份优先级。用户回答“不归给 task-1，记录身份不匹配”，记为能判断该具体冲突；未据此推断其已实践 trial 解析或预算开发。此前 D0 总体能力与依赖锁的学习记录一并保留。
