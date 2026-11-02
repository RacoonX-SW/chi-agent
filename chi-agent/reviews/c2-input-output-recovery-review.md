# C2 输入计量与输出截断恢复实施及独立审核

## 范围、基线与 P0 冻结（2026-11-02）

用户本轮授权 P0–P3 离线实现、Docker 自测、独立复审和 PR；主代理规格/审核/Git，唯一实现代理显式 Terra/high。自动摘要、C1/C3/C5、M2、真实模型/B/C/Trial/判分均不在范围。不读 Key，不访问真实账，不换账根解除阻断。

远端刷新后基线为 `5d11c40`（PR41 已合并）；PR40 `a4c84ed` 仍 open，不能写成已合并。隔离 worktree `~/.codex/worktrees/c2-input-output-recovery/Kaggle`、分支 `codex/c2-input-output-recovery` 从最新 main 建立；原目录 `codex/reliability-boundaries` 开始时干净，不修改其文件。PR40 的 output-recovery/input-context 作为用户指定规格来源；实现 PR 不依赖合并其分支。

已核对：Agents SDK 0.13.6、OpenAI 2.36.0、httpx 0.28.1，Docker Python 3.12.15。复用镜像 `chi-agent-a-control:latest` / `24bef2e2c7e3` 及已有只读 model/pdf 卷。首次未挂 model 卷的版本探针因缺 httpx 元数据失败；挂既有卷后核对成功，没有安装。旧 Guard length 测试单项通过：可信 usage 先结算，`chi_output_truncated` 停止。

调用链：run_chi → BudgetModel/OpenAIChatCompletionsModel.get_response → AsyncOpenAI → ChiGuard._validate/_handle_serialized → journal reserve/response/settle → _response → ToolContract.accept_batch → SDK Runner → MCP/local dispatch → record_result。严格 SDK 历史只包含已接受闭合批次。实际 wire 视图可包含程序生成的恢复片段，但不得放松 SDK 历史校验。不得重启 Runner 或持 billing_lock 嵌套请求。

计数位置已核对 guard used、journal reserve/replay/_validate、runtime feedback/max_turns、request_budget、inspect/reconciliation output 上限、usage_totals/summary、auxiliary patient 独立计数。main/confirmation/continuation 共享50；continuation 每链1/run2，患者保持独立。单次 main/continuation8192、confirmation32768、coding1024、patient8192 不变。时间沿原 run_started/admission/IO policy，不改模型/effort。

### 冻结接口与安全规则

