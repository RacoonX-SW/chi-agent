# 真实运行一次性审批包（草案，未生效）

建立：2026-11-01。**这不是调用授权**。只有用户在对话中明确批准具体任务/候选/资源/用途/次数/停止条件后，才可启动真实 B/C。当前已执行 B 1 次 + provider C 1 次；provider round17 pending/unknown，已停止 payer/CM/Y，禁止自动重试/换账根。详见 [真实批次A记录](../../../reviews/real-external-batch-a-review.md)。

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

官方 Rules 已于 2026-11-01 读取：公开 75 题；公开结果/75题 audit packet 非必需；必交 Kaggle Writeup、私有可运行包、IEEE 两栏 ≤5 页报告，截止 11/15 23:59 UTC；报名/组队 11/7；结果为模拟患者、无真实 PHI；handbook 受限且不得再分发。Go 隐私/非编码用途按用户决定不再确认，但不写成官方许可。

## 2. 建议的最小批次 A：1 B + 3 C

| 用途 | 次数 | 条件 |
| --- | ---: | --- |
| 当前候选 coding-B | 1 | 6 请求/1024 输出；成功收据；不连接业务世界 |
| provider 基线 | 1 C | `pa_t032_t032_o002_p01_new_referral_provider`；新世界；一次尝试 |
| payer 基线 | 1 C | `pa_t011_t011_o003_p01_intake_payer`（或批准的等价 payer 题）；新世界；一次尝试 |
| CM 基线 | 1 C | `cm_afib_moderate_anxious_001`；开发 Go 患者模拟；新世界；一次尝试 |

每 C 沿用主+确认共享 50 请求、主输出 8192、确认最多 2 次/32768；不自动重试。`external` 隔离 evaluation，声明与本机旧账分离，不证明账户历史为零；若要求接续旧 Q，需另行批准 `local` 模式。

**资源条件**：

- provider t032：`runs/representative-role-baseline-root/resources/dataset/prior_auth_provider/tasks/pa_t032_t032_o002_p01_new_referral_provider` 与 `evidence/role-resources-provider.json` 已有完整 role manifest/world；t013 只有 data 任务文件、没有现成 role manifest/world，故首批用 t032；
- payer t011：`runs/representative-role-baseline-root/resources/dataset/prior_auth_um/tasks/pa_t011_t011_o003_p01_intake_payer` 已有 instruction/tool_reference/task/fixtures manifest；
- CM：`runs/representative-role-baseline-root/resources/dataset/care_management/tasks/cm_afib_moderate_anxious_001` 已有 instruction/task/fixtures manifest 与 shared world；
- 运行前只选公开 instruction/tool_reference/资源与 world；`fixtures/expectations.json`、tests、solution、judge 不进入 Agent 输入；实际资源 hash/世界镜像由 F7 manifest 与 delivery plan 冻结；
- 若某题资源/世界预检失败，只用通过的题或延期，不伪造 hash。

用户已确认：批次 A、Y 4C、允许清单内新 attempt；`external` 隔离仍待最后确认。

## 3. 批次 B：Y 去留（4 C，用户已批准）

两个已见 payer 开发题 × off/shadow，各一次；任务/模型/参数/资源/预算固定。只用于判断来源校验是否保留，不声称稳定收益；若题目/资源不满足，明确不做，保持默认关闭。

合计：**1 coding-B + 7 C**（A 3 + B 4）。C 的 provider 请求上界按 50 计算，项目请求总上界约 `6 + 7×60 = 426`；实际按公开任务和停止条件记录，不要求跑满。

## 4. 可选批次 C：F1–F6 机制对照（最多 12 C）

只对实际采用且可独立切换的机制做 off/on；不混算六项收益。当前无资源/时间时不排入首批。

## 5. 不包含

- Z5 九题未见集（需另一次冻结清单/批准）。
- 官方判分、Claude/付费临床评审、独立付费摘要。
- 自动重试、换模型、换账根、清理旧 pending/halt。
- 对外发布或提交。

## 6. 确认状态

- [x] 批次 A（1 B + 3 C）已批准。
- [x] payer/CM/provider 资源已在本地开发数据集中找到；运行前只选公开文件并冻结 hash，无需用户另行上传。
- [x] history mode：`external` 已确认。
- [x] 批次 B（Y 4 C）已批准。
- [x] 停止后允许在同一清单内换新 attempt（不自动重发原请求）。
- [x] 已生成 external 操作者配置：`runs/real-external/configs/{provider,payer,cm}.json`；状态根 `runs/real-external/state`。
- [x] Go Key 只读注入文件已就绪（仅 `OPENCODE_API_KEY`，0600）。
- [x] B `real-ext-b-002` 成功；provider t032 C `real-ext-provider-001` 17请求后 `chi_timeout`，round17 pending/unknown；清理与world quiescence确认。
- [ ] payer t011 / CM afib / Y 4C：**未运行**；等待 unknown 处置。
- [ ] 不自动重试、不换账根；需用户提供 round17 Console 记录或明确决定。
