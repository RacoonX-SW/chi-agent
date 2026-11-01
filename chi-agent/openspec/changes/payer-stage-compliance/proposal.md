# payer 阶段性指令遵从（MD 决定与终态分支）

建立：2026-11-01。基于 `codex/real-run-v4` `4e4b717`。本变更只改版本化角色指导文本；不改工具、校验器、账目或世界。

## 为什么需要

payer 003 在真实运行中 `complete`，但四项确定性检查为 false，且与 W 批次完全相同：

- `md.audit`、`md.decision_exists`：目标 case 没有任何 MD 决定；
- `outcome.letter_types`、`outcome.target_status`：终态/信件随分支变化。

从**公开 instruction**（不含隐藏期望）即可看出原因：该题要求“walk the intake checklist, route it, then drive clinical review, **MD decision**, and any P2P through to final determination yourself”。运行轨迹显示 Agent 读了 `review.get_md_review_data`，但没有调用 `review.save_md_review` / `review.submit_md_case_decision`，直接用护士建议作为 determination 来源批准结案。

现有 guidance 只写“MD review 是可能的合法分支，不是每个 case 的必经步骤”，缺少“当 instruction 明确点名该阶段时必须执行”的条件，容易被理解成可以提前收口。

## 范围

- `chi-role-guidance-v1` payer invariants：把“MD 可选”与“instruction 点名时必须执行”写成同一条件句，并要求提前收口时记录规则依据。
- 测试断言该条件句存在，且原“not a mandatory step”表述保留。
- digest 随内容变化（`delivered_invariants()` 已覆盖）。

## 非范围

- 不读取、不引用隐藏 `expectations.json` 调参；只依据公开 instruction 与公开规则。
- 不硬编码 task id、不规定某题必须 MD、不改变校验器或分数。
- 不改变工具数量、账目语义或真实运行次数。