- 策略/恢复视图 `chi-output-recovery-v1` / `chi-recovery-view-v1`；内部用途 `continuation`。开关默认关闭，显式绑定 run.launch 的 `output_recovery`（值为 policy version）；旧记录不补字段，新字段精确校验。
- 输入计量 `chi-context-v2`、方法 `utf8_bytes_upper_estimate_not_tokenizer`：完整最终 JSON（含结构、reasoning、tool 参数、中文）计数；实际 raw wire 字节单列，分项字符仅为组成，不相加重复。完整 UTF-8 JSON 字节数作为保守 token 估算，不宣称真实 tokenizer。输出预留按本次实际 max_tokens/purpose，确认不能沿用8192。容量仍配置未实测；坏配置、坏 metric/未知容量、超限零发送。旧 v1 证据保留旧语义。
- 恢复记录至少精确包含 schema/policy、identity/evaluation/task/attempt/run、root_round/parent_round/parent_response_sha256、mode、chain_ordinal=1、history_version/history_sha256、instruction_version、view_sha256、continuation_round（允许未发送 null）、decision/result；版本化校验字段/类型/关联，不忽略未知字段。许可先持久消耗，再 reserve；重启不自动续发；可用 journal 内的严格新字段或独立不可覆盖记录实现同一事务契约。
- 模式 `partial` 固定指令 v1：`The previous response was interrupted by the output length limit. Continue the original task. Only accepted tool history establishes executed facts. If finishing, provide a complete standalone final answer. Do not treat the unfinished fragment as a completed action.`
- 模式 `regenerate` 固定指令 v1：`The previous response was interrupted by the output length limit. Its entire tool batch was not executed. Generate a complete next response from the accepted history. Do not replay completed actions recorded there.`
- partial 只精确保留同一原响应的 content/reasoning；regenerate 不携带任何残缺工具调用/参数，不拼接、不造 tool result。坏容器/不支持字段是 response_invalid，不借恢复掩盖。恢复后工具批次仍过全部原门禁。
- 工具恢复分类必须显式 canonical 名称表（local/MCP，按固定 catalog 逐项登记），不直接套 go_chi_state.effect_for 的动词启发式。未知分类拒绝恢复派发；inbox.list_messages 等有读取副作用者按 mutation。对已完成 mutation 用 canonical 名称+canonical JSON 参数指纹拒绝恢复直接重放，任何含拒绝调用的新批次零执行；不声称识别语义等价但参数不同的操作。
- 安全错误沿原 fatal 分类；新增有限码：`chi_recovery_invalid`、`chi_recovery_limit`、`chi_recovery_history_changed`、`chi_recovery_replay`、`chi_recovery_tool_unclassified`、`chi_recovery_persistence_failed`。默认关闭/第二次length继续 `chi_output_truncated`。不清 fatal，不恢复 unknown/cancel/network/persistence。对外不含正文/reasoning/原异常。

P0 后实现者可以在上述语义内选择最小接缝和记录布局；字段调整须先报主代理，由主代理依据证据更新本节，无需用户逐项确认。输入自动摘要仍为后续独立包。

## 实现、自测与独立复验

**实现候选 `bd1b9f5b322e6a47d2087f6fef5ebe8006208381` 在本轮 C2 限定离线范围独立通过。** 后续文档提交不改变该实现身份；用户最终验收/合并另行决定。原始命令、失败和日志集中在本轮忽略目录；作者自测与主代理独立执行分列。

唯一实现子代理实际派发为 `gpt-6.1-terra` / `high`、`fork_turns=none`，没有替换模型或增加实现者。代理最初不能可靠完成P2并停写；主代理进一步冻结schema→许可证据→一次性reserve→Guard→runtime/SDK的小步骤，仍由同一个Terra实现。原目录保持 `codex/reliability-boundaries` / `7984b60` 且干净，未覆盖、暂存或清理其修改。

交付前再次fetch：origin/main仍为 `5d11c40`；PR40仍open/merged=false，未合并或关闭。实现PR独立以main为基线并包含所需输出契约；PR40有文档重叠，不能称依赖已合并。

### 实际布局与P0补充冻结

