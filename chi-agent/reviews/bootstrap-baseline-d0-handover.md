# bootstrap-baseline/D0 交付报告

- **日期**：2026-10-24
- **阶段**：`bootstrap-baseline/D0`（离线环境构建与包装代码修复）
- **执行器**：Antigravity + Gemini 3.8 Flash (High)
- **基线提交（HEAD）**：`c660e2699b8b972c9aa1d114a3e4d63510b8985e`
- **分支**：`main`
- **状态**：`ready_for_review`

---

## 1. 主要变更及关键入口映射

针对历史验收报告（`reviews/bootstrap-baseline-2026-10-20.md`）和 OpenSpec（`specs/benchmark-readiness/spec.md`）提出的技术缺陷进行了针对性修复与实现：

| 变更项 | 涉及文件 | 关键符号 / 入口 | 解决的旧缺陷与设计取舍 |
| --- | --- | --- | --- |
| **容器开发环境** | `Dockerfile`, `compose.yaml`, `.dockerignore`, `pyproject.toml` | `services.dev` | 建立最小 Docker 开发镜像（Python 3.13-slim，预装 uv/git/docker-cli），依赖完全安装在容器内部 `/opt/venv`，源码通过卷挂载到 `/workspace`，持久化保留且不污染宿主机环境。`.dockerignore` 严格排除凭据、数据、runs 与 git 历史。 |
| **单题配置与命令修复** | `scripts/run_baseline.py` | `build_experiment_config()`, `main()` | 废除错误的 `cb submission run` 传参（旧版将 `include_task_name` 塞入 SubmissionRun 违反上游 schema）；改用上游官方支持的 `cb experiment run -f <ExperimentConfig.yaml>`，在配置中严格绑定 `dataset`、`include_task_name=[task_name]`、`n_tasks=1`、`n_attempts=1`、`concurrency=1`，并在代码中显式拒绝多题/多尝试误配置。 |
| **分模式就绪检查** | `scripts/check_readiness.py`, `project.yaml` | `evaluate_modes()`, `check_handbook()` | 彻底拆分就绪模式：`offline`（仅需容器/Python/Git，不依赖任何 API 密钥）、`tools`（需 Docker 守护进程）、`ungraded`（需模型 key 与手册/任务数据，不依赖 judge）、`scored`（需 Claude judge key）。`check_handbook` 优先通过本地 `SKILL.md` 文件存在核对真实下载证据，避免仅凭环境变量假冒。 |
| **严谨二元判分与无评分区分** | `scripts/run_baseline.py` | `extract_reward()` | 区分 `ungraded`（无判分文件，报告 `official_reward=null`，状态 `completed`）与 `scored`。严谨校验二元判分：仅接受浮点/整数 `1.0` 与 `0.0`，严格拒绝布尔类型、非法浮点（如 0.5）、负数及非数值；缺失判分文件标记为 `incomplete_no_verdict`；进程非零退出标记为 `process_failed`。 |
| **调用边界与预算记录** | `scripts/run_baseline.py` | `parse_args()`, `manifest` | 支持并校验 `--budget-cny`（默认 5.0）、`--max-rounds`（默认 30）、`--max-tokens-per-request`（默认 8192）、`--outer-timeout`、`--timeout-multiplier` 等有限正数限制。干运行校验参数并打印命令与 YAML 预览后退出 0，不启动子进程、不残留 started manifest。未知用量保留为 null 并注明未测量。 |
| **针对性离线测试套件** | `tests/test_readiness_and_baseline.py` | 全部 42 项单元测试 | 所有测试均驱动真实的生产模块函数或 CLI，仅 mock 外部边界（网络、进程、文件探针、时钟），覆盖全部分模式、单题约束、二元判分边界、干运行、异常/超时/失败以及敏感凭据防泄漏。 |

---

## 2. 容器内自测命令与实际执行结果

项目测试与检查全部在 Docker 容器内完成，宿主机未安装项目 Python 依赖包。

### 2.1 镜像构建
- **命令**：`docker compose build dev`
- **退出码**：`0`
- **镜像身份**：`chi-agent-dev:latest` (基于 Debian trixie arm64 `python:3.13-slim`)

### 2.2 离线测试套件（unittest）
- **命令**：`docker compose run --rm dev python3 -m unittest discover -s tests -v`
- **退出码**：`0`
- **结果摘要**：
  ```text
  Ran 42 tests in 0.193s
  OK
  ```

### 2.3 离线测试套件（pytest）
- **命令**：`docker compose run --rm dev pytest -v`
- **退出码**：`0`
- **结果摘要**：
  ```text
  ============================== 42 passed in 0.26s ==============================
  ```

### 2.4 分模式就绪检查（离线模式）
- **命令**：`docker compose run --rm dev python3 scripts/check_readiness.py --mode offline`
- **退出码**：`0`
- **输出摘要**：
  ```text
  [OK ] python_version          : 3.13.17 — OK
  [OK ] uv                      : uv at /usr/local/bin/uv
  [OK ] git                     : git at /usr/bin/git
  [OK ] docker                  : Docker daemon reachable
  [OK ] task_dataset            : Public provider tasks found at /workspace/data/prior_auth_provider/tasks
  [OK ] handbook_access         : Handbook verified on disk at /workspace/data/skills/managed-care-operations-handbook (SKILL.md present)

  --- Mode Summary ---
    [READY    ] OFFLINE   
    [READY    ] TOOLS     
    [NOT READY] UNGRADED  (未配置参赛模型 Key)
    [NOT READY] SCORED    (未配置 ANTHROPIC_API_KEY)

  STATUS: READY for mode 'offline'.
  ```

