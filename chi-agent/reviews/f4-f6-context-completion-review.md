# F4–F6 上下文、完成核验与失败处理：实现与离线证据

更新：2026-11-01。本报告只记录 F4–F6 的离线实现候选与自测；状态/权限见 [REVIEW_STATE](REVIEW_STATE.md)。**尚未外部 Gemini 复审，未真实模型/任务/判分/临床评审。**

## 1. 身份

| 项目 | 值 |
| --- | --- |
| 基线 | `066c9ae`（PR32 合并后的 `origin/main`） |
| 实现候选 | `efc90190ff3b3ce2b313f119aa2c2abd7471366a` |
| 分支 | `codex/f4-f6-context-completion`（未推送/未开 PR） |
| 环境 | Docker `chi-agent-dev:latest`，Python 3.12.15，固定 SDK/PDF 卷 |

## 2. 实现范围

| 能力 | 交付 | 文件 |
| --- | --- | --- |
| F4 测量 | system/instruction/tools/history/tool_result/reasoning 字符、字节、估计 token 分列；不存正文 | `scripts/go_chi_context.py` |
| F4 预算 | 3.5M 字符 / 1M 估计 token / 8k 输出预留；发送前停止 | `go_chi_guard.py`、`go_chi_runtime.py` |
| F4 记录 | `logs/context.jsonl` + run_log 统计；不重写历史 | `go_chi_runtime.py` |
| F5 完成 | `chi-completion-v1`、`local-completion-check`、run_log completion | `go_chi_state.py`、`go_chi_tools.py` |
| F6 未知写 | MCP mutation 异常返回 `UNKNOWN_WRITE_EFFECT`、open unknown、禁止重发写、未解决终态 | `go_chi_mcp.py`、`go_chi_state.py` |
| F6 停滞 | 重复读第 3 次警告/第 5 次阻断；重复写第 2 次阻断 | `go_chi_state.py`、`go_chi_tools.py`、`go_chi_mcp.py` |

## 3. 行为要点

- 上下文预算在 `journal.reserve()` 前检查，超限不产生请求；`context.jsonl` 只写计数，不复制正文。
- 默认预算是字符估计，明确 `configured_unverified`；服务返回的 `input_tokens` 另记，不冒充精确 tokenizer。
- 自动历史压缩**不采用**：`ToolContract.validate_history()` 要求完整批次；缺少新 contract 版本、reasoning/tool 关联、替换 hash、旧检查点防覆盖和真实 SDK/API 证据。F4 交付测量、预算、组织、停止，不声称压缩完成。
- 完成报告区分 `mechanical_pass/not_applicable/blocked` 与 `observed/not_observed/not_verified/unknown/violation`；只做机械/来源检查，不是临床/官方 verdict。
- MCP mutation 异常（非取消、非 fatal）不再直接终止 run，而是返回 `UNKNOWN_WRITE_EFFECT: <code>`，登记 open unknown；期间任何写被拒绝，模型只能用同目标更晚只读观察 resolve；未解决结束则 `chi_unknown_write_effect` incomplete。
- 重复读 3 次追加 `STAGNATION`，5 次拒绝；重复写 2 次拒绝；不自动重试/换模型/后台轮询。
- 本地文件写异常仍按原逻辑失败，不转成可继续的 unknown。

## 4. 实际命令与结果

定向：

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest \
  tests.test_go_chi_context tests.test_go_chi_state tests.test_go_chi_capabilities_runtime
```

结果：`Ran 37 tests ... OK`。

全量：

```bash
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

结果：`Ran 436 tests`，`FAILED (errors=2, skipped=8)`；2 个错误仍是既有环境缺 `anthropic`（`test_dev_patient_adapter`、`test_dev_patient_network`），无新增回归。

过程中的真实失败已修正：

1. 首版 run_log 用 `usage["prompt_tokens"]` 汇总，但 journal 结算字段是 `input_tokens`，导致 `chi_log_persistence_failed`；改为 `input_tokens` 后通过。
2. 新增 target-required 后，旧的 unknown/resolve 测试未设 target，按新契约补 target。
3. 未知写从“直接终止”改为“可只读查证”后，旧测试期望 GoFailure；改为验证继续、resolve、未解决终态两条路径。

## 5. 未验证项

- 真实 tokenizer、服务端 prompt_tokens 与 3.5M/1M 预算的实际余量；默认值只是保守估计。
- 真实模型是否会遵守 `STAGNATION` 提示、是否会在未知写后正确只读查证。
- 真实 MCP 超时/断连后的服务端副作用；当前只验证合成异常。
- 自动压缩/历史重写的 SDK/DeepSeek 协议可行性；当前明确不采用。
- 真实任务、业务终态、临床正确性、官方分数。
- 外部 Gemini 尚未复审；PR 尚未创建。

## 6. 下一步

1. 外部 Gemini 审查契约与实现候选，重点攻击未知写是否过宽、open unknown 是否应精确到 scope、停滞阈值、预算披露、压缩不采用理由。
2. 按意见返工后固定新候选。
3. 通过后创建 PR；Z1 配送、F7 实验清单和真实运行审批包另行推进，不混入本 PR。

## 7. 外部 Gemini 复审结论（2026-11-01）

- **结论**：通过（LGTM），建议创建 base=main 的 PR 交用户最终合并。
- **审查对象**：F4–F6 候选 `efc9019` / 文档/分支 HEAD `20b59b5`；复审方未在结论中另附命令日志，本条按用户转述记录。
- **逐项结论**：
  - F4 上下文预算与度量：通过；预算在 dispatch 前硬拦截，边界严格，无 prompt 脱敏泄露风险。
  - F5 完工检验：通过；报告状态与 claim/unknown 对齐，严守机械验证语义，不越界下临床结论。
  - F6 未知写恢复：通过；异常捕获合理，写阻断严格，恢复条件防穿越/跨 case，未结终态正确判 incomplete。
  - F6 停滞保护：通过；读 3 警 5 阻、写 2 阻，状态留痕且放行异参写。
- **边界**：仅离线静态/契约核对与 Docker 合成 MCP/HTTP 回归；未调用真实模型/外部付费 API，未执行官方判分或未见题；不构成真实模型、业务效果、临床正确性或官方评分通过。
- **后续**：创建 base=main 的 PR 由用户合并；真实运行仍需新 bundle manifest、合规 B 凭据与配额校验。自动压缩设计按讨论继续搁置，未进入本候选。
