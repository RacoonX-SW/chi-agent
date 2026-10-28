# 有界设计

## 固定协议与实验条件

- 新严格 profile：Go `https://opencode.ai/inference/go/openai/v1/chat/completions`，SDK base URL 为其 `/chat/completions` 之前的路径；模型 `deepseek-v4.1-flash`，凭据只取 `OPENCODE_API_KEY`。不允许任意 endpoint/model 覆盖或静默回退到 pay-as-you-go/native。
- 使用自身 `chi-agent` User-Agent，每个会话独立且会话内稳定的 `x-opencode-session`；TLS 校验、禁用代理环境、redirect 与所有自动重试。认证头和秘密不进入输出/错误/轨迹。
- 复用已有 Python 3.12 镜像、锁定 SDK 与工具循环。输出上限有界，thinking/high 的实际 wire 与 reasoning/tool history 按当前 SDK 验证；没有证据不声称与 native 快照完全一致。
- 上下文文档标称 1M，记作文档事实而非本轮实测；Go 正式 ID 不加 `[1m]`。DeepSeek 官方 Claude Code 示例的 `deepseek-flash[1m]` 不推广为通用 API 名称。不开百万 token 付费压力测试。
- 保留现有自主 C 的 50 次上限和反馈语义；本轮合成 coding 探针另设最多 6 次，不把旧患者专用提示复制为 coding 提示，也不让探针成为正式任务入口。

## 核算与持久化

新的 Go namespace 独立保存 profile/源码身份、请求 claim、每次 request/response 的安全证据、工具交换、耗时和 token 用量。新 namespace 表示项目开始记录 Go，并不证明账户此前消费为零。旧 J/K/review 的所有失败、pending、claim、人民币费用和 B 回执不变。

每次发送前先持久化 pending；已存在 pending、未知用量、身份不一致、重复 run-id 或持久化不明时拒绝后续调用。可信 usage 先结算，再判断模型/工具/最终答案是否有效；不能因业务验证失败丢掉已知费用。余额扣费 `usage.cost`、模型价目价值 `usage.opencode.list_cost`、套餐额度消耗 `usage.opencode.allowance` 分别以 USD 记录，订阅固定月费另列文档，不将它们相加或换算为 CNY。字段缺失不臆造 0。

只接受 Go/Go Plus 的预期账单来源；发现 balance/byok/其他来源或非零额外余额扣费，保存可信用量后终止，不能再次发送。客户端不能保证服务端 Extra Usage 设置；真实运行前核对用户侧设置，报告任何未核验项，不把客户端无 fallback 说成服务端绝不扣费。

## 本轮接口与授权边界

提供 provider 层的严格客户端/SDK model 接口，下一阶段可显式复用。当前公开 CLI 只允许 plan/preflight、离线合成和固定 coding smoke，不接受任意指令文件、任务 ID、MCP 世界或评审载荷。真实探针通过自己的新 attempt/锁，走与离线相同的 SDK/transport/journal，零自动重试；不读 `.env` 全文到日志。用户已明确本 Go 路径不受 DeepSeek 官方 API 的避峰时段限制，可全天安排已授权验证；只有显式改回官方 API 时才适用该窗口。程序不新增时钟门禁。

不为了绕过用途边界把医院任务伪装成代码、不冒充 OpenCode 客户端；临床模拟用途的服务支持、十一月隐私条款和正式启动参数在下一阶段重新核对。此次不迁移 native 开发 worker 的账本或 source receipt；正式入口接线须单独规格与身份验收。

## 验收场景

1. 实际 SDK 序列化发送固定 Go 路由、模型、UA、session、thinking/high 和有界输出；工具参数严格校验；两次依赖工具交换与最终回答形成可验证闭环。reasoning 仅在同模型/同 endpoint 回放，空内容历史不丢失。
2. 任意 route/model/header 篡改、外域/重定向、错误工具/重复 call ID、未完成工具历史、流式/非预期 wire 被拒绝；秘密不出现在文件或异常中。
3. 429/timeout/取消/缺失或非法 usage/持久化失败不自动重试，已发送请求保留 pending 并阻断后续 attempt；已知用量而模型/内容错误先结算后报错。
4. 成功/失败尝试均保留；重复 ID、并发 claim、旧 source/profile 或损坏状态不能清零重跑。Go USD 三项累计与旧 CNY 账目隔离。
5. 主代理在固定源码上独立审核并 Docker 禁网复验；Key 存在、数据来源及执行范围核对后，仅执行一次新 coding smoke。Go 无上述避峰时段要求。若提供方实际响应不满足协议，保留失败和未知，不盲重试或编造实测通过。

### 首次真实响应后的工程兼容补充

首次真实 smoke 三次请求和两次工具均已返回并结算，最后 `stop` 文字消息省略 `reasoning_content`，被本地过严验证误拒。工具调用阶段继续要求原 reasoning 严格回放；终止阶段允许该可选字段缺失/null，不伪造 reasoning，也不放宽工具历史。用本地已保存的三份真实响应禁网回放验证，正文仍不上传。

新增显式 `rebind-source --reason <说明>`：只在独占锁、pending=null、全部用量和账单已知、无 halt、历史逐请求汇总/身份/完整文件哈希校验通过时，允许登记新的 source identity；费用、tokens、旧 run/失败/claim 保持原值。归档原 accounting 字节及 hash，保留可验证的身份转换与历史 run 哈希，新源码不能自动把旧 run 改写为自己已跑。预检不自动接续，不删账本或更换根目录绕过身份。

完成该兼容修复的固定候选与独立离线复验后，允许一个新 run-id 做一次最终 coding smoke（仍最多 6 请求），用于核验真实新源码及升级后的账目连续性。这是针对已定位工程缺陷的显式开发尝试，不是自动重试；原失败及所有费用照常保留。若再有未知用量立即停下，不追加刷通过。

## 已核验的一手来源（2026-10-28）

- [Go 路由、客户端、套餐及隐私](https://opencode.ai/v2/docs/console/go/)
- [usage 字段与美元含义](https://opencode.ai/v2/docs/console/api/inference/)
- [OpenCode 的 V4.1 Flash 上下文元数据](https://opencode.ai/data/deepseek/deepseek-v4-1-flash)
- [DeepSeek 原生模型规格](https://api-docs.deepseek.com/quick_start/pricing/)
- [Claude Code 专用配置示例](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)

Go 当前 DeepSeek ZDR 约定仅标明有效至 2026-10-31，不能默认覆盖十一月；本轮小探针不验证长上下文可靠性、账户剩余额度或 CHI 业务能力。
