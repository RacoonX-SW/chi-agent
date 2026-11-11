# 输入摘要：实现与独立离线审核

日期：2026-11-03。结论：`chi-input-summary-v1`在下列限定离线范围通过；默认关闭。没有读取Key、真实模型/摘要/续写请求、world、B/C/Trial或判分。语义忠实度、真实端点兼容与费用收益未验证，不能据此启用真实任务。

## 1. 候选、分工与边界

- 已核实PR45合并；基线`21ec34c15f4e6e3f8606b4bb10d15ed3a72560ad`，新分支`codex/input-summary`，规格提交`0e2172b`，实现/测试候选`3e420429b146786c22c077f61ac23d958f5044ac`。
- 主代理冻结[契约](../openspec/changes/project-completion/input-summary.md)、拆分、独立复验、文档与Git。唯一实现者显式`gpt-6.1-terra/high`、`fork_turns=none`；实现者编写生产代码及首批测试。主代理另写`test_go_chi_summary_review/persistence/reader.py`独立反例，未以作者自测代替验收。
- 实现者后段额度中断；恢复后其旧工具环境把worktree认作不可写，runbook写入被自动审批以额度限制拒绝，未执行。未换模型：同一Terra提供输出schema/SDK测试和runbook的**文本补丁**，主代理在已授权worktree机械落盘，随后独立审核/执行。补丁未由实现者自测，不能把下列最终复验列为作者自测。
- 原DeepSeek目录`/Users/asaki/Documents/ChatGPT/Kaggle`仍为`codex/reliability-boundaries`、干净，未覆盖/暂存/清理；本worktree与测试输出隔离。没有接管M2、全面重构或改变C1/C5业务结论。
- 本地证据集中忽略目录`runs/input-summary-20261103/`：`selftest/`保留作者全部成功/失败；`independent/`保留主代理脚本、快照、原失败日志、合成旧证据、包和复验结果。均不上传受限轨迹/vendor/凭据。

## 2. 实际行为与调用链

入口`go_chi_entry --input-summary chi-input-summary-v1`仅live可用，profile/CONFIG精确同步；`SUMMARY_POLICY`默认off。与output_recovery、Y shadow同时启用明确拒绝，不静默关闭另一项。

正常链：`run_chi`保持Runner完整历史 → `ChiGuard._handle_input_summary`严格验证原请求/ToolContract → 达到4/5预算或超限时选择旧闭合前缀、保留最近2批 → `protected_snapshot`固化程序事实 → `ChiJournal.select_summary`写selection并发一次性许可 → 原reserve/HTTP留证/可信usage settle → 候选验证 → `install_summary`先持久候选/检查点 → `project_summary`保存原source、保护状态及wire映射 → 重新计量后发送main → 新工具仍过原门禁和整批写重放检查。

摘要不是覆盖原账的“新真值”：SDK/ToolContract和证据保留原批次，真实wire才使用user角色检查点加近期/新增批次。原system主体、任务instruction、tools、近期reasoning不变；第一次投影用summary后used，后续不再次加1。原始工具结果hash及args/实体ID仍可回查。模型候选只提供有来源的文字、疑问和计划，不改绑定、pending、claim、授权或费用。

每run最多1次summary，8192输出，同模型/thinking/high，计原共享50并留下一次main；不改确认32768/最多2次或患者辅助10次。摘要输入包含完整`output_schema`和原instruction，均计量；候选≤32768 UTF-8字节，投影至少缩减1024字节且适配最终预算。一个检查点可重用，不二次摘要。文本块列表、未知写效果、保护状态已超限等保守停止；没有统一首尾截临床资料。

`validate_saved_source`以首次实际main wire、launch instruction hash、已接受assistant/tool批次及原journal工具证据锚定source。claim成功还要求原local-claim_done成功结果及最终账标志；reader严格验证类型/字段/关联和孤儿证据。初始TaskState/PatientBinding来自可信runtime回调的内存快照；reader不能从未绑定外部logs重建初始内存，也不声称抵抗全部账/证据/seal被共同重写。

## 3. 独立环境与固定材料

全部Python在禁网只读Docker内运行；宿主机仅编辑/Git/Docker。无安装或依赖升级。

