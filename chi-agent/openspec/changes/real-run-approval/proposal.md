# 真实运行一次性审批包（草案，未生效）

建立：2026-11-01。**这不是调用授权**。只有用户在对话中明确批准具体任务/候选/资源/用途/次数/停止条件后，才可启动真实 B/C。当前 0 次真实调用。

## 1. 绑定身份

| 项目 | 当前值 |
| --- | --- |
| 源码 | `dac60805a1b6beac85a1e38b1652cf46a78bd351` |
| release bundle SHA | `95302f2252b838b6bd272f1ba205272c47e208eb86ea80cfedfc2d2387c6f664` |
| 干净 preflight | `identity_verified`，`identity_sha256=d4651acbd5c987fd6c1098359cb8259d4f423dd8cb93bab5f413c97d65f32633` |
| 模型 | `deepseek-v4.1-flash`（OpenCode Go 路由） |
| 账目 | `record_only` / null cap；三项 USD 分列；旧 CNY 不混 |
| 停止 | 未知结果/token、pending/halt、跨患者写、清理未确认、资源身份不符、Key/额度异常 |

任何代码/release 变化都使上述身份失效，需要新 release、新的 coding-B 和新的资源 hash。

## 2. 建议的最小批次 A：1 B + 3 C

| 用途 | 次数 | 条件 |
| --- | ---: | --- |
| 当前候选 coding-B | 1 | 6 请求/1024 输出；成功收据；不连接业务世界 |
| provider 基线 | 1 C | `pa_t013_t013_o002_p01_new_referral_provider`；新世界；一次尝试 |
| payer 基线 | 1 C | `pa_t011_t011_o003_p01_intake_payer`（或批准的等价 payer 题）；新世界；一次尝试 |
| CM 基线 | 1 C | `cm_afib_moderate_anxious_001`；开发 Go 患者模拟；新世界；一次尝试 |

每 C 沿用主+确认共享 50 请求、主输出 8192、确认最多 2 次/32768；不自动重试。`external` 隔离 evaluation，声明与本机旧账分离，不证明账户历史为零；若要求接续旧 Q，需另行批准 `local` 模式。

**资源条件**：

- provider t013 的公开资源与 manifest 已在本地有固定副本；
- payer t011、CM 题的任务 instruction/工具参考/world/资源需要先供应并计算 manifest/hash；未供应则本批次缩减为 provider 或延期；
- 三题都必须使用公开输入/工具；fixture/expectations/verifier/judge 不进入 Agent 输入；
- 世界镜像、MCP 端点、handbook、工具参考、state/logs 在运行前由 delivery plan 检查。

## 3. 可选批次 B：Y 去留（4 C）

在批次 A 完成后，两个已见 payer 开发题 × off/shadow，各一次；任务/模型/参数/资源/预算固定。只用于判断来源校验是否保留，不声称稳定收益；若题目/资源不满足，明确不做，保持默认关闭。

## 4. 可选批次 C：F1–F6 机制对照（最多 12 C）

只对实际采用且可独立切换的机制做 off/on；不混算六项收益。当前无资源/时间时不排入首批。

## 5. 不包含

- Z5 九题未见集（需另一次冻结清单/批准）。
- 官方判分、Claude/付费临床评审、独立付费摘要。
- 自动重试、换模型、换账根、清理旧 pending/halt。
- 对外发布或提交。

## 6. 需要用户一次性确认

1. 是否批准批次 A（1 B + 3 C）？
2. payer/CM 资源是否由你提供；若不能，是否只跑 provider 或延期？
3. history mode：`external` 隔离（推荐，声明不证明旧账为零）还是 `local` 接续旧 Q？
4. 是否同时批准批次 B（Y 4 C），还是先看 A？
5. 停止后是否允许在同一批准清单内换新 attempt（不自动重发原请求）？

未确认前，我只继续离线材料/Z8；不启动真实调用。
