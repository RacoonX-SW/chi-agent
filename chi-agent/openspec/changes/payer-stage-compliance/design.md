# 设计：条件化的阶段完成要求

## 问题分类

这不是“模型缺少工具”或“世界不接受”，而是**计划阶段漏掉 instruction 点名的步骤**：工具 `review.save_md_review`、`review.submit_md_case_decision` 在可用列表中，`review.get_md_review_data` 也调用过，但没有提交 MD 决定。

## 变更

payer invariants 由一条绝对句改为两条条件句：

1. MD 不是每个 case 的必经步骤；但当 instruction 声明端到端所有权并点名后续阶段（MD 决定、P2P 等）时，必须完成该阶段再 finalize。
2. 提前收口只有在观察到的公开规则使后续阶段不必要时才合法，并需记录理由。

guidance 仍通过工具下发，不进入官方 system prompt；digest 覆盖全部交付内容。

## 为什么不改校验器

校验器反映的是公开规则和任务 instruction 的要求；放宽它会把“没做 MD”写成通过。正确修复是让计划阶段读 instruction 并执行被点名的步骤。

## 验证

- 测试：payer guidance 同时包含 “not a mandatory step”“names a later stage”“makes the later stage unnecessary”。
- digest 变化可复现；无新工具、无新请求类型。