| 项目 | 实际值 |
| --- | --- |
| 镜像 | `chi-agent-a-control:latest`，`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3` |
| 解释器 | Python3.12.15，Linux arm64 |
| 固定overlay | `chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`，只读 |
| SDK | openai2.36.0、openai-agents0.13.6、httpx0.28.1、mcp1.30.0、jsonschema4.26.0、pydantic2.14.1/core2.50.1 |
| vendor | 干净`4444a07fa68a4f1623f841a292a54e284fc8e7f7`，只读挂载；未启动world |
| 首审快照 | `diagnostic-1.tar` SHA256 `1f5c60389b3d01ee3a4cba7fed6915abf1d60624a1cb6db241042b58e538b2fc` |
| schema返工快照 | `candidate-2.tar` SHA256 `d7382b93ad2c52136559f484b334b5d3322b2ac2220246284c06a6a944c654a0`；其生产/profile/runbook与最终候选相同，后补主代理测试不改变包 |
| 最终Go包 | 40文件，manifest `d99a49f090abdc767a5712947b1acac0b0b5a8551cbe54335b37acb1e2609041` |
| 隔离Go运行身份 | `aa88a6544d2397dcc59c3d5c4009065d4616dbc822b87994d5d1522b34b7b21c`；新身份，不能复用旧B |
| 旧evaluation包 | 14文件，manifest `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`，与基线一致 |

SDK/PDF/源码身份详情留`independent/work/independent-2/isolated-package.log`，不把旧版本实跑冒充新身份已验证。

## 4. 验证结果

以下套件存在重叠，不能相加为总覆盖量；子测试与pytest测试分别报告。

| 检查 | 结果及证明边界 |
| --- | --- |
| 最终受影响回归 | **405 passed、8 skipped、90 subtests passed**；含Go全套、配置/C4/import清单、患者绑定/request_budget和主代理新增反例 |
| 环境跳过 | 5个旧Harbor overlay、3个旧operator Docker SDK环境检查；跳过不算通过，本包未改这些控制器接点 |
| 真实SDK长历史 | 固定OpenAI Agents/官方Runner模块+MockTransport，summary无tools；main/main/main/summary/main/main，原SDK历史继续合法，首投影保留2批，后续增加新批，trace物理请求与逻辑步分开 |
| 独立Guard反例 | 正常缩小/中文/近期reasoning保留/检查点重用；坏JSON、空、重复键、额外字段、echo hash错、虚构来源、候选UTF-8过大、缩减不足、length、工具响应、保护状态变化、未知usage、取消均阻断后续main |
| 整批写重放 | 新批同时含读和已完成canonical+args写时，两项均零accept/dispatch；原完整record仍保留 |
| CM真实混合journal | 1summary包含在50共享、10患者辅助，总60；第51共享在lower前拒绝；parent/用途与strict inspect通过，见`cm-counter.log` |
| 严格reader | 任务/旧工具结果/claim自洽伪造3类拒绝；run/event额外字段、bool round、projection bool、缺关联、未知status6类拒绝且只读字节不变 |
| 组合/默认 | parser默认off；preflight/coding-B+summary、summary+recovery在身份前拒绝；runtime summary+shadow在网络/日志准备前拒绝 |
| 旧证据兼容 | 用基线旧代码生成closed/unknown/recovery三组合成历史，共21文件；新inspect读取前后逐文件hash不变。unknown复制件仍报`chi_usage_unknown`阻止新attempt，不清零 |
| 隔离Go包 | 仅导出包+2个测试辅助文件+固定SDK/vendor/PDF，未挂工作区源码；真实`_identity`通过，包内实际摘要SDK用例1 passed |
| 隔离evaluation包 | 实际`_runtime_identity`通过，budget纯模块来源/hash核对通过；未宣称执行真实Trial |
| 最终存储一致性 | 逐个allowlist来源→包内目标比对全部字节、六个摘要测试与已测快照一致；新报告/契约本地链接存在，见`final-integrity.log` |

4个独立持久化断点均报`chi_summary_persistence_failed`，同对象后续reserve sticky拒绝、无投影main派发，原可信用量保留。各结果：

| 故障写入 | 物理summary | 共享请求数 | 事件落盘状态 |
| --- | ---: | ---: | --- |
| selection | 0 | 5 | 未建立事件 |
| candidate | 1 | 6 | requested |
| checkpoint | 1 | 6 | candidate |
| projection | 1 | 6 | installed（检查点已落盘，后续投影失败） |

