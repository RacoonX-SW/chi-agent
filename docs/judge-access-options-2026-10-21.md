# 判分访问方式：纠正 API Key 唯一性的说法

2026-10-27 补充：用户要求使用已有 DeepSeek 替代本地 Claude 评审。实现契约见 [L 设计](../openspec/changes/bootstrap-baseline/design.md#deepseek-开发评审l)，运行方式见 [README](../README.md)，实际能力与验收结果查 [审核状态](../reviews/REVIEW_STATE.md)。此处下文保留 10 月 21 日的访问核对与当时授权，不作为后续开发暂停指令。

DeepSeek 官方提供 [Anthropic 兼容 API](https://api-docs.deepseek.com/guides/anthropic_api/)，但固定 CHI ClaudeRunner 会清理代理地址；只改环境变量或模型名不能完成本项目接入。L 采用独立的 DeepSeek Chat Completions runner，复用固定 PA adapter、评分条目和提示，确定性部分检查另列；与原版 Claude 的判断可能不同，因此只标本地开发评审，官方 reward 仍为 null。没有 Claude 账号也可改进与测试参赛 Agent，官方最终评分仍由主办方按其协议执行。

核对日期：2026-10-21（Asia/Shanghai）。仍处规划阶段，没有安装 Claude Code、读取登录凭据、生成 token、运行判分或调用付费模型。

## 纠正结论

此前“官方本地判分只能使用 Anthropic 原生 API Key”的说法过于绝对。官方 `docs/judge.md` 确实写 API Key 必需，但固定提交 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 的实现还支持已登录 Claude Code 会话/OAuth fallback。源码与文档存在差异，应以已核对实现说明技术能力，不能只复述文档。

用户已确认：目前没有 Claude 付费订阅，只有免费 Claude 账号；可用 API 额度仍是 Gemini 免费/约 10 美元及 DeepSeek 约 25 元人民币。免费 Claude 账号不满足当前官方文档列出的订阅 OAuth token 条件。没有实测任何认证路径，不能宣称已具备完整本地判分能力。

## 已核对的实现

| 能力 | 实际证据 | 限制 |
| --- | --- | --- |
| API 凭据 | `ClaudeAgentRunner._ensure_authenticated`（494 行起）优先检查 `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` | 配置存在不等于凭据有效、余额或模型可用 |
| Claude Code 登录/OAuth | 无上述凭据时执行 `claude auth status`；`_subprocess_env`（674 行起）保留相应登录路径 | 仍需合法可用的 Claude 权限、比赛指定模型及运行参数，不能等同于免费网页登录 |
| 容器 token 传递 | `docker_env.py::FORWARDED_ENV_KEYS` 与 `modal_env.py::SERVER_ENV_FORWARD_KEYS` 都包含 `CLAUDE_CODE_OAUTH_TOKEN` | 不代表本机已配置；token 不应输出或提交。Antigravity 的 Claude 选项不能代替 Claude Code 登录权限 |
| 第三方代理地址 | `_subprocess_env` 清除 `ANTHROPIC_BASE_URL`，使 Agent 的代理地址不影响 judge | 不能只改这个变量就让原版 judge 使用中转平台；不自动等于其余所有云路径都不可能 |
| 判分模型覆盖 | `CHI_BENCH_JUDGE_MODEL` 传入 `ClaudeAgentRunner`，实际仍启动 `claude` CLI | 仅换成 Gemini/DeepSeek 的模型名不会自动切换 provider；改判分模型偏离官方口径 |
| 部分确定性检查 | `task_runtime.collect_all_verifier_checks`（956 行起）在阶段校验分支支持 `include_semantic_judge=False`，返回阶段/兼容检查后跳过 workspace judge | 是函数级入口，不是已验证的 CLI 开关；适用任务、输入准备与运行器集成待验证。只得到部分检查，不能报告完整官方 reward |

“确定性检查”指普通程序依据状态、字段或产物判断条件，不调用评审 LLM。“语义评审”则让模型判断规则依据和推理等内容。跳过后者会留下完整评分缺口。

## 可选方案与当前建议

1. **Claude Code 订阅 OAuth**：源码已有路径，理论上可沿用原版 Claude judge；需相应订阅、指定模型权限、容器认证和实际运行验证。当前用户仅有免费账号，不是现成可用方案，不建议据此立即购买订阅。
2. **其他渠道提供的 Claude**：Claude Code 官方支持云平台等多种认证，但不能据此断言 CHI 固定版本已经支持对应环境和模型映射。需检查原版配置、指定模型供应与实际结果；现有 Gemini 额度不自动代表可以支付云平台 Claude。当前不作为已就绪方案。
3. **确定性检查加工程自检**：优先考察官方上述函数级分支，独立于 Agent 运行，保持评测资料与 Agent 输入隔离。报告具体检查结果及未评审项，完整官方 reward 为 null。实际入口仍待实现验证。
4. **Gemini/DeepSeek 辅助评审**：可另设计开发评审器，对公开任务要求、允许提供的运行产物与轨迹给出诊断；需要额外适配并消耗现有额度。与官方判分分开，不生成冒充原版的 scorecard、reward 或 pass@1，也不能把隐藏评分资料送给参赛 Agent。
5. **最终私有评测交主办方**：继续沿用用户已选路线；本地仍验证工程和可复现性，正式提交时准确披露已有结果及限制。

用户已确认采用：先接入确定性检查，再按需要增加 Gemini 辅助评审，完整官方评分交给主办方。确定性检查的适用范围/集成与辅助评审的具体规格、模型、费用上限仍待验证和细化；没有授权立即编码或发起付费运行，也未改变官方最终模型/票数要求。判分侧 OAuth 路径不自动解决患者/P2P 模拟器的所有凭据依赖，它们需分别验证。

## 来源

- [官方判分文档](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/docs/judge.md)。
- [认证与地址处理实现](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/verifier/judge/claude_runner.py#L494)。
- [Docker 环境变量传递](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/docker_env.py#L40)、[Modal 环境变量传递](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/experiment/modal_env.py#L111)。
- [确定性检查分支与 judge 构建](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/verifier/task_runtime.py#L956)。
- [Claude Code 官方认证说明](https://code.claude.com/docs/en/authentication)：支持订阅登录及其他认证；`claude setup-token` 的订阅 token 要求 Pro、Max、Team 或 Enterprise 等适用计划。未在本机执行这些命令。
