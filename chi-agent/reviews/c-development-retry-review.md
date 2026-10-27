# Terra 协作与多次 C 开发尝试审核

日期：2026-10-27。最终候选 `2b6058d76232eccaa968c19d761993e93c34e1fb` 独立离线验收通过；当前源码真实 B3 与新世界 C2 均已完成。C2 工具回读为 submitted / payer intake in_progress，官方 reward=null。保留先前失败及所有费用；不将程序结束或业务提交当作最终批准/官方评分。

## 授权、基线与协作

用户要求先将实现子代理改为 GPT-6.1 Terra、更新全部现行文档，再继续 C；明确允许多次尝试，API 费用不再以旧 5 元上限阻挡。参赛运行时仍为 DeepSeek，官方判分暂停，F.5 未冻结。主代理维护规格、文档、独立审核、教学、真实运行和 GitHub；一个 `gpt-6.1-terra` / `high` 实现子代理负责代码与 Docker 离线自测，不读取真实 Key 或发起 API。

GitHub 已核对 PR #14 merged=true，合并提交 `3cca5f89de205cb8b608d4bded345e426577461f`；fetch 后从此最新 origin/main 建 `codex/terra-c-development`，写入前干净。J 的真实 B 成功和唯一 C 启动失败保留其原身份，详细记录只见 [J 报告](real-b-c-ungraded-review.md)。

