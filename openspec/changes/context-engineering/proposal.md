# 上下文工程与执行可靠性（context-engineering）

状态：**设计已定（2026-11-08 讨论），未实现、未运行真实 B/C。** 真实模型/judge/Trial/发布不在本变更内；实现需另行授权。正式验证前还需处理 240s 单请求读超时（另立小变更）。

## 1. 为什么

1. **上下文没有工程化**：t022-rerun5 round 15 请求 652,663 字节、65 条消息；工具结果 74%（`local-fs-read` 350KB/22 次，单次最大 104KB），reasoning 10%，tools schema 10.5%。
2. **预算单位混用**：`max_estimated_tokens` 实际存 UTF-8 字节；`max_chars` 永远是死参数；无法回答“离模型窗口还有多远”。
3. **长任务撞 240s 单请求读超时**：t022-rerun5 round 15 `240,005ms`；t024-rerun6 round 6 `240,008ms`。两题都不是 output truncation，recovery 一次未触发。
4. **完成门禁留口子**：run_log 记录 `final_text_without_claim_not_blocked`，模型可以不 claim 就宣布完成。
5. **官方不提供好用的政策检索**：payer agent profile 不暴露 `payer_policy_library.search`（仅 full profile）；search 只对 title/filename/category 做子串匹配；handbook 是 1,279 个 md + 11 个 pdf 文件。

## 2. 做什么

五项能力，按依赖排序：

| # | 能力 | 核心 |
| ---: | --- | --- |
| 1 | 预算模型 v3 | token/字节双轨、模型 profile、校准、删除死参数 |
| 2 | 上下文装配 | 工具层截断 + reducer + 去重 + 占位符；reasoning 暂缓 |
| 3 | 多轮状态 | 事实分层、意图锚点、漂移检测（先警告后停止） |
| 4 | 完成门禁 | 强制 claim、程序推导证据、执行/验证分离、负证据、终态对象 |
| 5 | 检索 L0 | 结构化关键词检索；L1/L2 仅在有证据时 |

## 3. 不做什么

- 不做向量 RAG；
- 不做任务级 resume；
- 不做 reasoning 压缩（暂缓）；
- 不做 LLM 摘要与 output_recovery 的组合；
- 不跑 judge/Trial/发布，不 auto-merge。

## 4. 成功标准

- 离线测试覆盖五项能力，旧 v2 证据仍可读；
- 合成上下文从 652KB 降到 150–250KB；
- 无 claim 的最终文本被门禁判为 incomplete；
- 漂移先警告、重复升级停止；
- 真实验证仍需单独授权与新的 bundle/B。

## 5. 证据来源

- `runs/final-validation-20261105/nine-rerun5-20261108/`（t022 15 轮、240s 超时）；
- `runs/final-validation-20261105/nine-rerun6-20261108/RESULT.md`（t024 6 轮、240s 超时）；
- `vendor/chi-bench/src/chi_bench/mcp/payer_server.py:174`、`services/policy_library.py:105-118`；
- `data/skills/managed-care-operations-handbook`（1,279 md + 11 pdf）。

## 6. 依赖

- 240s 读超时覆盖：建议另立小变更，先于本变更的真实验证；
- 预算常量与工具 schema 变化会改 bundle 身份：需重建 bundle + 新 B；
- 真实运行仍需用户单独授权。