四者只读inspect均可辨识并返回`execution_allowed=false`；不能把最后一行说成检查点未安装。sticky是当前journal对象的fatal，不虚称所有新attempt永久全局封禁；入口不提供自动重启安装/续发，同attempt重复和unknown等原门禁继续有效。

## 5. 审核发现、返工和失败保留

1. 首审发现模型仅被要求“指定JSON”，实际请求却没有完整候选格式。单元测试硬编码候选可掩盖这一缺口。同一Terra补入`OUTPUT_SCHEMA`及原instruction，SDK合成响应改为依据收到schema构造，主代理增加独立固定字段/限制断言；摘要输入连schema一起计量。最终验收基于返工后代码。
2. 作者`sdk-01/02`因合成MCP structured与text包装导致预算提前超限，失败保留；修正合成结果规模/预算后sdk03/04通过。这不是放宽生产预算。作者旧isolated/export是返工前身份，不能充作最终包通过。
3. 主代理首个Guard夹具错误要求API请求有`response_format`，本契约未要求该字段；callback断言触发未知pending。保留`guard-independent.log`及`independent_guard-response-format-assumption.py`；修正夹具后通过，未修改生产协议来迁就测试。
4. CM夹具首投影把source_used写成summary后计数，正确被`source_changed`拒绝；改回源请求原计数后通过。reader夹具最初父目录缺失引发`chi_state_persistence_failed`；配置检查夹具漏传必填lower引发TypeError。各失败脚本/日志保留，不列为生产缺陷或被通过覆盖。
5. 最终完整性脚本初次把allowlist目标路径当源码路径，找不到映射后的`RUN_CHI_GO.md`；保留失败脚本/日志，按destination→source映射核对后通过，未改包或生产代码。作者额度/写入拒绝，以及中间编辑命令语法错误保留其执行含义；没有据此换模型、重跑历史真实任务或隐藏成本。合成usage/cost不代表账户消费。

## 6. 可复验命令与材料

独立材料根为`runs/input-summary-20261103/independent/`，`audit/`保存所有脚本，`isolated/`保存隔离测试辅助，`work/independent-1/2/`保存原日志，`work/root-evidence/legacy/`仅为本次合成旧版本材料。最终受影响命令：

```sh
python -m pytest -q -rs -p no:cacheprovider \
  tests/test_go_chi_*.py tests/test_config_limits_consistency.py \
  tests/test_c4_policy_boundaries.py tests/test_import_inventory.py \
  tests/test_patient_identity_binding.py tests/test_request_budget.py
```

在上述固定镜像中`--network none --read-only --tmpfs /tmp`，`PYTHONDONTWRITEBYTECODE=1`，`PYTHONPATH=/audit:/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src`；候选`chi-agent`挂`/workspace:ro`、独立结果挂`/workspace/runs:rw`、固定vendor/依赖卷只读。`audit/cm_counter.py`、`audit/legacy_fixture.py`（基线脚本）、`audit/legacy_verify.py`及`audit/config_gates.py`分别复验混合计数/旧证据/配置。隔离包以`package-go:/package:ro`运行`isolated/package_identity.py`和`pytest isolated/test_go_chi_summary_sdk.py`，Python路径仅`/package/scripts:/audit`加固定依赖/vendor，没有宿主项目源码。

## 7. 验收限制及后续

本次实现和离线复验完成，用户最终验收/合并；主代理不merge或auto-merge。真实端点对派生历史/保留reasoning的接受程度、摘要语义忠实度/提示注入抵抗、临床正确性、长运行收益及净费用均未验证。实际SDK场景为payer；CM混合用途为真实journal/transport合成验证，未冒充完整CM业务Runner实跑；provider新摘要路径尚未真实业务验证。

同一run不支持摘要+length恢复或Y shadow，不再摘要，不流式，不改模型/思考强度。没有闭合前缀、无法缩小、保护/近期内容过大则停止；有已结算坏候选也不fallback。取消/网络/未知token保持原pending/阻断；持久化故障不能靠清理或换账根消除。

C1旧unknown处置/后继特定授权、C5交流佐证、依赖锁及Harbor正式运行等原未闭合项保持，不顺带修复。下一步先审本PR；若要真实兼容探针，需基于这一新身份另给具体用途、次数、停止条件和可用准入证据，不能默认沿旧B收据启动。