现行 AGENTS、协作、工作流、学习/新对话提示、README 与 OpenSpec 已先同步新模型和授权；工作流改为中性名称 `subagent-workflow.md`，全仓相对链接同步，D0 旧模板明确归档。历史实际 Luna 派发与旧费用限制不改写。已通过 OpenAI Docs 技能核对 [官方模型标识](https://learn.chatgpt.com/docs/models#choose-a-model-2)，本会话派发接口也提供此模型；实际派发及验收另记。

文档先提交后，实际派发 `/root/terra_c_development_impl`，显式 `model=gpt-6.1-terra`、`reasoning_effort=high`、精简上下文；已返回设计并进行实现。没有启用第二个实现者或递归子代理，也没有修改全局模型配置。

## 独立环境与历史前置核对

主代理复核 dev/controller/world 镜像 ID 与 J 相同，SDK 复用 `chi-h-root-model-deps-20261027-v1`，未安装/下载/重建。旧生产 accounting、B 回执、C claim、两个编排结果与 B journal/四份必需产物分别计算指纹，B 的五项回执哈希均匹配，旧状态 known、pending=null、失败 claim 保留。Key 只输出存在性布尔值。前置证据为忽略目录 `runs/c-development-root/predecessor-before.json`，后续导入/试跑后再按同一清单核对旧文件未变。

主代理用独立 controller 脚本 `runs/c-development-root/check_world_ready.py`，在固定官方镜像中验证 J 已修的 artifacts 父目录 bind。世界只连 internal 网络，无模型/judge Key，未创建 Agent runner、未查询病例或调用模型；官方 entrypoint 的初始化/MCP 启动探针完成，**8.852 秒到 ready，退出 0**，精确 world/network handles 均已删除。原始 stdout/result/container.log 在 `runs/c-development-root/world-readiness/` 与 `world-readiness.stdout.json`；这是模型前的官方启动验证，不是 C 任务或官方评分通过。

## 实现与独立审核

按 [K 设计](../openspec/changes/bootstrap-baseline/design.md#k多次-c-开发尝试与真实账目接续) 与任务场景验收。首候选 `3adc645a6184dbbfd29b1312b8ae9c0ccf7efa30` 停写后，主代理读取三文件差异及相关调用，Git archive 到 `runs/c-development-root/candidate-1/chi-agent`；固定源码只读、SDK/vendor 分挂，测试输出全新且与真实根分离，禁网、无 Key/socket。全量执行 `/opt/venv/bin/python -m pytest -q -p no:cacheprovider`，结果 **249 passed / 124 subtests，退出 0**；J 原七项和另两项独立故障回归均退出 0。

主代理为 K 新写 `check_k_faults.py`，复用旧 Case/Fake 的外部服务替身，自行设置状态、故障与预期，执行 `/opt/venv/bin/python /checks/check.py`。五项中两项通过：真实 guard 的合成 provider 用量累计超过旧 5 元仍成功，以及 controller wrapper 下两个不同世界/claim、相同 attempt 拒绝。其余三项失败，驱动退出 1，候选 **不验收**：

| 问题 | 独立复现 |
| --- | --- |
| R1：K 投影仍写旧根 | 使用真实 `_copy_projection` 与合成公开输入，在复制后停止；新根没有投影，旧 real-b-c 根被写入 K 投影。Mock 投影掩盖了路径路由缺口 |
| R2：接续来源未参与前置 | 合法 adopt/rebind 后删除 adoption.json，K B 仍发出三次合成请求并成功，缺失的费用来源没有被验证 |
| R3：启动前错误永久卡住调度 | 在读取 Key 时注入缺失错误，尚无 Docker/provider 资源，controller gate 却永久 active；修正后仍被 prior_cleanup_unverified 阻挡 |

证据为 `runs/c-development-root/evidence/candidate-1/pytest.log`、`old-faults.log`、`candidate-faults.json`、`old-extra.log`、`remaining-evidence.json`、`k-faults.log` 与 `k-faults.json`，原始内容不上传。三项已交同一 Terra 修复，另要求历史绑定/金额及 usage 冲突前置拒绝，未知资源与 pending 保持失败关闭，不为通过检查加入生产 bypass。

实现代理报告首次旧回归命令使用整项目只读挂载，包含不应带入自测的 `.env` 与旧 runs；代理称未读取它们。该运行不作为合格隔离证据；主代理要求保留命令/限制，改为可分发源白名单快照重测。主代理后续独立验收从固定 Git archive 导出，只读 SDK/vendor 分挂且使用新的测试输出，不挂凭据/生产账目。只读挂载不等于内容隔离，这项偏差不以测试通过掩盖。

### 修复候选与独立通过范围

同一 Terra 停写后，主代理读取差异并固定 `ddfc9778950d84c5a20984d4a5748decdf0890a7`。R1 的实际投影明确传入本次新 run 目录；R2 将 adoption、source transition 与已归档 B 回执哈希链绑定到状态，校验导入和迁移时的累计金额/用量下界，并在 controller、直接编排、worker 和请求 reserve 前验证；R3 在资源前失败写独立诊断，不提前设置 active，资源开始后才持久调度 gate，硬中断/未知清理仍阻挡。

主代理重新 Git archive 到 `candidate-2/chi-agent`，新建四份隔离输出，用与首审相同的禁网/只读源/分挂 SDK/vendor 条件复验。全项目 **252 passed / 124 subtests**；J 九项独立故障全部通过；K 驱动扩为八项，包括缺/改 adoption、prior 金额冲突、缺 transition 的请求前拒绝，**8/8 通过**；四个执行均退出 0。K 驱动只为新 `output_parent` 接口适配外部 Fake，实际投影复制检查仍调用生产函数。证据在 `runs/c-development-root/evidence/candidate-2/`，文件名沿首审；独立验收后代码停写，真实调用使用本 SHA 的实现身份。

该候选的离线实现验收通过，允许按用户新授权执行真实接续、B 与 C；不将 Mock 两次世界或超 5 元合成用量当成真实任务/费用。旧 J 入口、5 元策略、G/H 正式入口回归保留。

### R4 PDF 修复与独立依赖复现

固定 PDF 候选 `a15a6cc8aeaea7f3668f814d4b86dae2a27aa794` 新增有界读取器、独立 `requirements-pdf.lock` 与针对测试。使用固定官方 uv.lock 的 pypdf 6.20.1/wheel、sdist 哈希；主代理在新空卷 `chi-k-pdf-deps-20261027-v1` 执行 `uv pip install --target /pdf-deps --require-hashes -r /requirements-pdf.lock`，核对 Python 3.12.15、包版本及可导入，退出 0。原模型 SDK 卷/锁、基础镜像、vendor 未改；controller/runner 各只读挂 PDF 卷，K 身份绑定锁与实际包源码哈希。安装证据为 `actual/pdf-install.log`。

主代理读取路径校验与解析器差异，核对 PDF 的 8 MiB/100 页、解压工作量、提取 100 万字符/返回 10 万字符限制，禁外部 JBIG2；UTF-8 和行切片保留，非文本/坏/加密文件返回工具错误。读取器源码也绑定 J 身份，但 J 不强制 PDF 包。固定快照 `candidate-3/chi-agent` 的独立全量 **256 passed / 124 subtests**；旧 J 九项（不挂 PDF 卷）、K 八项、独立手工构造文本 PDF 经生产文件工具的十项均通过。原始证据在 `evidence/candidate-3/`；手工 PDF 不使用实现测试的 PDF Writer 构造方式，也不使用手册/病例内容。

### R5 SDK 空值历史兼容与最终独立验收

真实 B2 在第 3 次请求发送前被 `history_reasoning_missing` 拒绝（见后文）；没有保留原始 provider 响应内容，不能断言该次具体字段组合。Terra 用固定 SDK/官方循环与合成边界复现两个连续工具轮空字符串历史的同类丢字段：旧 helper 为多个空 reasoning/content 条目复用固定 ID，SDK 合并历史时会去重。修复为每条内部 item 唯一 ID，且只在相同 model/endpoint、明确允许回放、完整 call-id 批次对应时恢复原始空串；不将缺字段、null 或错误类型伪装成空串，也未放松 Guard。

Terra 留下修复及测试后因额度中断；最后自测日志有三项错误码预期失败，文件中已改正为原 Guard 的 `response_invalid`，没有一份已完成的最终自测通过日志。主代理未换模型，直接按已授权的审核职责固定候选 `2b6058d76232eccaa968c19d761993e93c34e1fb`，独立完成验收。

主代理自己的 18 项矩阵先在旧 PDF 候选运行，**14/18 通过、四项失败，退出 1**；在新固定快照 `candidate-4/chi-agent` 为 **18/18 通过，退出 0**，包括 16 种两工具轮 content null/空串与 reasoning 非空/空串组合逐 call-id 原样回放，以及缺失/错误类型的请求前拒绝。全量 **261 passed / 143 subtests**；旧 J 九项、K 八项、PDF 十项也全部通过，六个新快照执行均退出 0。原始命令沿前述 Docker 禁网、只读 Git archive、独立输出；证据在 `evidence/candidate-4/`，新增 `empty-history-matrix.json/.log`，旧对照矩阵在 `candidate-3`。读取器/SDK 修复均由 Terra 实现，主代理未代写生产代码；最后候选通过后停写，真实复验使用该身份。

## 真实接续、B 与 C

实际使用已通过的固定候选。主代理在 controller Docker 依次执行 `adopt-prior`、`rebind-source --reason reviewed_ddfc977_for_user_authorized_repeated_C`，均退出 0。独立只读核对新根 `runs/real-c-development/` 的 prior=**0.011664 CNY**、新增费用=0、旧 input/output 已保留、cap=null、pending=null，adoption 摘要匹配且有一次源码 transition，旧 B 未被复制成当前成功回执。按前置指纹清单复核全部旧文件原字节未变。证据为 `runs/c-development-root/actual/adopt-prior.stdout.json`、`rebind-ddfc977.stdout.json` 和 `after-adoption.json`。

随后 `k-b-smoke --run-id k-b-20261027-001` 实际退出 0，`smoke_completed`；三次请求均 settled，lookup/transform 分别在第 1/2 轮 dispatch 并返回，结果进入后续历史。provider 回报 **4,897 input / 172 output tokens**，本次按峰值价估算 **0.01117 CNY**；旧 prior 独立为 0.011664，累计估算 0.022834 CNY，并非账单。必需日志与当前 B 回执存在、runner 已删除、无清理错误、pending=null；当前回执只绑定本候选，不冒充 J 原回执。原 journal/日志留新生产根，脱敏编排 stdout 留 `actual/k-b-001.stdout.json`。

### 第一轮 C：进入业务执行后读取 PDF 失败

完成 B 后实际执行 `c-run --run-id k-c-20261027-001`，控制器退出 **1**、`runner_failed`。官方世界 **7.768 秒 ready**，runner 实际启动；模型自主查询患者/医嘱、读取规则并建立案件，最后读取两份授权手册 PDF 时，`local-fs-read` 按 UTF-8 解码抛出 UnicodeDecodeError，SDK 终止。主代理仅在运行结束后排错，以参数哈希匹配授权文件格式，确认两个未完成读取为 `.pdf`（60,577 / 56,877 bytes），未向实现代理提供病例内容或业务动作。

**R4：允许的文件格式能力缺口。** 文件路径本身在允许范围，但工具仅支持 UTF-8；当前任务流程需要读取 PDF 示例。拟用独立哈希锁与只读依赖卷补有界 PDF 文本提取，不开放 shell/Python、路径范围或评分资源；不改任务答案和官方源码。该次失败不重放原 attempt，修复独立验收后显式接续源码、重新取得 B，再创建新世界。

本次 **12 个真实请求均 settled**，provider journal 回报 **1,284,650 input / 10,742 output tokens**，峰值估算 **2.655236 CNY**；加旧 prior 和新 B 的累计估算为 **2.678070 CNY**，并非账单。34 项 dispatch 中最后两项文件读取无正常返回，其状态为 unknown；没有未知 provider 用量或 pending。SDK 错误路径的原始 `run_result.json` 显示 turns/usage=0，不能据此当作没有调用；journal 是逐请求的实际用量来源。SDK 错误路径只留下 run_result/run_log，未生成 run_output/trace，未补造缺失文件。

runner/world/network 均已按精确 handle 清理，world 日志捕获成功，无 cleanup/persistence 错误，controller gate 为 clean，失败 claim 与所有实际产物保留；official reward=null。脱敏编排 stdout 为 `runs/c-development-root/actual/k-c-001.stdout.json`，实际 journal/claim/workspace 留生产忽略目录。后续 C 仍由模型在新世界自主执行，不在运行中代选动作或修结果。

### PDF 候选 B2：历史字段转换失败

PDF 修复独立验收后，实际 `rebind-source --reason reviewed_a15a6cc_bounded_pdf_reader_after_C1` 退出 0，旧 B 回执归档，历史费用与 C1 失败保留。随后 `k-b-smoke --run-id k-b-20261027-002` 退出 1，`history_reasoning_missing`；**两个请求均 settled，3,185 input / 107 output tokens，估算 0.007226 CNY**。第 3 次请求在传输前被拒绝，没有新增 provider pending；runner 已清理、gate clean，累计估算 **2.685296 CNY**。错误路径仍只有原始 run_result/run_log，不补造 trace/output；该次没有启动 C。

完成 R5 后，实际 `rebind-source --reason reviewed_2b6058d_empty_history_conversion` 退出 0。随后 `k-b-smoke --run-id k-b-20261027-003` **退出 0、smoke_completed**：三次请求全部 settled，provider 回报 **4,932 input / 174 output tokens**，本次峰值估算 **0.011256 CNY**，累计估算 **2.696552 CNY**；回执/日志有效、runner 已删除、pending=null。各 stdout 在 `actual/rebind-a15a6cc.stdout.json`、`k-b-002.stdout.json`、`rebind-2b6058d.stdout.json`、`k-b-003.stdout.json`。

### 第二轮 C：自主流程完成，官方业务状态已提交

实际执行 `c-run --run-id k-c-20261027-002`，**控制器与 runner 退出 0，completed_ungraded**。使用当前固定候选、新官方世界与同版本 PDF addon；world **8.936 秒 ready**。从持久 claim 到清理后终态为 **168.062 秒**，这是该区间计时，不包含此前投影准备的端到端时长。

本次 **26 个真实请求均 settled，45 项工具 dispatch 均返回**，provider 回报 **4,019,646 input / 18,652 output tokens**，与 SDK 成功结果的 26 turns 相符；本次峰值估算 **8.188508 CNY**。实际读取一份允许的 PDF，返回 1,837 字符、没有工具错误。模型自主查询、保存表单、上传证据、组包、调用提交与状态回读，并通过完成工具结束；运行中没有人工代选动作或修改结果。

业务观察以实际 MCP 返回为依据：`auth.submit_authorization` 返回 case.status=`submitted`、intake.status=`in_progress`，后续 `auth.check_status` 和 `cases.get_case` 回读仍为 submitted / in_progress。未取得最终付款方批准，未运行 verifier/judge；模型结束语中的其他临床/规则正确性与“已验证”表述不据此背书，official reward 始终 null。原始任务、医疗事实、生成材料与最终全文仅留本地，不复制进本报告。

必需 `run_result.json`、`run_output.txt`、`trace.jsonl`、`run_log.txt` 均非空；runner/world/network 已按精确 handle 删除，日志捕获成功，cleanup/persistence 错误为 null。新旧 attempt claim 分别保留、controller gate clean、usage_complete=true、pending=null。stdout 为 `actual/k-c-002.stdout.json`，完整生产证据在 `runs/real-c-development/` 与 `runs/a-environment/k-c-20261027-002/`。

### 最终对账与证据完整性

主代理在禁网 Docker 独立逐 run 核对本轮五份 journal：新 B1、失败 C1、失败 B2、成功 B3、成功 C2，总共 **46 次 provider 请求**，每次均 settled。新费用估算合计 **10.873396 CNY**，原 J prior **0.011664 CNY**，累计 **10.885060 CNY**；包括原 J 用量的总计为 **5,322,286 input / 30,061 output tokens**。这些金额使用峰值未命中价，不是实测账单，也未扣缓存优惠。

当前 B 回执的五份产物哈希全部匹配；旧 J 指纹清单逐一完全不变。保留三次显式 source transition 和已归档 B 回执，失败/成功 C 各有独立 claim，不清零预算或重放同一 attempt。独立对账结果为 `actual/final-reconciliation.json`，原始内容不上传。

## 交付与限制

只上传可分发代码和脱敏报告，不上传 Key、手册、data/vendor、原始轨迹或受限产物。本轮完成协作模型切换、多次尝试/费用接续及一个自主无评分 C；业务提交已有工具证据，最终批准、官方评分、完整任务覆盖、正式包配送/F.5 冻结仍未完成。交付创建 base=main PR，由用户审核合并，主代理不合并或设置自动合并。
