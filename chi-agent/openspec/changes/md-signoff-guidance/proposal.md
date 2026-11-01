# MD 决定签核与 P2P 收口指导

建立：2026-11-02，基于 `codex/ab-capability-toggle` `516e6aa`。只改版本化角色指导；不改工具、校验器或世界。

## 为什么需要

t027（nurse_review，denial 路径）唯一 false 是 `md.signed_off`：Agent 提交 `p2p_review`（允许 `signed_off=false`），随后直接 `determination.finalize` 成 `denied`，MD 决定始终未签核。

公开工具文档已经写明：

- `submit_md_case_decision` 的 `signed_off` 是显式布尔参数，默认 false；
- 终局决定（approve/deny/partial_approve）必须签核；只有 `request_info`/`p2p_review` 可不签；
- `p2p_review` 是“保留最终决定”，要等 P2P 之后再收口。

原 guidance 只写“决定要匹配规则”，没有提示这个参数与 P2P 的先后关系，模型因此用了默认 false。

## 范围

- payer invariants 增加两条：
  1. `signed_off` 对终局决定必须为 true；
  2. 选 `p2p_review` 时先完成 P2P 再 finalize，不得从“仍保留决定”的记录直接出不利终态。
- 测试断言这三条关键表述存在。

## 非范围

- 不把 MD 变成每题必经步骤。
- 不改校验器、不读隐藏期望、不按题写策略。