1. 计量使用 `chi-context-v2` / `chi-context-budget-v2`：total_chars为完整canonical JSON字符，分项仅作组成说明；estimated_tokens取完整UTF-8 JSON字节与实际raw字节较大值。它不是tokenizer，容量仍configured_unverified。有效输出预留取配置基础与本次max_tokens较大值。显式旧v1 metric/budget组合保留旧算法，旧文件不迁移；未知budget不能免检。
2. 默认无 `launch.output_recovery` 字段。仅启用CHI的新run精确增加 `recovery_events`；旧run保持旧字段集合。profile/CONFIG绑定 `RECOVERY_POLICY`，default_enabled=false；单次上限、每链1/run2/shared50及TIME_POLICY数值不变。runbook中的陈旧60/120秒已更正为当前240/300秒，这不是本次修改超时。
3. immutable许可schema为 `chi-recovery-permit-v1`，另含policy、`view_version=chi-recovery-view-v1`、`history_version=chi-tool-history-v1`、`instruction_version=chi-recovery-instruction-v1`及上述身份/轮次/hash字段。受限view_body只留在本地wire证据。文件为 `wire-evidence/<run>/<parent>-recovery.json`，复用exclusive写/fsync。账内事件精确为 `{parent_round,permit_sha256,continuation_round}`。许可文档的null/issued/pending描述发放时事实，实际关联/结果来自事件与请求/诊断，不覆盖许可。
4. issue_recovery核对父main已settled、HTTP200/完整length/可信usage/ok诊断、原wire/历史及精确派生视图；许可先落盘再记账引用，reserve在同次accounting persist绑定唯一下一轮。孤儿/坏关联拒绝，落盘异常当前对象禁止重用；未发送许可也消耗额度，重启不自动续发。
5. Guard外层control lock维持逻辑step，两次物理请求分别取得billing lock；不持不可重入锁嵌套HTTP。普通SDK历史仍走原ToolContract；continuation要求程序持有的request对象、精确body/view hash和原闭合prefix，不允许任意marker/额外历史。原Runner只运行一次，不重置turns、时间或claim。
6. 截断工具批次整批零accept/dispatch。恢复新批次先在contract副本完成整批校验，再核对canonical分类/已完成写参数指纹，成功后才真实accept及原before_batch、实体/角色/路径/claim门禁。分类依据固定catalog与服务源码，inbox.read_message写read_at，部分get/list会sync工作区，保守按mutation。明确REFUSED的零执行记录不算完成写；实际dispatch返回的mutation即使业务ERROR也保守防重放。不能识别参数不同但语义等价的重复操作。
7. 每个wire经过观察登记及完整计量。wire-trace每实际dispatch一行，recovery-trace另记消耗许可的未发送/已结算/失败/未知。summary分列physical用途次数、SDK逻辑步、当前run已知token和account_namespace整账累计；SDK ModelResponse只含返回Runner的最终响应，不能代替两笔wire账。每条恢复停因取自身诊断，后续失败不回写旧成功恢复。

主代理要求并核对的返工包括：完整total_chars/基础预留、bool与整数视图差异、坏工具容器拒绝、读工具真实副作用、REFUSED不冒充完成写、未发送许可追踪和独立停止归因。没有清guard.error、忽略未知字段或扩大工具权限。

### 固定环境与主代理独立证据

