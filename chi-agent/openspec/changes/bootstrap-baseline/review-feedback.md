# bootstrap-baseline 返工任务，第 1 轮

规格负责人/独立验收：Codex。执行器：Antigravity 的 chi-agent 会话 `b5d07b48-57b7-4720-b6a2-00350e0bfca9`。

2026-10-20（Asia/Shanghai）：候选 `9a347195fc786c69db5ecddd4c1b2d50615eb682` 未通过。先读 `reviews/bootstrap-baseline-2026-10-20.md` 和配套 observations JSON，再读原 proposal/design/specs/tasks。

## 本轮范围

只修复现有 bootstrap-baseline 的调用契约、结果判定、测试和交接。保持“Codex 负责规格与验收、Antigravity 负责实现”。

不运行付费模型评测、不假定手册已获批、不提交比赛或推送 GitHub、不修改 RepoPilot。离线修复无需等待用户报名；依赖访问权限的步骤继续明确标为待办。

## 必须完成

- [ ] R1：使用固定提交真正支持的单任务接口；禁止隐式领域批量执行；测试实际 argv/config 的任务选择。
- [ ] R2：删除或修正非法 submission slug，用真实 schema/契约检查配置。
- [ ] R3：按固定上游 trial/reward 产物验证二元 reward；绑定目标身份，拒绝多记录歧义和无效判分；进程完成与评测完成分开。
- [ ] R4：关键测试驱动生产入口，只替换外部依赖；覆盖超时、命令失败、异常、reward 0/1/null/非法值与单任务边界。
- [ ] R5：让 --env-file 与凭据检查一致；干运行不调用模型并有明确终态；校验有限正数时间限制并说明超时清理范围。
- [ ] 补最小可复现的 Python 依赖清单，明确解释器，记录实际命令和退出码。
- [ ] 同步 README、tasks 中自己完成的项和仓库内交付报告；删除无证据的成本估计。原验收报告作为历史记录保留。

实现方式允许合理调整；若需改变外部行为或验收口径，先报告差异，由 Codex 更新规格。不要通过弱化测试、把 fixture 标为真实产物或代勾用户/审查任务来通过验收。

## R1 / R3 实施中澄清

- 固定上游 `include_task_name`、`n_tasks` 是 ExperimentConfig 字段，SubmissionRun 没有这些字段。把字段塞进 submission YAML 不能证明实际生效。使用 `cb experiment run -f <ExperimentConfig>` 并验证实际解析/转发，或使用明确的单任务 dataset 路径。
- 本任务仅接受数值 0 或 1。0.5、负数、超范围值、NaN/Inf、字符串和布尔值均不得作为有效二元判分；不能用 >=1 的通过阈值放宽输入验证。
- 真实 trial 目录和 task 身份必须按固定上游输出确定，不能假定总是 `output/trials/<task_name>`；缺证据或歧义时报告 unknown/incomplete。
- 公共源码参考缓存在 `.coordination/upstream-reference/`，其 README 说明出处与截取范围；它不是 vendor checkout 或运行证据。

## 交付信号

自测完成后，报告保存到仓库内 `reviews/bootstrap-baseline-rework-1-handover.md`，不依赖 Antigravity 私有 brain 目录。

最后写 `.coordination/delivery.json`（已忽略），至少包含：

```json
{
  "schema_version": 1,
  "task_id": "bootstrap-baseline-rework-1",
  "status": "ready_for_review",
  "candidate_commit": "实际交付 SHA，未提交则为 null 并提供可核验差异",
  "completed_at": "实际 ISO 时间",
  "handover_path": "reviews/bootstrap-baseline-rework-1-handover.md",
  "tests": [{"command": "实际命令", "exit_code": 0}],
  "real_baseline_run": false,
  "remaining_prerequisites": []
}
```

先完成实现、自测和报告，再写 ready_for_review，随后停止修改等待验收。无法继续的权限/账号/配额问题使用 needs_user_input 状态并说明具体原因。

Codex 自动检查时会核对代码身份、独立审查并重跑适用检查。执行器不代勾审查或用户验收。
