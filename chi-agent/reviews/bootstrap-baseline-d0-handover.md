# bootstrap-baseline/D0 交付报告（R1–R8 返工）

- **日期**：2026-10-24
- **阶段**：`bootstrap-baseline/D0`（离线环境构建与包装代码修复，R1–R8 专项返工）
- **执行器**：Antigravity + Gemini 3.8 Flash (High)
- **开工基线提交**：`ff2e23d72fe1ae37b41872fbae655a1498c592e0`
- **上次已审候选**：`01a044fe237aff7ddcafc3332e9444d443c41999`
- **分支**：`main`
- **状态**：`ready_for_review`

---

## 1. R1–R8 返工逐项修复说明

针对 Codex 独立审核报告（`reviews/bootstrap-baseline-d0-review.md`）中的 R1–R8 进行了逐项彻底修复与离线验证：

| 编号 | 问题与要求 | 修复位置 | 具体修复与设计保障 |
| --- | --- | --- | --- |
| **R1 (P1)** | **未验证的 ungraded 真实入口应明确阻断**<br>固定上游 `cb experiment run` 无已验证 skip-judge 开关，不能宣称 verifier 未执行。 | `scripts/run_baseline.py`<br>`tests/test_readiness_and_baseline.py` | 1. 在 `_check_prerequisites()` 中，当 `mode == "ungraded"` 时直接添加明确阻断原因，在外部进程启动前退出（code 2）。<br>2. 记录 `execution_status="blocked_before_execution"`、`blocked_prerequisites` 理由与 exit_code 到 manifest。<br>3. 保留 `--dry-run` 预览与离线模式。<br>4. 新增 `test_ungraded_real_execution_blocked_before_subprocess`，断言外部执行进程完全未调用。 |
| **R2 (P1)** | **预算与生成限额需离线决策逻辑**<br>此前仅记录在 manifest 中，无用量预留或停止判断，且未知用量误写 `within_budget`。 | `scripts/run_baseline.py`<br>`tests/test_readiness_and_baseline.py` | 1. 实现 `evaluate_budget()` 函数，定义 `MIN_SINGLE_REQUEST_RESERVATION_CNY = 0.001` 元最低单请求预留。<br>2. 执行前若预算不足最低预留，立即返回 `stopped_insufficient_budget` 并阻断运行。<br>3. 包装层未测量 token 用量或成本时，manifest 的 `budget_status` 严格标为 `unverified_unknown_usage`，绝不虚假声称 `within_budget`。<br>4. 在 `build_experiment_config()` 中将 `max_rounds`, `max_tokens_per_request`, `budget_cny` 注入 `agent_kwargs`。<br>5. 补齐正常、不足、未知用量回归测试。 |
| **R3 (P1)** | **判分收集绑定唯一目标 trial，严格验证类型与来源**<br>此前未解析 `config.json` 元数据、未拒绝随机后缀/截断/多结果歧义，且误接受字符串 `"1"`。 | `scripts/run_baseline.py`<br>`tests/test_readiness_and_baseline.py` | 1. 重写 `extract_reward()`：遍历匹配候选 trial，优先读取 `trial_dir/config.json` 中的 `task.path` / `task.id` / `task.name` 元数据，次选 `task_name__<suffix>` 前缀匹配。<br>2. 发现多条匹配 trial 时明确拒绝歧义（返回 `(None, None, "Ambiguous...", None)`）。<br>3. 严格二元数值校验：必须为 `int` 或 `float`，严格排除 `bool`（排除 Python `isinstance(True, int)` 陷阱）、排除字符串 `"1"`、排除非有限值（`NaN`, `Inf`）、排除非二元值（如 `0.5`, `-1.0`）。<br>4. 返回并记录实际读取的 `reward_path`（而非猜测路径）。 |
| **R4 (P1)** | **移除 D0 默认 Docker socket 挂载，离线检查不依赖引擎权限**<br>D0 开发服务挂载了 socket，且 offline 模式将 docker 列为必要条件。 | `compose.yaml`<br>`scripts/check_readiness.py`<br>`Dockerfile` | 1. 从 `compose.yaml` 中彻底移除 `/var/run/docker.sock` 挂载。<br>2. 从 Dockerfile 中移除 `docker-cli`。<br>3. `check_readiness.py` 中的 `offline` 模式要求仅保留 `[python_version, git, uv]`，移除 `docker_chk`，容器内离线就绪无需 Docker 守护进程。<br>4. 新增 `test_offline_mode_does_not_require_docker_or_api_keys` 验证无 socket 环境离线检查。 |
| **R5 (P1)** | **统一就绪门禁与实际执行门禁，缺资料明确阻断**<br>环境变量标志不能假冒已下载手册；ungraded 需 vendor 检出；真实入口需对齐门禁。 | `scripts/check_readiness.py`<br>`scripts/run_baseline.py` | 1. `check_handbook()` 严格要求磁盘上存在 `SKILL.md` 且大于 0 字节；若仅有 `HF_HANDBOOK_ACCESS_GRANTED=1` 而无文件，明确返回 `ok: False` 并说明“授权标志不等于已下载文件”。<br>2. `evaluate_modes()` 中将 `vendor_chk` 加入 `ungraded` 和 `scored` 模式的必要条件。<br>3. `run_baseline.py` 的 `_check_prerequisites()` 严格对齐：核对上游 vendor clone 及 commit、核对任务数据集目录、核对手册文件真实存在、核对候选 runner key、核对预算预留；缺失时明确阻断。<br>4. 保留 Claude Code / OAuth 说明，不将原生 API key 写为唯一判分技术路径。 |
| **R6 (P2)** | **生成并锁定依赖，确保可复现构建**<br>此前无 lock 文件，依赖使用 `>=` 浮动版本。 | `requirements.lock`<br>`pyproject.toml`<br>`Dockerfile` | 1. 在容器内冻结生成 `requirements.lock`，锁定 11 个直接/间接依赖的精确版本（PyYAML 6.0.3, pydantic 2.14.1, pytest 9.1.1 等）。<br>2. `pyproject.toml` 的直接依赖改为精确 `==` 固定版本。<br>3. `Dockerfile` 固定基础镜像 digest（`python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39`）和 `uv==0.6.14`，使用 `uv pip install --no-cache -r requirements.lock` 安装。 |
| **R7 (P2)** | **严格有限正数校验，拦截 NaN 和 Infinity**<br>此前仅检查 `<= 0`，导致 `nan` / `inf` 绕过校验。 | `scripts/run_baseline.py`<br>`tests/test_readiness_and_baseline.py` | 1. 实现 `_validate_positive_finite(name, val)`，使用 `math.isfinite(val) and val > 0` 严格校验。<br>2. 在解析参数后立即对 `--budget-cny`, `--timeout-multiplier`, `--outer-timeout`, `--max-rounds`, `--max-tokens-per-request` 执行有限正数校验，在任何写配置或子进程启动前拦截。<br>3. 新增 `test_non_finite_parameters_rejected` 回归测试。 |
| **R8 (P2)** | **规范化相对 `--env-file` 绝对路径，统一优先级**<br>此前子进程在 vendor 目录执行，相对路径指向不同文件；且环境加载优先级与上游不一致。 | `scripts/run_baseline.py`<br>`tests/test_readiness_and_baseline.py` | 1. 启动入口第一时间执行 `Path(args.env_file).resolve()` 规范化为绝对路径。<br>2. 生成的 `experiment.yaml` 中写入绝对路径，保证 child process 在 `vendor/chi-bench` 下能定位到同一物理文件。<br>3. `_load_env_file()` 读取文件后以文件值覆盖当前进程环境（`{**os.environ, **file_env}`），与固定上游 `load_dotenv(override=True)` 行为完全对齐。<br>4. 新增 `test_relative_env_file_resolves_to_absolute_path` 回归测试。 |

