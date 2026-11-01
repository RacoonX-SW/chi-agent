# F4–F6 执行清单

当前：离线实现候选已完成 Docker 自测，待外部 Gemini 独立复审；真实运行未启动。

## F4 上下文

- [x] 新增 `go_chi_context.py`：system/instruction/tools/history/tool_result/reasoning 分列，字符/字节/估计 token 分开。
- [x] 默认预算 `chi-context-budget-v1`：3.5M 字符、1M 估计 token、8k 输出预留；标记 configured_unverified。
- [x] guard 在 `journal.reserve()` 前检查预算；超限 `chi_context_budget_exceeded`。
- [x] 每次请求写 `logs/context.jsonl`，不含正文；run_log 写上下文统计。
- [x] 组织复用 F1 状态摘要/F3 片段回读；明确自动压缩不采用及原因。
- [ ] 真实 tokenizer/服务端预算与真实 SDK 历史续接验证（需真实运行，未授权）。

## F5 完成核验

- [x] `chi-completion-v1` 报告：mechanical_pass/not_applicable/blocked + observed/not_observed/not_verified/unknown/violation。
- [x] `local-completion-check` 只报告，不替代 claim。
- [x] run_log 保存 completion 报告；claim 仍用原门禁。
- [x] 测试覆盖无写、写后回读、写后未回读、unknown、violation。
- [ ] 真实任务终态与最终输出一致性（需真实运行）。

## F6 未知写与停滞

- [x] MCP mutation 异常转 `UNKNOWN_WRITE_EFFECT`，登记 open unknown，不自动重发。
- [x] open unknown 期间拒绝所有 mutation；只允许同目标更晚只读 resolve。
- [x] 未解决 unknown 结束 → `chi_unknown_write_effect` incomplete。
- [x] 重复读：第 3 次警告、第 5 次阻断；重复写：第 2 次阻断。
- [x] 测试覆盖读回/resolve、未知期间写拒绝、未解决终态、重复读/写。
- [ ] 真实 MCP 超时后的服务端副作用与真实模型停滞行为（需真实运行）。

## 集成与文档

- [x] 全量 Docker：436 tests，2 个既有环境错误（缺 `anthropic`），8 skipped；新增 12 个测试。
- [x] `git diff --check` 通过。
- [x] 外部 Gemini 复审实现候选 `efc9019`：通过（LGTM；限离线静态/契约/Docker 合成，无真实模型/判分/未见题）。
- [ ] 更新 README/REVIEW_STATE/阶段报告（本提交）。
- [ ] 用户合并后开 Z1/F7 或真实运行审批包；不在本 PR 混入真实调用。
