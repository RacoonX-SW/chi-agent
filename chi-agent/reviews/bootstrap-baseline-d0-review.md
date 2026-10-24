# bootstrap-baseline/D0 独立审核

日期：2026-10-24（Asia/Shanghai）。审核者：Codex。**结论：未通过，需 Gemini 返工；本轮没有通过的 D0 实现提交。** 原有 42 项测试通过，但补充检查复现了下列 8 项问题。没有运行官方任务、参赛模型或 judge，也没有产生官方 reward。

## 身份与范围

| 项目 | 核对结果 |
| --- | --- |
| Git 根目录 / 分支 | `/Users/asaki/Documents/ChatGPT/Kaggle` / `main` |
| 规划基线 | `c660e2699b8b972c9aa1d114a3e4d63510b8985e` |
| 已审候选 | `01a044fe237aff7ddcafc3332e9444d443c41999`，直接父提交为上述基线 |
| 执行器 | 用户报告 Antigravity + Gemini 3.8 Flash (High)；未操作或监控其客户端 |
| 开始审核时 | HEAD 等于候选，暂存区/工作区干净；候选包含交付报告，共改动 11 个文件 |
| 阅读范围 | 提交差异、Docker/依赖/配置、两个生产脚本及其调用者/测试、对应 OpenSpec、历史验收和返工要求 |
| 测试代码身份 | `git archive` 导出固定候选到 `/private/tmp/chi-d0-review-01a044fe/candidate/`；测试使用该只读快照 |
| 实现写入边界 | 未修改候选实现、原测试或 Gemini 交付报告；只新增/更新审核、学习及当前状态文档 |

原交付报告见 [Gemini 自测与交付](bootstrap-baseline-d0-handover.md)。历史候选 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 未通过的结论保留，首次 D0 不以旧实现作为可信通过基线。

## 返工要求

### R1 / P1：ungraded 没有切换执行路径，却宣称 verifier 未执行

位置：[run_baseline.py](../scripts/run_baseline.py) 第 106–107、458–477、573–575 行。

`--mode` 没有进入实际 ExperimentConfig 或 argv；两个模式都调用 `cb experiment run -f ...`。`ungraded` 只略过 judge key 检查，并在收集结果时直接返回 null，理由固定写成“official verifier not executed”。独立探针比较两种模式的有效配置，除临时路径外完全相同；替身即便写出 reward=1，ungraded 仍丢弃它并宣称未运行 verifier。