镜像 `chi-agent-a-control:latest` / `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Python3.12.15/Linux arm64。Agents0.13.6、OpenAI2.36.0、httpx0.28.1；mcp1.30.0、jsonschema4.26.0、pydantic2.14.1、pydantic-core2.50.1、httpcore1.0.9。只读复用原model/PDF卷，没有安装/升级。固定vendor为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，没有读题世界/隐藏expectations。

初始源码归档SHA256 `3bf20ba5ae7f372c219ca5ee4ef1c6dc10f8a7964b62ad40c9f20a9a2ffccb56`，归档时runbook尚为旧说明。功能测试在其只读源码上完成；之后仅将更新runbook纳入最终包并独立重验身份/SDK路径。代码与实现提交一致：

| 文件 | SHA256 |
| --- | --- |
| go_chi_guard.py | `504283842276a7c3d246aa067cc198f94db11c8b9f5a49cb23e63a81a7648c5d` |
| go_chi_runtime.py | `a0efbda276ac1c634d3002e69e15fca7c45e830c89d86badf7ab4feebdc388a7` |
| go_chi_journal.py | `1f6fe2eea2f7bda35db379925049baf9a82bc36a833eacf4f967022069927a14` |
| go_chi_recovery.py | `c20ebb511b7c2a10a08025f3c388472ca5e97331aa02253d1a9e339413dbeb65` |

证据集中在本worktree忽略目录 `runs/c2-input-output-20261102/`：selftest为作者日志；independent/audit为主代理另写的4份脚本，independent为独立日志、固定归档及离线包。原历史账/轨迹没有挂入测试容器，不重跑历史真实任务，不创建后继state绕过阻断。

| 执行者与检查 | 实际结果/日志 |
| --- | --- |
| 作者最终相关回归 | 235 passed、61 subtests；后加续写在途取消组21 passed，与前组重叠不相加。selftest/p2c-final-targeted.log、p2c-sdk-continuation-cancel.log；只是作者自测 |
| 主代理另写反例 | **30 passed、96 subtests**，退出0；independent/root-counterexamples-1.log。17项真实SDK runtime、6项计量/分类、7项许可/故障，数据和断言独立构造 |
| 主代理受影响回归首轮 | 317 passed、24 failed、8 skipped、53 subtests，退出1；affected-regression-1.log。24项为非标准vendor挂载导致upstream_identity_unavailable，未算通过 |
| 主代理只修挂载后同代码复跑 | **341 passed、8 skipped、53 subtests**，退出0；affected-regression-2.log。5项Harbor overlay缺失、3项controller Docker SDK缺失，不计通过，未安装补数字 |
| 最终allowlist包与真实身份链 | 38文件；manifest `b6833fbc6f692203e5ce4a1a64e5a340888bcf9d86112133b8542506b626d56b`；profile `ce313e330e469e1ce9d3316dc48b967d287c37794fc982eae7f6c0ce72bea6e2`；runtime identity `f486540643839d9b81cf409850a86ea9ca997c0d8361878622acd1ad2d96e458`。package-build.log、package-identity.log；真实_identity未打桩 |
| 仅挂最终导出包的实际SDK恢复路径 | **17 passed**，退出0；package-sdk.log。没有源码checkout补依赖，不扩大为C3全部旧局部导入已修复 |

独立SDK覆盖A/B片段、完整前半批与残缺后半批整批零执行、新工具结果回传、provider绑定/CM路径/原门禁、重复ID/完成写重放/REFUSED区别、再次length、两链后第三拒绝、坏容器/未知/超时/取消/marker；事务反例覆盖无许可purpose、bool索引、许可间插入、精确view篡改、hash刷新后未知字段、落盘孤儿及旧证据字节/只读inspect不变。作者故障矩阵另外覆盖reserve/response/settle/diagnostic及取消锁等待断点，主代理从固定候选实际复跑。

包内17项是上述runtime反例重复执行，不能与30项相加冒充47项不同测试。作者分步数量也不累计为更大分母。P0无依赖卷/只读挂载错误、作者预算夹具缺字段、取消夹具/错误码预期不符、独立首轮24项环境失败均保留日志；旧anthropic/Harbor/controller环境缺口没有改成全量通过。

实际独立外壳如下（SNAPSHOT为固定归档项目、AUDIT为主代理脚本、VENDOR为固定原vendor；先创建快照的空vendor挂载点）：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v "$SNAPSHOT:/workspace:ro" -v "$VENDOR:/workspace/vendor/chi-bench:ro" \
  -v "$AUDIT:/audit:ro" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro -w /workspace \
  --entrypoint /opt/venv/bin/python chi-agent-a-control:latest \
  -m pytest -v -p no:cacheprovider /audit/c2_independent_runtime.py \
  /audit/c2_independent_meter.py /audit/c2_independent_journal.py
```

反例首轮实际vendor挂在/vendor并以/vendor/src导入，不依赖旧身份路径；身份敏感回归改用上述标准路径。受影响回归参数为 `tests/test_go_chi_*.py tests/test_patient_*.py tests/test_request_budget.py tests/test_dev_patient_broker.py`，容器内shell展开。包测试工作目录/PYTHONPATH改为/package，完全不挂源码，先c2_independent_bundle.py真实身份链，再c2_independent_runtime.py。所有容器禁网/只读根/tmpfs，无Key、socket、真实账或world；fixture是合成输入，不是官方判分或真实模型响应。

### 未验证项与后续真实验证候选