---

## 2. 容器内自测命令与实际执行结果

所有构建、测试与检查均在 Docker 容器内完成，宿主机保留干净状态。

### 2.1 依赖与开发镜像构建
- **命令**：`docker compose build dev`
- **退出码**：`0`
- **构建特征**：
  - Base: `python:3.13-slim@sha256:57b29a7c050c4e679e4bea572e14b3965cf4b5839de2da49d55e49ffc4024f39`
  - uv: `uv==0.6.14`
  - 依赖安装：`uv pip install --no-cache -r requirements.lock`（11 packages locked）
  - Socket 挂载：无（`compose.yaml` 已移除挂载）

### 2.2 离线测试套件（覆盖 R1–R8 补充回归）
- **命令**：`docker compose run --rm dev python3 -m unittest discover -s tests -v`
- **退出码**：`0`
- **输出摘要**：
  ```text
  Ran 51 tests in 0.295s
  OK
  ```
- **关键测试覆盖**：
  - `test_handbook_granted_via_env_flag_alone_fails`: 仅授权标志断言为 `ok: False` (R5)
  - `test_offline_mode_does_not_require_docker_or_api_keys`: 无 docker socket/daemon/keys 离线就绪 (R4)
  - `test_ungraded_mode_requires_vendor_checkout`: 缺少 vendor 检出时 ungraded 门禁阻断 (R5)
  - `test_evaluate_budget_insufficient_reservation`: 预算低于最低预留时阻断 (R2)
  - `test_evaluate_budget_unmeasured_usage_post_execution`: 未测量用量标记为 `unverified_unknown_usage` (R2)
  - `test_extract_reward_with_trial_suffix_and_config_json`: 后缀匹配与 config.json 元数据解析 (R3)
  - `test_extract_reward_rejects_ambiguous_trials`: 多匹配结果拒绝歧义 (R3)
  - `test_extract_reward_rejects_numeric_string`: 拒绝字符串 `"1"` (R3)
  - `test_extract_reward_rejects_boolean`: 拒绝布尔 `True` (R3)
  - `test_extract_reward_rejects_non_binary_float`: 拒绝 `0.5` 与 `-1.0` (R3)
  - `test_ungraded_real_execution_blocked_before_subprocess`: 真实 ungraded 执行在外部进程启动前阻断并记录 manifest (R1)
  - `test_relative_env_file_resolves_to_absolute_path`: 相对 env-file 规范化为绝对路径并传递给 YAML (R8)
  - `test_non_finite_parameters_rejected`: 严格拒绝 `nan`, `inf`, `-inf` (R7)