### 2.5 实际生产入口干运行测试（dry-run）
- **命令**：
  ```bash
  docker compose run --rm dev python3 scripts/run_baseline.py \
      --agent deepagents \
      --model deepseek/deepseek-chat \
      --domain pa_provider \
      --task-name pa_t018_t018_o001_p01_new_referral_provider \
      --dry-run
  ```
- **退出码**：`0`
- **生成预览**：
  ```yaml
  agent: deepagents
  concurrency: 1
  dataset: /workspace/data/prior_auth_provider/tasks
  env_file: /workspace/.env
  environment: docker
  include_task_name:
  - pa_t018_t018_o001_p01_new_referral_provider
  max_retries: 0
  model: deepseek/deepseek-chat
  n_attempts: 1
  n_tasks: 1
  timeout_multiplier: 1.0
  trials_dir: /workspace/runs/run-20261024t103843z-c1978a8a/output/trials
  ```
- **生成真实 CLI 命令**：
  ```bash
  uv run --project /workspace/vendor/chi-bench cb experiment run -f <run_dir>/experiment.yaml
  ```
- **输出状态**：`[dry-run] status: dry_run/not_executed — no task started, no manifest created.`

---

## 3. 状态分层与边界

| 层面 | 当前状态 | 证据与说明 |
| --- | --- | --- |
| **D0 离线实现** | **已完成** | 最小容器构建成功；单题配置生成、分模式就绪、二元判分、预算边界与 42 项离线测试全部通过。 |
| **D0 离线验收** | **待 Codex 独立审核** | 候选代码与本报告均已就绪，保持本地提交，停止进一步修改。 |
| **A 官方工具接入** | **暂停 / 未执行** | 未拉取完整官方源码（vendor/chi-bench），未启动真实任务容器世界，实时 MCP schema 仍未获取。 |
| **B 模型工具往返** | **暂停 / 未执行** | 未调用付费模型 API，5 元预算保持完整留存。 |
| **C 真实任务执行** | **暂停 / 未执行** | 未运行真实 trial，官方 reward 为 null，无真实评测通过声明。 |
| **官方判分** | **暂缓** | 本地判分因缺 Claude 账号已暂缓，不编造跳过 judge 开关。 |

---

## 4. 关键设计取舍与教学材料

### 4.1 为什么不能用 `cb submission run` 跑单题？
在固定上游代码中，`cb submission run` 的输入是 `SubmissionConfig`，它接受的是整个 `domain`，内部会隐式遍历领域下的所有任务。在旧实现中，执行器试图将 `include_task_name` 和 `n_tasks: 1` 写入 submission YAML 的 `run:` 字段，但 `SubmissionRun` 定义严格启用了 `extra = "forbid"`，该字段在反序列化时会被 Pydantic 判定为非法字段并报错抛出异常。
修复方案改用固定上游原生用于受控实验的 `cb experiment run -f <ExperimentConfig>`，该 schema 明确支持 `include_task_name: list[str]` 与 `n_tasks: int`，从机制上杜绝了多题 fan-out。

### 4.2 为什么必须区分 `reward=0` 与 `verdict=null`？
- `reward=0`：评测执行成功、verifier 正常输出评分，但 Agent 没有完成医疗业务目标（如未发现缺失材料或申请被拒绝）。这属于**已完成的评测（completed evaluation）**。
- `verdict=null`：进程中途崩溃、超时、或 verifier 没有产生结果文件。这属于**进程/基础设施失败（process failed 或 incomplete）**。
混淆这两者会导致把基础设施故障误判为模型能力不足，或把未跑完的任务误统计进通过率。

### 4.3 为什么容器内依赖放在 `/opt/venv` 而非 `/workspace/.venv`？
宿主机项目目录在容器运行时以 bind mount 方式挂载至 `/workspace`。如果将依赖安装在 `/workspace/.venv`，会导致容器内的 Linux 二进制依赖覆盖宿主机构建，或者在重建容器时被宿主机未安装依赖的目录遮蔽。将虚拟环境放置在容器系统的独立路径 `/opt/venv`，彻底解耦了容器环境与宿主机工作区。

---

## 5. 未验证项与后续建议

1. **上游完整 checkout**：`vendor/chi-bench` 尚未 clone（Pinned commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`），目前离线测试使用合成 fixture 验证生产入口契约；进入阶段 A 时需在容器内完成拉取。
2. **调度容器调用 Docker 引擎权限**：本轮已验证容器内通过挂载 `/var/run/docker.sock` 成功探测宿主机 Docker 守护进程，下一阶段 A 将进一步验证容器内调度并列任务容器。
3. **真实模型 API 接入**：未配置或调用 `GEMINI_API_KEY` / `DEEPSEEK_API_KEY`，运行时限额与逐请求拦截将在获授权的阶段 B 验证。
