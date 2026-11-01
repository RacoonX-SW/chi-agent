# Z8 参赛材料骨架（草稿）

建立：2026-11-02。**只有结构与缺口，数值在运行后填入，绝不预填。**

依据：官方 Rules（75 公开题；必交 Kaggle Writeup + 私有可运行包 + IEEE 两栏 ≤5 页报告）；当前实现与证据见 `reviews/REVIEW_STATE.md` 与各阶段报告。

## 1. 必交清单

| 项 | 状态 | 备注 |
| --- | --- | --- |
| Kaggle Writeup | 未开始 | 结构见第 3 节 |
| 私有可运行包 | 已有内部 release（v4–v7 系列），最终包未冻结 | 需最终候选重建并记录 identity |
| IEEE 两栏 ≤5 页报告 | 未开始 | 结构见第 4 节 |
| 公开结果/audit packet | 非必需（已核对 Rules） | 不提供 |

## 2. 运行手册（交付物之一）

必须写清、且只用真实成立的事实：

- 精确模型与端点、推理设置（`deepseek-v4.1-flash`、thinking + high、`max_tokens` 8192/32768/1024）
- 包结构、依赖锁、PDF/模型依赖卷、vendor 来源
- 启动命令：`role_operator` → `role_runner` → `go_chi_entry`（外部 operator 为开发侧，参赛包不含）
- 凭据注入：仅 `OPENCODE_API_KEY`；模拟器/judge 凭据不进入 runner
- 资源获取条件：公开任务文件 + 共享 world（payer/provider/CM）
- 失败与恢复：`chi_timeout` / `chi_transport_error` / `chi_tool_batch_invalid` / `chi_output_truncated` 的语义与处置
- 支持架构：只在 Docker + Python 3.12 验证过
- 明确不支持的：E2E 双角色、marathon 25 案、官方患者模拟器、官方判分

## 3. Kaggle Writeup 结构

1. 问题与任务：三个角色、75 题构成、评分口径
2. 系统：进程/容器拓扑、MCP 工具面、状态与账目、guard/contract
3. 方法：F0–F7 各自解决什么问题；哪些被采用、哪些被否（F4 不做自动压缩；A/B 无差异）
4. 实验：真实运行清单与分母（成功/失败/未运行/unknown 分开）
5. 限制：期望边界、未支持家族、官方未评、费用/未知项
6. 复现入口：包、命令、资源、依赖
7. AI 协作角色：实现/复审/规划如何分工

## 4. 技术报告结构（IEEE 两栏 ≤5 页）

1. Abstract
2. Task and environment（CHI-Bench 三角色、公开/隐藏边界）
3. System design（调度、工具、状态、证据、失败语义）
4. Experimental setup（模型、预算、任务选择、分母）
5. Results（真实运行表：run / 状态 / 检查分布 / 费用；明确 n 与重复）
6. Failure analysis（超时、传输中断、工具批次、截断、期望边界）
7. Limitations and reproducibility
8. Conclusion

## 5. 证据表字段（运行后填）

`run_id | 角色 | 任务 | 候选/identity | 结果 | 请求数 | tokens | 费用 | 检查 true/false/NA | 失败码 | 备注`

## 6. 当前可直接引用的数字（截至 2026-11-02）

- payer t011：26/28（v6/v7 多次一致）
- payer t027：21/22（`md.signed_off` 未过，期望选择差异）
- payer t030：23/28（triage；off/on 相同）
- CM afib：14/14（CM-004）；CM-003 停在 outreach（患者未同意，合规）
- B 收据：B4–B10 均 complete
- 能力 A/B：t011 off(n=3, 2 完成) vs on(n=1) 无差异；t030 off/on 无差异

## 7. 写作时必须遵守

- 不把 partial 写成通过；不把未运行写成 0 分；不预填官方分数
- 不把自有 operator 的运行写成官方 Harbor Trial
- 不把开发患者模拟器写成官方模拟器兼容
- 每处数字可追溯到 `runs/real-external` 下的证据文件
