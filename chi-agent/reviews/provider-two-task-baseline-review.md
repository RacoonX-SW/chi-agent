# 两个新 PA provider 任务的固定条件基线

执行日期：2026-10-27 至 28（Asia/Shanghai）。基线 `dee5ae0f3616a57c529acb706fe4c829fa16074c`，PR #16 已经 GitHub 与本地 fetch 核对合并；新分支 `codex/two-task-baseline`。一个 GPT-6.1 Terra / high 负责实现及 Docker 自测，主代理负责冻结规格、独立审核、实际运行、教学和 GitHub。两题基线验证完成，实际业务与执行结果见下文，不将阶段完成写成两题全成功。

## 任务冻结与可比条件

固定官方源码 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，数据 revision `5ce88104df2a91e057619eb70fb51f56fc5949eb`。固定官方 task_index 通过 Docker SDK 再取后与已有本地字节完全一致，SHA-256 `598411de37f088edc4d1e2a2ddfa0ddf12a76c795cc0b8cecaa33872bc1dea5e`。[固定公开索引](https://huggingface.co/datasets/actava/chi-bench/blob/5ce88104df2a91e057619eb70fb51f56fc5949eb/task_index.md)。

先按公开 instruction 情境提出候选，仅投影必要的契约兼容元数据。t008/t031、t015/t024、t026 均被当前官方 `_is_pa_um_judge_eligible()` 的非 submit 路径门禁排除，不放宽门禁。最终冻结 t013 与 t019，之后不因结果更换；两题在此前真实 claims 中均未出现，也未用于改业务策略。此前 t008/t031 只读材料不作为开发/试跑证据。

| 固定 task_id | 公开输入情境 | 契约与预检 |
| --- | --- | --- |
| `pa_t013_t013_o002_p01_new_referral_provider` | 腰椎神经根病、功能下降与康复评估 | provider / contract_v5 / eligible；原始目标 chart 可构建 |
| `pa_t019_t019_o001_p01_new_referral_provider` | PAP 不耐受的睡眠呼吸暂停、进一步手术评估 | provider / contract_v5 / eligible；原始目标 chart 可构建 |

包括兼容筛选共获取固定索引及七个候选各五个必要文件，合计 36 文件 / 132,807 bytes；不获取整个数据集、tests 或 solution。最终运行只使用冻结两题。原始资源、指纹清单与排除记录留在忽略的 `data/provider-baseline/<revision>/`；实现只绑定最终两题的固定文件元数据。虚拟空 export 的 adapter 预检得到两题分别 4 / 8 rubric、16 / 19 workspace 文件，非真实任务或判分。冻结证据见 `runs/provider-two-task-root/selection.json`。

participant 统一使用现有 DeepSeek Flash thinking/high、Chat Completions、30 轮、每轮 8192 输出上限，B 维持独立小轮数工具闭环；系统提示与工具许可不按题改变。reviewer 统一使用既有独立配置和原版 PA prompt，32768 输出上限、360 秒总截止。原 prompt 版本 `2026-04-28-pa-provider-v3`、SHA-256 `42db1f985695b877c77c36607efe6459bb7a26590233d9058f37015b8f49dbe2`；内联补充协议延续 L。两种角色配置各自固定，不把 reviewer 的预算用于 participant。

2026-10-27 再次核对 [DeepSeek 官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)，与现有 profile 一致；估算仍使用 CNY 输入 2/百万、输出 8/百万的高峰未命中上界，不根据缓存和时段折扣扩大运行。费用不是账单。

## 环境与资源边界

复用 Linux arm64 / Python 3.12.15 的现有镜像：dev `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，controller `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，world `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`。复用 H 模型卷 `chi-h-root-model-deps-20261027-v1` 和 K PDF 卷 `chi-k-pdf-deps-20261027-v1`，未安装或重建，锁未改。环境证据见 `runs/provider-two-task-root/environment.json`。

原 world 镜像只内置 t018；新题必要 task 目录仅只读挂到该 world 的官方 tasks 路径，沿用原 entrypoint 和已固定共享世界。participant 不挂新 fixtures、完整 data 或开发评审输入，只有公开 instruction/reference、既有授权 handbook 和受限业务 workspace。主代理仅检查已有 `.env` / Key 的存在性，没有输出秘密。

筛选时一次 Docker stdin 未加 `-i`，进程没有执行 Python、下载或模型调用；随后修正。一次只读 world 检查误用 dev 的解释器路径，退出 127；核对后按 world 实际 `/workspace/.venv/bin/python` 接续。一次 controller adapter 预检因缺 pydantic 退出，在已有 dev + SDK/PDF 只读卷内完成；没有安装依赖。以上是资源核对错误，不是 C 尝试或业务失败。

## 实现候选与独立审核

固定候选 `c4716a06f0e27cedaf8f4fbf4a85ed9c4713b877`。Terra 停止写入后，主代理从 Git archive 导出只读源码，挂固定 vendor/data 和既有依赖卷，以禁网、无凭据、无 Docker socket 的 Python 3.12 dev 容器独立检查。完整回归 291 tests / 143 subtests 通过；另有 21 项独立资源/捕获/评审故障检查及 5 项完整模拟生命周期通过。实际运行前逐项核对 participant 文件 hash 与候选完全相同。

交付复查发现新增资源单测依赖忽略的本地 task 文件：空 data 挂载下复现 1 failed / 2 passed（`without-task-data.log`）。这违反合成离线测试应独立于任务下载的要求，交同一 Terra 仅修测试夹具，以自造 revision/world/task/内容/hash/manifest 替代真实数据。固定测试修复候选 `f28ea578760f1134afe3a44603d856a94f0e2b8c` 后，主代理从新只读 Git 快照、空 data 与空 runs 的禁网 Docker 独立复验，291 tests / 143 subtests 通过，证据 `evidence/candidate-2/pytest-empty-data.log`。生产 scripts/profile/锁与 `c4716a0` 逐字一致，保留已验证的 26 项生产故障范围和真实 B/C 身份，没有重做付费试跑。

新增 `provider_task_resources.py` 只绑定两题的固定文件元数据及共用 world hash；K 源码身份包含该模块。显式 task-id 贯通 controller、官方环境/只读 task 挂载、worker/claim/journal、capture 与 reviewer。B 继续绑定源码/SDK/profile，保留历史 receipt 的旧 task 字段语义。新增 paid review 持共享 controller 锁，并核对已知账目、逐请求 settled、终态资源和跨文件身份；失败终态可诊断但保留 attempt_status。

独立故障范围包括：真实固定资源验证、改写 instruction 在读 Key/账目前阻断、FIFO/祖先链接/多余 task 文件、错题 expectations 和共享 world、两个新任务的完整 capture 与失败诊断、错题 claim、unknown request、非静止 runner、controller 忙。完整模拟通过实际 SDK/固定官方循环和 mock HTTP/MCP/Docker，分别覆盖两题的任务传播/挂载、非零退出、wait 异常及停止失败；检查停止→确认→capture→删除的顺序，无法确认停止时不得 ready。独立生命周期首次假 Docker 缺少 api.timeout，使等待异常案例不能走到 stop；补齐测试夹具后 5/5，生产候选未改。

证据：`runs/provider-two-task-root/evidence/candidate-1/{pytest.log,independent.json,lifecycle.json,lifecycle-2.json}`，主代理脚本为同根 `check_independent.py` / `check_lifecycle.py`。实验身份见 `experiment.json`；统一 participant system prompt SHA-256 `f6db1a146efe771b73a2415948b725570b374833724b584d8d8e12f9d3ac7084`。没有重做已通过 G/H 的安装/打包，也没有更换模型、锁或镜像。

复验命令采用 L 报告相同只读快照方式，替换快照为 `runs/provider-two-task-root/candidate-1/chi-agent`，PYTHONPATH 加 `/workspace/scripts`，输出为 `runs/provider-two-task-root/evidence/candidate-1`：`/opt/venv/bin/python -m pytest -q -p no:cacheprovider tests`；两份独立脚本在同一禁网环境执行。源码快照不含凭据和真实 runs，故障材料均为本地合成或固定资源指纹检查。Terra 首次自测因 runs 挂为只读而有四个测试不能建临时目录，改用独立可写 runs 后通过；不算生产故障或真实尝试。

## 全部真实尝试、终态与评审

全部使用已独立通过的 `c4716a0` participant 身份：显式 rebind 接续旧账，再做一次新 B，随后 t013 C/评审、t019 C/评审。未改变两题之间的源码、profile、系统/评审提示、工具许可或执行上限；没有人工代选业务动作。每题仅一个 C 和一个 review，失败后没有重跑或增加轮数。

下表列出本轮**全部五次真实运行/评审**。模型用量为 provider 回报；CNY 为峰值保守估算，非实际账单。

| run / review ID | 结果 | 模型请求 | 工具返回/调用 | input / output tokens | 耗时秒 | 估算 CNY |
| --- | --- | --- | --- | --- | --- | --- |
| `m-b-20261027-001` | smoke_completed；lookup→transform 有依赖工具闭环 | 4 | 3/3 | 6,683 / 205 | 4.618 | 0.015006 |
| `m-c-t013-20261027-001` | completed_ungraded，权威捕获 ready | 30 | 56/56 | 7,209,546 / 21,484 | 157.524 | 14.590964 |
| `m-review-t013-20261027-001` | complete；目标案件逐项 4/4 通过 | 1 | 无工具 | 52,713 / 2,696 | 14.243 | 0.126994 |
| `m-c-t019-20261028-001` | **runner_failed / incomplete**；MaxTurnsExceeded，捕获 ready | 30 | 56/56 | 6,730,221 / 35,941 | 261.007 | 13.747970 |
| `m-review-t019-20261028-001` | complete；保留 attempt_status=runner_failed，目标案件逐项 8/8 通过 | 1 | 无工具 | 61,693 / 6,268 | 28.487 | 0.173530 |

共 66 个已计量请求、14,060,856 input / 66,594 output tokens、115 次工具调用。新增估算 **28.654464 CNY**，其中两笔 review 合计 0.300524。review 的 cache hit 均为 1,920，miss 分别为 50,793 / 59,773；估算没有扣减缓存折扣。未登录控制台核对实际扣费，也不把累计估算当余额消耗。

耗时口径：B 为 instruction 文件写入至 controller 清理完成；C 为 claim 持久化至清理完成，均不含之前预检。review 为独立目录创建至结果写入，以 Docker GNU stat 可读的文件系统 birthtime 与结果 mtime 计算，不含 workspace 构建。最初汇总曾误用会在终态更新的 claim mtime，发现负值后依据目录 birthtime 更正；原评审未重跑。它们不是包含开发、下载和人工审核的端到端时长。

工具分类（“返回”只表示有确定返回，不据此断言业务选择正确）：

| 工具 | t013 次数 | t019 次数 |
| --- | --- | --- |
| local-fs-list / local-fs-read | 11 / 16 | 9 / 10 |
| local-sleep / local-claim_done | 1 / 1 | 2 / 0 |
| chart.search_patients / get_patient_chart_by_patient / list_candidate_orders | 1 / 5 / 1 | 1 / 7 / 0 |
| cases.create_from_order / get_case / list_cases | 1 / 2 / 1 | 2 / 1 / 2 |
| docs.create_submission_bundle / list_case_documents / upload_evidence | 2 / 1 / 1 | 2 / 2 / 2 |
| forms.list_required_forms / save_form_response / validate_form | 1 / 1 / 1 | 1 / 2 / 2 |
| auth.check_status / submit_authorization / finalize_provider_determination | 2 / 1 / 1 | 4 / 2 / 0 |
| inbox.list_messages / people.list_ordering_providers | 4 / 1 | 4 / 1 |

B 的三个工具为 smoke_lookup、smoke_transform、local-claim_done 各一次。两题均无 transport/dispatch 未返回项，所有 provider 请求已结算；模型自行重复业务查询/提交和自动网络重试是不同现象，本轮网络/SDK 重试仍为零。

### t013：完成目标流程，局部检查通过

完整终态为一个目标患者案件 submitted、一个付款方 intake in_progress，无付款方最终 determination。原版确定性部分检查 9/9 为 true；DeepSeek 的 2 个 evidence 与 2 个 submission rubric 全部返回严格 bool 和有效引用。真实 workspace 为 16 文件 / 164,816 bytes，capture manifest SHA-256 `47b6ea8d11741f79e016d3158f13dacfd2ccedebbd3506075af9307665318c29`。不把 submitted 或本地 verdict 写成付款方批准/官方通过。

### t019：轮数耗尽，且存在错患者的真实副作用

runner 日志明确为 `MaxTurnsExceeded: Max turns (30) exceeded`，controller 为 runner_nonzero_exit；run journal 保留 official_runner_failed / incomplete。world、runner、network 均清理，30 个请求已结算，完整捕获 ready，故可以对失败终态进行诊断，而不是补造成功结果。

终态中有两名不同患者的两个案件和两份 service_request，均已提交、intake 均在处理。第一笔属于**非目标患者**，第二笔才属于目标患者；独立对照 export.target_patient_id 与两个 cases/service_requests 的 patient_id，得到 false / true。轨迹记录第一轮建案在观察轮次 12、提交在 18；随后查询/等待，再于 26 为另一患者建案、30 提交，未产生正常 claim_done。这里没有推断模型内在原因；可核验的事实是错患者副作用已经发生，后来正确目标案件没有撤销它。

原版确定性部分检查仍为 9/9 true，DeepSeek 对目标案件的 6 个 evidence 与 2 个 submission rubric 为 8/8 true。固定 `PaUmJudgeAdapter.build()` 通过 `resolved_target_case_id()` 选择目标案件，并按它构建 agent_outputs 和过滤 audit_logs；主代理独立确认解析的是目标患者案件。**这些局部检查没有否决另一患者已提交的副作用，因此不能称本次完整任务成功。** 真实 workspace 为 19 文件 / 181,765 bytes，capture manifest SHA-256 `c4efc1a7c40a688b8fd0aa0524ee290f07fb89e707fe1467243855aca1f8e8a4`。

独立诊断证据在 `terminal-diagnostics-t019.json`、`patient-binding-t019.json` 和 `review-scope.json`；只向报告导出数量/状态和匹配布尔值，患者/病例原文与评审全文不上传。

### 历史、费用和资源独立对账

主代理重新计算旧 21,679 个文件指纹，除了允许变动的 K accounting/controller/B-success 与 review accounting 四个累计/指针文件，其余旧证据完全不变；旧 B receipt 在 b-receipts 中保持原字节。adoption、source transitions、旧成功/失败尝试和 claim 均保留，未清零。

K 的 139 个请求全部 settled，加 J prior 的 3 个及 review 的 4 个为累计 146 个已计量请求。逐请求 tokens/cost、旧 prior 和 review settlement 与累计账目一致；包含全部历史的峰值估算为 **47.756786 CNY**。两套 pending=null、controller clean。按精确 ID 通过 Docker API 再核对本轮三个 runner、两个 world、两个 network 均不存在，未按名字猜测删除其他资源。证据为 `final-reconciliation.json`。

安全元数据在 `runs/provider-two-task-root/{actual-summary.json,b-001.json,c-t013-001.json,c-t019-001.json,deterministic-t013-001.json,deterministic-t019-001.json,review-t013-001.json,review-t019-001.json}`；原始运行、终态、评审及结算仍在既有忽略目录。实际命令复用 README 的 Docker 函数：

```sh
chi_live_control rebind-source --reason 'M independently reviewed c4716a0 two frozen PA provider tasks; preserve prior history'
chi_live_control k-b-smoke --run-id m-b-20261027-001
chi_live_control c-run --run-id m-c-t013-20261027-001 --task-id pa_t013_t013_o002_p01_new_referral_provider
chi_development_review deterministic --input-dir runs/development-review-inputs/m-c-t013-20261027-001
chi_development_review review --input-dir runs/development-review-inputs/m-c-t013-20261027-001 --review-id m-review-t013-20261027-001
chi_live_control c-run --run-id m-c-t019-20261028-001 --task-id pa_t019_t019_o001_p01_new_referral_provider
chi_development_review deterministic --input-dir runs/development-review-inputs/m-c-t019-20261028-001
chi_development_review review --input-dir runs/development-review-inputs/m-c-t019-20261028-001 --review-id m-review-t019-20261028-001
```

## 证据解释与下一项通用改进

本轮先固定实验，再用真实新任务发现问题，结果没有支持“两题全通过”或跨任务稳定能力。工程层面，新任务挂载/运行/捕获/结算/清理已验证；t019 的直接退出原因是轮数上限，不是认证、Docker 或未知用量故障。业务层面，错患者创建和提交是独立的决策/身份控制问题，不能由增加轮数解释或修正；目前不据此推断临床方案本身错误。评审层面，目标案件局部 verdict 与全世界副作用有范围差异，主代理也未独立作临床/规则裁决。

**下一项优先改进：公开证据驱动的患者身份绑定门禁。** 在首次写业务状态前，将公开任务描述的关键区分事实、候选患者和 chart 证据绑定；仅靠同诊断或第一条搜索结果不能直接进入建单/建案。模型负责基于公开材料给出可追溯的选择，程序检查身份字段完整、证据引用存在，以及后续 order/case/form/submission 一直属于已绑定患者；冲突时回到只读核对，不允许顺手处理第二名患者。它不能读取 expectations/target_patient_id，也不能硬编码本轮患者或答案。首次选择是否正确仍须通过新的多候选场景验证，单纯“锁住第一次选择”不足以解决问题。

验证方案：先用两个相同诊断但关键经历不同的合成患者测试歧义处理，注入跨患者 order/case/submission，要求在副作用之前拒绝；保留正常同患者路径。独立审核新候选后做必要 B，在同样模型/提示/资源/30 轮条件下对两题做开发回归，比较完整 world 中非目标患者写入数、正常结束、目标结果、调用/耗时/费用，完整保留新旧尝试。不能以再次得到局部 rubric 全 true 作为唯一验收；之后还需未用于调参的新兼容任务验证迁移。该改进本轮仅提出，未实现、未追加付费回归或宣称有效。

次级观察是历史增长：t013 首/末请求 input 为 10,424 / 346,786，t019 为 10,433 / 388,046，最大请求分别约 1.164 / 1.367 MB；t013 inbox 查询有三次相同参数/结果、auth 状态有两次。支持以后研究有界上下文和重复查询，但不证明压缩已有效，也不把不同任务费用差异当作因果对照。错误患者副作用的优先级高于成本优化。

official_reward 始终 null；Claude 原版判分、F.5 正式配送与最终冻结继续暂停。没有评测正式包、全任务、其他领域/架构、独立临床裁决或实际账单的新证据。最终候选为仅修测试的 `f28ea57`，真实 participant 的生产文件身份保留与 `c4716a0` 相同；后续文档/PR 提交不替代验收。