本轮真实请求 **0**。没有读取Key、发模型/摘要/续写请求、启动B/C/Trial/判分、签发新B、正式release或发布。Go真实partial assistant/reasoning协议、实际失败率/总用量/时延收益、业务/临床正确性和官方成绩均未验证。没有输入自动摘要、tokenizer精度或百万token实测结论。不同参数的语义重复写、OS/daemon硬崩溃、真实端点断点及skip路径不在本轮通过范围；Python故障注入不等于穷尽电源/文件系统故障。

若后续批准真实验证，最小提案为候选实现bd1b9f5及上述最终bundle/runtime identity，同一Go endpoint、deepseek-v4.1-flash/high不变：先只读核对现行同账准入，旧未知仍按原门禁阻断，不换root；获准后新coding-B一次、最多6请求/每次1024，再做A/B各一条自造协议历史探针（每条最多2请求/每次8192，总最多4请求）。只验证精确部分reasoning视图与完整新工具往返；探针不伪造“真实length发生”，B不证明恢复收益。需要自然length的任务回归时再冻结具体已见任务/角色/每run50与对照条件。任何未知token/结果、意外费用源/Extra Usage、协议不符、额外工具或超限立即停止并留证。本提案未执行/未授权，不占摘要预算，不把旧B/基线写成新候选证据。

用户验收后按学习约定集中讲解正常与失败调用链，不默认安排小测；无用户实践证据，不记为掌握。

### 首次Git交付

[PR42](https://github.com/xsw932187210-cell/chi-agent/pull/42)首次创建为base=main、非draft/open，附加到本聊天，未合并/启用auto-merge。原实现提交为bd1b9f5，首轮文档提交4442866已通过git ls-remote核对后建PR；随后文档提交23c3f05不改变已审代码或包身份。当时PR40仍open，未由主代理合并/关闭。仅显式暂存自有代码/合成测试/配置及文档；runs、原始轨迹、Key、数据、vendor和离线包均未上传。

收尾一次批量保存曾因自动审批用量耗尽被拒绝执行，非安全判定；原命令未执行。用户将聊天工作区切换到本worktree并更新写权限后，正常workspace写入保存证据/报告；后续Git提交/推送审批实际成功，没有绕过被拒绝的Git动作。记录见independent/p0-environment-failures.log。

### PR40合并后的冲突消解（2026-11-02）

用户报告PR42冲突后重新fetch：main已为`42b86881009d48e5ca3c5a934a6ef92e2fd6b628`，PR40已合并。原PR42的`23c3f05`归档保存在本地，备份分支`codex/c2-recovery-pre-pr40-backup`保留完整原提交链。将本任务分支rebase到最新main，没有merge或push main；六个冲突均在学习入口、design、output-recovery、spec、tasks和REVIEW_STATE文档，代码提交自动干净重放。

变基实现提交为`5da610a`。与原已审提交链逐文件比较scripts、profiles、tests及包内runbook均无差异；原bd1b9f5及其测试结论保留历史身份，变基只改变祖先/提交SHA，不冒充新功能复验。已合并PR40的AGENTS/COLLABORATION、架构评审及路线补充保留，文档同时保留规划取舍与后来的实际实施状态；旧“PR40仍open”只保留为首次交付历史，当前状态更新为已合并。

本轮仅做文档冲突消解，检查冲突标记、diff和链接，并按冻结38文件包manifest再次核对实际源码/大小/hash。包身份及之前离线证据适用范围保持，不重跑无变化的功能测试，不读取Key、不发真实请求、不处置旧账。变基推送使用绑定原远端`23c3f05f456cbc12aead3261cedb3b0591276a3c`的force-with-lease，防止覆盖其他新增提交；最终再核对远端SHA及PR可合并状态。

冲突消解后的Docker/Python3.12检查实际通过：10份入口/规格/状态文档无冲突标记，244个本地链接目标存在；全部38个包文件逐字节大小/SHA256与上述最终manifest一致，manifest仍为`b6833fbc6f692203e5ce4a1a64e5a340888bcf9d86112133b8542506b626d56b`。脚本与日志在`independent/pr40-conflict/`，没有安装依赖或运行真实请求。