### 2.3 分模式就绪检查（无 Socket 容器内执行）
- **命令**：`docker compose run --rm dev python3 scripts/check_readiness.py --mode offline --json`
- **退出码**：`0`
- **输出摘要**：
  ```json
  {
    "mode": "offline",
    "ready": true,
    "modes": {
      "offline": {
        "ready": true,
        "failures": []
      },
      "tools": {
        "ready": false,
        "failures": [
          "docker CLI not found",
          "vendor/chi-bench not cloned (expected at /workspace/vendor/chi-bench)"
        ]
      },
      "ungraded": {
        "ready": false,
        "failures": [
          "Docker daemon must be reachable for containerized execution.",
          "vendor/chi-bench not cloned (expected at /workspace/vendor/chi-bench)",
          "No candidate runner API key found. Set at least one of: DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY"
        ]
      },
      "scored": {
        "ready": false,
        "failures": [
          "Docker daemon must be reachable for containerized execution.",
          "vendor/chi-bench not cloned (expected at /workspace/vendor/chi-bench)",
          "No candidate runner API key found. Set at least one of: DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY",
          "ANTHROPIC_API_KEY is not set — required for the official Claude judge."
        ]
      }
    }
  }
  ```

### 2.4 生产入口干运行（Dry-Run Preview）
- **命令**：
  ```bash
  docker compose run --rm dev python3 scripts/run_baseline.py \
      --agent deepagents \
      --model deepseek/chat \
      --task-name pa_t018 \
      --dry-run
  ```