固定上游的 `run_experiment()` 会把配置交给 Harbor；其命令生成器没有从这些配置中取得“跳过 verifier”的指令。此处不能据此保证无判分，更不能在未来获授权运行时把这条路径当成已验证的无评分入口。[固定上游执行器](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/runner.py#L254)。

**要求：** D0 内明确阻断尚未验证的 ungraded 真实执行，记录 unsupported/blocked 原因；保留干运行与离线检查。若以后找到有证据的独立开发入口，再在获授权的 A 阶段验证。不要新增猜测的 skip-judge 参数，不通过实际调用 judge 证明此问题。增加生产入口测试，验证阻断发生在外部进程启动前。

### R2 / P1：预算与生成限额只有记录，没有离线决策或执行保障

位置：[run_baseline.py](../scripts/run_baseline.py) 第 244–284、501–504、532–534 行；[tasks.md](../openspec/changes/bootstrap-baseline/tasks.md) 的 2.8。

`budget_cny`、`max_rounds`、`max_tokens_per_request` 仅出现在参数/预览/manifest，未进入有效 runner 配置，没有累计预算、下一请求预留、用量未知或预算停止的判断。manifest 无条件填写 `budget_status="within_budget"`。探针给出预算 `0.000001`、轮数/token 上限均为 1，替身仍被启动；用量与成本为 null，预算状态却仍是 within_budget。

**要求：** 在 D0 实现并用合成用量/价格验证预算决策：累计已用、下一请求输入/最大输出预留、余量不足和用量未知时停止，并记录原因。明确“计划限额”与“已验证生效限额”；未验证的 runner 限额不能当作已实施保障。D0 不要求调用真实模型或完成 B 的拦截接入，但应阻断没有必要保障的真实执行。修正 2.8 的完成声明，增加正常、耗尽、未知用量等离线回归。

### R3 / P1：判分收集仍猜目录，并接受歧义与非法类型

位置：[run_baseline.py](../scripts/run_baseline.py) 第 109–119、137–144、590 行。

独立 fixture 复现了三个问题：

- 按固定上游说明构造 `trials/job-1/task-1__AbC123/`，其中 `config.json::task.path` 指向目标 task-1，且 verifier/reward.json 为数值 1；候选仍返回“reward.json not found”。固定上游明确说明 trial 名追加随机后缀，并可能截断任务名，身份应优先取 config.json，而非猜目录。[上游目录与身份说明](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/runner.py#L563)。
- 两个 job 都有完整 task-1 子目录，判分分别为 0 和 1，候选取 glob 的第一个结果，本次得到 0，未拒绝歧义。
- `{"reward":"1"}` 被 `float(raw)` 接受为有效 1.0，违反只接受数值二元值的约定。若 fallback 成功，manifest 的 reward_path 还会重新拼成原猜测路径，未必是实际读取文件。

**要求：** 按固定上游元数据解析唯一目标 trial，兼容后缀/截断；拒绝多记录歧义、身份不符以及字符串/布尔/非二元/非有限值。保留有效的 0；返回并记录真正读取的 reward/scorecard 路径。补齐相应生产入口回归，不只测试人为固定的 `trials/<完整任务名>` 结构。

### R4 / P1：D0 默认取得调度引擎权限，离线 readiness 反而依赖它

位置：[compose.yaml](../compose.yaml) 第 10 行；[check_readiness.py](../scripts/check_readiness.py) 第 293–295、343 行。

开发服务默认挂载 `/var/run/docker.sock`，与 [D0 离线边界](../openspec/changes/bootstrap-baseline/handoff.md) 明确规定的“不向容器提供任务调度引擎权限”不符。与此同时，offline 把 Docker daemon 可达作为必要条件。独立无 socket 容器能够通过全部 42 项原测试，但 offline readiness 返回 false。

**要求：** 移除 D0 默认 socket 挂载；容器内离线检查只要求实际需要的解释器、依赖和工具。宿主机用 Docker 启动开发容器与容器内获得调度引擎权限分开处理；后者留给获授权的 A 阶段。增加无 socket、无密钥、无完整数据时的离线就绪回归。不得为让 readiness 变绿重新开放引擎权限。

### R5 / P1：就绪报告与生产门禁不一致，缺资料仍可放行

位置：[check_readiness.py](../scripts/check_readiness.py) 第 188–237、286–327 行；[run_baseline.py](../scripts/run_baseline.py) 第 171–203 行。

- 只有 `HF_HANDBOOK_ACCESS_GRANTED=1`、没有任何手册文件时，手册检查仍为 ok。单个非空 SKILL.md 也被称为 verified，未核对已有版本/清单证据；原测试第 111–119 行还明确断言仅授权标志就应通过。
- readiness 计算了 vendor 检查却没有将其作为真实执行的必要条件；只有规划用 instruction 子目录、缺 vendor 时也会报告 ungraded ready。
- 实际入口的门禁只检查 Docker CLI、手册文件或标志、以及 scored 的 Anthropic key。探针在 vendor、任务数据、手册文件、模型 key 都缺失时，仅设置授权标志，门禁返回空阻塞列表。旧版本的 uv/vendor pin 检查也在本次差异中被移除。

**要求：** 统一模式报告与实际入口的必要条件，区分授权、下载、版本校验和连通性。真实执行必须核对固定上游、所选领域/任务所需文件、已有手册版本证据与所选 provider 的凭据配置；缺失或未验证时明确阻断，不伪造连通性。无需重新申请或下载已验证的手册。判分认证还须保留已有 [Claude Code/OAuth 更正](../docs/judge-access-options-2026-10-21.md)，不要再次将原生 key 写成唯一技术路径；本轮不做真实认证或判分。

### R6 / P2：依赖没有锁定，不能据此宣称可复现

位置：[pyproject.toml](../pyproject.toml) 第 7–15 行；[Dockerfile](../Dockerfile) 第 1、12、24 行。

提交没有 uv.lock 或等价锁文件；直接依赖都是 `>=`，uv 本身和基础镜像标签也未固定。`uv pip install -e ".[dev]"` 会在重新解析时选择当时的版本。将依赖装到 `/opt/venv` 解决的是位置隔离，不等于版本锁定。README 的“锁定依赖”及 tasks 2.9 的完成声明证据不足。

**要求：** 在容器内生成并提交可审查的依赖锁，构建使用冻结安装；固定构建工具/解释器的实际版本或镜像身份，并记录架构。验证干净重建，不依赖临时手装或现有缓存。保留 Python 3.13 开发、官方 3.12 契约分别验证的边界；未验证的目标如实列出。

### R7 / P2：NaN 和 Infinity 绕过有限正数检查

位置：[run_baseline.py](../scripts/run_baseline.py) 第 376–384 行。

float 参数仅检查 `<= 0`。`--budget-cny nan/inf`、`--timeout-multiplier nan/inf` 四个离线子例全部以 0 退出；后两项还进入生成的 YAML。NaN 不满足常规大小比较，正 Infinity 也大于零，因此当前判断并未落实“有限正数”。

**要求：** 在写配置、建立运行目录或启动子进程前同时检查有限性与正数范围；为 NaN、正负 Infinity、零、负数补边界回归。

### R8 / P2：相对 --env-file 在预检查与上游执行时指向不同文件

位置：[run_baseline.py](../scripts/run_baseline.py) 第 159、279、464、533 行。

预检查从启动目录读取相对 env-file，配置原样保留该相对路径，外部进程却在 vendor/chi-bench 中运行。独立探针使用 `--env-file review.env`：wrapper 侧文件存在，child cwd 下不存在，但包装仍以 0 结束。固定上游 `_load_env()` 在文件不存在时直接返回，且存在时使用 `load_dotenv(..., override=True)`；这也与本地门禁目前的进程环境优先策略不同。[上游 env 加载](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/runner.py#L331)。

**要求：** 尽早规范化 env-file 绝对路径，并保证预检查、YAML、执行环境及记录使用同一份配置和一致的优先级。补测相对路径、含空格路径以及文件/进程环境冲突；不输出真实凭据。

## 独立检查与证据

所有 Python 执行和测试均在 Docker 内。运行容器使用 `--network none`，没有 Docker socket 或真实凭据；候选源码只读，只有合成证据目录可写。构建使用单独标签 `chi-agent-d0-review:01a044fe`，未覆盖 Gemini 镜像。

| 检查 | Codex 实际结果 |
| --- | --- |
| 独立快照构建 | 退出 0；命中已有依赖层缓存，不等于无缓存依赖重建 |
| 候选原有 unittest | 42/42 通过，0.210 秒，退出 0 |
| 独立回归探针 | 13 个测试方法：2 个通过、11 个方法失败；含 NaN/Inf 子例，共 14 条失败断言，0 errors，退出 1 |
| 相对 env-file 探针 | wrapper 路径存在、child 路径不存在，退出 1 |
| 固定上游配置/argv | 实际 ExperimentConfig 解析成功；执行上游命令生成函数，核对 include-task-name、n-tasks=1、max-retries=0；未启动 Harbor |
| 环境身份 | Python 3.13.17，`/opt/venv/bin/python3`，aarch64；PyYAML 6.0.3、pydantic 2.14.1、pytest 9.1.1 |
| 审核镜像 ID | `sha256:3fc8876a8b3a57bdab39d68919358e4473c0dd6fdc91c285918e37d545efde7b` |
| 候选 diff 格式 | `git diff --check <base> <candidate>` 退出 2；交付报告第 66、67 行有行尾空格，属于文档小问题，未改候选 |

Gemini 报告中的 pytest 42 项、带 socket 的 readiness 等是执行器自测证据；Codex 没有重复运行同一套 pytest，也没有按候选 Compose 开放 socket。上表为本次独立结果。

实际执行的主要命令（工作目录为 Git 根目录，源码取自固定候选快照）：

```bash
docker build --progress=plain --tag chi-agent-d0-review:01a044fe \
  /private/tmp/chi-d0-review-01a044fe/candidate/chi-agent

docker run --rm --network none \
  --mount type=bind,source=/private/tmp/chi-d0-review-01a044fe/candidate/chi-agent,target=/workspace,readonly \
  --workdir /workspace chi-agent-d0-review:01a044fe \
  python3 -m unittest discover -s tests -v

docker run --rm --network none \
  --mount type=bind,source=/private/tmp/chi-d0-review-01a044fe/candidate/chi-agent,target=/workspace,readonly \
  --mount type=bind,source=/private/tmp/chi-d0-review-01a044fe/probes,target=/probes,readonly \
  --mount type=bind,source=/private/tmp/chi-d0-review-01a044fe/reference,target=/reference,readonly \
  --mount type=bind,source=/private/tmp/chi-d0-review-01a044fe/logs,target=/evidence \
  --workdir /workspace chi-agent-d0-review:01a044fe \
  python3 /probes/audit_probes.py
```

相对路径探针使用相同源码/probes/evidence 挂载，入口为 `python3 /probes/env_file_probe.py`。完整输出及探针已保留在本机忽略目录 `/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.coordination/d0-review-01a044fe/`，不进入 GitHub：

- `logs/build.log`、`logs/unittest.log`、`logs/probes.log`、`logs/env-file.log`。
- `logs/observations.json`、`logs/env-file.json`、`logs/environment.json`。
- `probes/audit_probes.py`、`probes/env_file_probe.py` 和固定上游只读 reference。

上游 config 文本经 GitHub connector 重新核对，与缓存一致；argv 探针只执行命令构造函数，并替换可执行文件定位及凭据边界，不启动上游执行器。所有 reward fixture 都是合成数据，不能作为官方评分或竞赛通过率。

未运行：OpenSpec CLI（镜像未提供）、无缓存依赖重建、官方 Python 3.12/其他目标架构兼容检查、完整资料/实时 MCP、真实模型工具往返、正式 trial 和官方判分。超时后的子进程/任务容器清理也未作真实验证，不能把外层 timeout 当作精确费用或清理保障。

## 已核对的改进与接续

- 原 submission 字段层级和 slug 路径已替换为实际支持的 ExperimentConfig，单题/单次尝试/并发 1 与禁重试参数的传递已做离线契约检查。
- 原测试现在调用生产 main，而非在测试中自行编造终态；干运行确实不启动子进程，也不留下 started manifest。
- 数值 0/1、布尔、0.5、缺文件及进程异常已有部分覆盖，但上述未覆盖场景仍阻止 D0 通过。

用户将本报告 R1–R8 交给 Gemini 返工；Codex 不直接改实现或自动派发。返工继续仅限 D0，报告/README/tasks 应反映实际完成范围，尤其不能保留预算已生效、依赖已锁定等无证据声明。仍使用一份阶段交付报告，稳定提交后停止写入，由用户提供新候选 SHA。

下一轮先比较本次已审候选与新候选，再核对规划基线至新候选的累计目标和 R1–R8；记录关闭/未关闭证据，不把新增提交或备份当作通过。A/B/C、参赛模型 API、官方判分继续暂停。

教学记录：已用实际 `main → build_experiment_config → YAML → uv/cb` 与独立 manifest 写入说明记录和执行约束的区别。用户回答“不能，仅有记录还不能约束执行”，支持其能判断这一具体区别；没有预算接入或调试实践证据，不扩大为已掌握 runner/预算系统。详见学习约定。
