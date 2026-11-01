# F7 实验清单与全分母汇总：实现与离线证据

更新：2026-11-01。本报告只记录 F7 离线工具候选；状态/权限见 [REVIEW_STATE](REVIEW_STATE.md)。**未运行真实实验，未官方判分，未临床评审。**

## 1. 身份

| 项目 | 值 |
| --- | --- |
| 基线 | `4ade699`（PR34 合并后的 `origin/main`） |
| 实现候选 | `fd617c3f5c25ce06403fcbb72b775c826fe189f4` |
| 分支 | `codex/f7-experiment-harness`（未推送/未开 PR） |
| 环境 | Docker `chi-agent-dev:latest`，Python 3.12.15 |

## 2. 实现

- `experiment_manifest.py`：
  - `chi-experiment-campaign-v1` 严格校验；未知字段、重复 cell/task、缺停止条件拒绝。
  - F1–F6 mechanism；off/on 两臂必须同任务集合、角色、attempt、limits；不可独立切换用 `na` + reason。
  - 任务资源只登记 manifest SHA 与世界镜像 ID，不登记答案/rubric/隐藏路径。
  - `freeze_manifest()` 生成规范 JSON + SHA-256；CLI `validate`/`freeze`。
- `experiment_summary.py`：
  - `chi-experiment-record-v1` 严格校验；candidate 必须与 manifest 一致；计划外/重复记录拒绝。
  - 全分母：planned/attempted/completed/failed/skipped/blocked/not_run/missing_evidence。
  - checks pass/fail/na/not_run；NA、跳过、缺日志不补 pass。
  - usage 分 known sum / missing；official reward 只计 present/absent，不合成。
  - failure code 计数、by_role 计划/未运行分母；off/on 只并列，不计算因果或 success rate。
  - CLI `summarize`，支持 JSON 数组/JSONL。

## 3. 实际命令与结果

定向：

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -e PYTHONPATH=/workspace/scripts -e PYTHONDONTWRITEBYTECODE=1 \
  -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest tests.test_experiment_harness -v
```

结果：`Ran 15 tests ... OK`。

全量：

```bash
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

结果：`Ran 451 tests`，`FAILED (errors=2, skipped=8)`；2 个错误仍是既有环境缺 `anthropic`，无新增回归。

过程中的真实失败已修正：

1. checks 计数器用 `Counter(pass_=0)`，实际 key 变成 `pass_`，与 `checks["pass"]` 不一致；改为显式 dict 初始化。
2. by_role 只从已有 record 建角色，漏了“计划但未运行”的角色；改为从 manifest 计划任务初始化 planned。
3. CLI 测试补上 stdout 捕获与有效/无效退出码。

## 4. 未验证项

- 未用真实 Z4/Z5 manifest/record 运行；没有真实任务、模型、模拟器或官方分数。
- 检查项 ID/适用性尚未与真实检查器映射；当前只验证汇总契约。
- 真实日志 hash、用量/费用字段、attempt 回归流程仍需接入。
- 外部 Gemini 尚未复审；PR 尚未创建。
- 不计算 success rate/因果，也不证明某机制有效。

## 5. 下一步

1. 外部 Gemini 审查 manifest 严格性、off/on 单变量约束、检查分母和缺证据语义。
2. 按意见返工后创建 PR。
3. 合并后进入 Z1 正式配送离线准备；Z4/Z5 的真实 manifest/record 需用户另行批准任务/次数/资源。