- **退出码**：`0`
- **输出摘要**：
  ```yaml
  agent: deepagents
  agent_kwargs:
    budget_cny: '5.0'
    max_rounds: '30'
    max_tokens_per_request: '8192'
  concurrency: 1
  dataset: /workspace/data/prior_auth_provider/tasks
  env_file: /workspace/.env
  environment: docker
  include_task_name:
  - pa_t018
  max_retries: 0
  model: deepseek/chat
  n_attempts: 1
  n_tasks: 1
  timeout_multiplier: 1.0
  trials_dir: /workspace/runs/run-20261024t115704z-06369ad2/output/trials
  ```
- 结果：验证了单题绑定、`agent_kwargs` 限额注入与绝对 `env_file` 解析；无子进程启动、无 manifest 产生。

### 2.5 真实入口阻断验证（Ungraded Real Execution Blocked）
- **命令**：
  ```bash
  docker compose run --rm dev python3 scripts/run_baseline.py \
      --agent deepagents \
      --model deepseek/chat \
      --task-name pa_t018 \
      --mode ungraded
  ```
- **退出码**：`2`
- **输出摘要**：
  ```text
  ERROR: prerequisites / execution gate not satisfied for mode 'ungraded':

    • vendor/chi-bench not cloned (expected at /workspace/vendor/chi-bench)
    • No candidate runner API key configured. Set at least one of: DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY
    • Ungraded real execution is currently unsupported by fixed upstream cb experiment run (no verified skip-judge mechanism). Blocked before real execution to prevent unverified scored run.

  Execution BLOCKED. Manifest saved to: /workspace/runs/run-20261024t115804z-2e0124fd/manifest.json
  ```
- 记录 manifest 摘要：
  - `execution_status`: `"blocked_before_execution"`
  - `exit_code`: `2`
  - `budget_status`: `"blocked_before_execution"`
  - `reward`: `null`
  - `blocked_prerequisites`: 完整记录上述 3 条门禁阻断原因。

---

## 3. 状态分层与边界

| 层面 | 当前状态 | 依据与证据 |
| --- | --- | --- |
| **D0 离线实现** | **已完成返工** | R1–R8 全部修复，51/51 单元测试通过，依赖锁已就绪，无 socket 离线就绪通过。 |
| **D0 独立验收** | **待 Codex 独立审核** | 新候选 commit 即将创建，交付报告更新完毕，停止进一步代码修改。 |
| **A 官方工具接入** | **暂停 / 未执行** | 未拉取 vendor 源码，未挂载调度引擎，未启动任务容器。 |
| **B 模型工具往返** | **暂停 / 未执行** | 未调用付费模型 API，5 元预算完整留存。 |
| **C 真实任务执行** | **暂停 / 未执行** | 未产生真实 trial，官方 reward 为 null。 |

---

## 4. 未验证项与后续阶段说明

1. **上游源码真实检出**：`vendor/chi-bench` 尚未 clone（Pinned commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`），目前离线测试由合成/mock 测试覆盖；进入阶段 A 时在容器内拉取。
2. **任务容器调度引擎权限**：D0 按照安全最小化原则移除了开发容器默认 Docker socket 挂载；阶段 A 将在授权下验证容器内调度并列任务容器。
3. **真实模型 API 凭据与运行时限额**：未配置或调用真实 `GEMINI_API_KEY` / `DEEPSEEK_API_KEY`，运行时真实 token/round 拦截留待阶段 B 验证。
4. **官方 judge 判分**：本地评分暂缓，保持官方 reward 为 null，不伪造连通性或无判分保证。
