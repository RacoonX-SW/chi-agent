# F0 任务家族—能力—支持矩阵（首版）

建立：2026-10-31。来源：`data/task_index.md`（公开索引）、`vendor/chi-bench/src/chi_bench/mcp/catalog.py`、`go_chi_mcp.CM_NAMES`、公开 `instruction.md`/`tool_reference.md` 与既有阶段报告。**未读取** `fixtures/expectations.json`、verifier、solution 或 tests。

状态词表见 [design](design.md#22-状态词表)。`partial` 不等于该家族已验收；没有当前候选证据的格子写 `unverified`。历史报告只证明其注明范围。

## 1. 跨角色前置能力

| 能力 | 当前基础 | 缺口 | 状态 |
| --- | --- | --- | --- |
| 角色/工具隔离 | `MCPBridge` 按官方 allowlist 选工具，未知/跨角色拒绝 | 新增本地工具需继续走同一 contract | supported_offline |
| 目标实体绑定 | provider 患者 roster + 近邻 + 确认（N/W） | payer/CM 的 case 目标尚无独立状态对象 | partial |
| 请求预算/账目 | 主+确认共享 50，B 6，零重试，pending 阻断 | 新能力改变工具集后需 rebind + 新 B | supported_offline（旧候选） |
| 业务状态/记忆 | 无；仅 journal 调用记录 | F1 | needs_implementation |
| 角色阶段指导 | 官方 `SYSTEM_PROMPT` + 工具描述 | F2 | needs_implementation |
| 规则/材料定位 | 整文件 `local-fs-read`、`local-fs-list`、PDF 提取 | F3 | needs_implementation |
| 完成核验 | `local-claim_done` 仅 `record_claim()` | F5；本变更只做 claim 门禁 | needs_implementation |
| 失败查证/停滞 | 工程失败/超时/取消/清理已有控制 | F6 业务未知与停滞 | needs_implementation |

## 2. Provider（`prior_auth_provider`，公开 25 题同一 stage）

| ID | 家族/触发 | 必要能力 | 主要工具 | 可观察完成证据 | 正常分支 | 失败/缺证分支 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PV-1 | 新转诊，公开材料足够选定服务 | F1/F2/F3/F5 | chart.get/search、cases.create_from_order、docs.*、forms.*、auth.submit_authorization | case 状态、submission bundle、表单校验、提交回执 | 选服务→建案→表单/证据→提交→回读 | 证据不足则不提交或补证；冲突则停止并说明 | partial（W 一次 provider 关单；非全家族） |
| PV-2 | 新转诊，材料缺失/需补证 | F1/F2/F3/F5/F6 | chart.*、docs.upload_evidence*、forms.validate_form、inbox.* | 缺项清单、补证记录、未提交原因 | 定位缺项→补证→再校验→提交或停止 | 无法补齐时如实未完成，不伪造材料 | needs_implementation |
| PV-3 | 收到 pend/补件通知 | F1/F2/F3/F5/F6 | inbox.list/read、auth.respond_to_pend、docs.* | pend 响应回执、更新后的 case 状态 | 读通知→核对缺项→响应→回读 | 错 case/超期/材料冲突时拒绝或升级 | needs_implementation |
| PV-4 | 拒绝后申诉 | F1/F2/F5/F6 | auth.file_appeal、auth.file_external_appeal、docs.* | 申诉受理/回执、状态回读 | 读决定→组织依据→申诉→回读 | 无新依据/时限不明时停止 | needs_implementation |
| PV-5 | P2P 请求/响应 | F1/F2/F5/F6 | auth.request_peer_to_peer、respond_to_peer_to_peer、p2p_session.* | 会话记录、summary、状态 | 请求/接受→准备要点→会话→summary→回读 | 对方未响应/信息不足时如实未完成 | needs_implementation |
| PV-6 | 提交后状态/最终处理 | F1/F5 | auth.check_status、auth.finalize_provider_determination、cases.get_case | 最新状态、最终处理回执 | 回读→确认→finalize | 状态未受理/未知时不重复提交 | partial（W provider 关单路径） |
| PV-7 | marathon 25 案连续会话 | F1/F2/F4/F5/F6 | 全部 provider 工具 | 每案独立状态与最终汇总 | 逐案计划→执行→回读→切换 | 单案失败不污染其他案 | unsupported（当前 entry 无 session harness） |

## 3. Payer（`prior_auth_um`，公开阶段）

| ID | 家族/触发 | 必要能力 | 主要工具 | 可观察完成证据 | 正常分支 | 失败/缺证分支 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| UM-1 | intake 新案入队 | F1/F2/F3/F5 | payer_intake_hub.*、list_documents、confirm_decisions | intake decisions、line items、确认回执 | 读队列→核文件→录 header/dx/provider/lines→确认→回读 | 文件缺失/冲突时补件或挂起，不臆造 | needs_implementation |
| UM-2 | triage 路由 | F1/F2/F3/F5/F6 | triage.get/calculate_sla/check_gold_card/set_disposition/route_case | disposition、SLA、路由结果 | 读案→算 SLA/资格→设 disposition→路由→回读 | SLA/资格不明时停止或补查 | needs_implementation |
| UM-3 | nurse review | F1/F2/F3/F5 | review.get_nurse_review_data/save_criteria_evaluation/submit_nurse_case_recommendation | 条件评估、建议、提交回执 | 读临床→逐条评估→保存→建议→回读 | 证据不足时建议补件/挂起，不硬套批准 | needs_implementation |
| UM-4 | MD review | F1/F2/F3/F5 | review.get_md_review_data/save_md_review/submit_md_case_decision | MD 决定、依据、提交回执 | 读 nurse 建议→独立核对→记录决定→回读 | 不要求所有案必经 MD；信息不足可退回 | needs_implementation |
| UM-5 | P2P | F1/F2/F5/F6 | p2p.list/offer_slots/schedule/record_outcome、p2p_session.* | 排期、会话、结果 | 读请求→排期→会话→记录→回读 | 未排上/未达成时保留实际结果 | needs_implementation |
| UM-6 | determination + letter | F1/F2/F3/F5/F6 | determination.get_summary/finalize、payer_letter_center.* | 最终决定、函件类型、投递/审计回执 | 汇总→选择合法结局→生成函件→审计→finalize/deliver→回读 | 批准/部分/拒绝/挂起均可合法；不得按旧 verdict 倒推 | partial（W payer 终态不符，原因未充分解释） |
| UM-7 | marathon 全阶段连续会话 | F1/F2/F4/F5/F6 | 全部 payer 工具 | 每案阶段状态与最终汇总 | 逐案/逐阶段计划→执行→回读 | 单案失败不污染其他案 | unsupported |

## 4. Care management（`care_management`）

| ID | 家族/触发 | 必要能力 | 主要工具 | 可观察完成证据 | 正常分支 | 失败/缺证分支 | 当前状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CM-1 | 入队/开案/退案 | F1/F2/F5 | cm_intake.list_referral_queue/get_referral/open_case/disenroll_case | 案件归属、开案/退案回执 | 读队列→核对→开案→回读 | 目标不明/重复开案时停止 | partial（W 开发模拟链路） |
| CM-2 | 病历核对 | F1/F2/F3/F5 | cm_chart.get_chart_data/submit_chart_review | 病历读取、review 提交 | 读病历→核对→提交 review | 信息缺失时记录缺口 | partial |
| CM-3 | 外呼/消息/记录 | F1/F2/F5/F6 | cm_outreach.start_outreach_call/send_message/get_transcript/end_outreach_call | 通话/消息记录、transcript、结束状态 | 联系→记录→读 transcript→结束 | 患者 STOP/无法联系时停止，不再外呼 | partial（开发模拟器；官方模拟器 official_dependency） |
| CM-4 | 评估 | F1/F2/F3/F5 | cm_assessment.start_assessment/save_section/complete_assessment | 分段保存、完成回执 | 开评估→逐段保存→完成→回读 | 缺资料时保留未完成 | partial |
| CM-5 | 照护计划/结案 | F1/F2/F3/F5 | cm_care_plan.create_draft/save_care_plan/finalize | 计划版本、finalize 回执 | 草拟→保存→finalize→回读 | finalize 失败/未知时不重复写 | partial |
| CM-6 | marathon 25 案 | F1/F2/F4/F5/F6 | 全部 CM 工具 | 每案独立状态与汇总 | 逐案计划→执行→回读 | 单案失败不污染其他案 | unsupported |
| CM-7 | 官方患者模拟器兼容 | 官方服务 | 官方模拟器 | 官方环境回执 | — | 无官方证据时不得声称已兼容 | official_dependency |

## 5. E2E / 其他

| 家族 | 现状 | 缺口 |
| --- | --- | --- |
| `prior_auth_e2e` 双 agent | 当前 entry 只启动单角色 | 需要双方编排、共享 case 身份与结果归并；未支持 |
| 公开全量 75 题 | 历史只运行有限开发题 | 需要 Z4/Z5 实验与规则确认；不得用 0 填充未运行 |

## 6. 本变更优先支持顺序

1. **PV-1/PV-2/PV-6**：provider 新转诊的“提交/不提交/回读”三态，是 F1/F2/F3/F5 的主闭环。
2. **UM-1/UM-2/UM-3/UM-6**：payer 的文件完整性、规则适用、条件评估和合法结局，验证 F2 分支与 F3 定位。
3. **CM-2/CM-3/CM-5**：病历、外呼 STOP、照护计划，验证状态来源与停止条件。
4. 其余家族保留 `needs_implementation`，不在本变更勾成完成。

## 7. 证据与限制

- 本矩阵是**支持范围声明**，不是新运行结果；`partial` 只继承历史报告的限定范围。
- 矩阵不包含期望答案、rubric 分数或按题策略；任务选择仍以公开索引和用户批准的实验清单为准。
- `official_dependency` 家族在取得官方环境证据前不得写 “已支持官方模拟器”。
