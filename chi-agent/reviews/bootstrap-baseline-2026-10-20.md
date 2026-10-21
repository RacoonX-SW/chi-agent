# bootstrap-baseline 独立验收

日期：2026-10-20（Asia/Shanghai）。候选提交：`9a347195fc786c69db5ecddd4c1b2d50615eb682`。

## 结论与实际检查

**离线候选未通过验收，需返工；真实基线未运行。**

独立运行 `python3 -m unittest discover -s tests -v`：30/30 通过。但部分测试仅构造字典或在测试中模拟状态赋值，没有执行生产入口，不能证明调用契约和结果收集正确。

另用 Python 3.13 调用了真正的 `run_baseline.main()`，仅替换前置检查和外部 subprocess，在临时目录提供输出 fixture。5 个观察记录保存在 [observations.json](bootstrap-baseline-2026-10-20-observations.json)。这是离线探针，不是官方任务或模型评测。

上游提交已通过 GitHub connector 核实存在；以下接口判断针对同一固定提交。

## 阻塞问题

### R1 / P1：没有真正限制为单个任务

位置：`scripts/run_baseline.py:139–143, 182–226`。

入口使用 `cb submission run` 并附加 `--task-id`。固定上游 `submission_run()` 仅接受 config、domain 和 skip_preflight，没有 `--task-id`。显式提供任务 ID 会被 CLI 拒绝；省略时 YAML 仅选择领域，会上游 fan-out 到领域中的任务，不是注释声称的第一个任务。manifest 却无条件记录 `n_tasks: 1`。

使用固定提交实际支持的单任务路径，例如 `cb experiment run --dataset <具体任务目录>`，或同等经过验证的方案。缺少任务标识必须拒绝或解析为一个明确、可验证的公开任务。

### R2 / P1：生成的提交 ID 不符合上游 schema

位置：`scripts/run_baseline.py:175–185`。

run_id 含大写 `T` 和 `Z`，submission_id 直接拼接 run_id。固定上游 `SubmissionMeta._slug_safe()` 要求全小写。独立探针确认生成的 ID 不合法。若改用 ExperimentConfig、不再需要 submission ID，可以删除不适用路径；保留的配置必须满足真实 schema。

### R3 / P1：判分来源、数值和完成状态错误

位置：`scripts/run_baseline.py:315–355`。

代码搜索第一个 scorecard 并读取其顶层 reward。官方还使用 verifier/reward.json 及 trial result 的 verifier_result；scorecard 提供 binary_reward 等诊断信息。探针提供官方形状的 reward=1 产物后，manifest 仍为 null；任意 `{"reward": 0.5}` 却会被直接接受。

按固定上游产物提取并验证二元 reward，绑定目标 task/trial，排除聚合记录、无关文件和多记录歧义。进程 exit=0 但缺有效判分应为未完成；reward=0 则是已完成评测、任务未解决。

### R4 / P1：关键测试没有调用生产执行逻辑

位置：`tests/test_readiness_and_baseline.py:242–409`。

`_make_manifest()`、`_run_with_mock_subprocess()` 在测试内自行设置 reward/status；后者没有调用 runner 的 main 或执行函数。即使生产超时、失败、判分分支损坏，这些断言仍可通过。

替换为对真实入口的测试，仅 mock 网络、进程、时钟等外部边界。覆盖成功、reward=0、命令失败、超时、启动异常、缺判分、非法 reward、单任务选择和凭据缺失，fixture 与固定上游结构一致。

### R5 / P2：env-file 与干运行状态不一致

位置：`scripts/run_baseline.py:60–104, 146–170, 264–269`。

虽然提供 --env-file 和 .env.example，前置检查只读当前进程环境，仅按文档写入 .env 仍会被判缺 key。dry-run 也先经过真实访问门禁；门禁满足后，又留下 started、finished_at=null 的 manifest，尽管没有启动任务。

统一配置加载和优先级。干运行应不调用模型、输出真实命令并有 dry_run/not_executed 终态。时间限制应为有限正数；说明真实超时的子进程/容器清理和未知外部请求边界。

## 环境与未验证项

- 本机有 Python 3.13.5，但 Codex 默认 python3 指向 3.9.6，应使用明确解释器/项目环境。
- PATH 无 uv。Docker CLI 存在，但沙箱外 docker info 也失败，socket 不存在；不能归因于沙箱限制。
- vendor/、runs/ 为空。验证远端 pin 不等于克隆、安装或运行。
- 当前进程缺少所需 API key；不代表其他工具或环境没有凭据。
- Kaggle 报名、手册获批未确认。真实镜像 ID、用量、成本未测量。
- 原交付报告“每轮成本预计 < $1”没有实测证据，不应作为可信预期。

## 固定上游依据

- [CLI 源码](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/cli.py)：experiment_run、submission_run。
- [Submission schema](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/submission.py)：领域路径与小写 slug 校验。
- [ExperimentConfig](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/config.py)：dataset、env_file、trials_dir 与时间限制。

返工要求见 [review-feedback.md](../openspec/changes/bootstrap-baseline/review-feedback.md)。
