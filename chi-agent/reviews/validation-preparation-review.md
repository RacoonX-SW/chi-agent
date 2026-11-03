# 交付候选冻结与最小真实验证准入准备

日期：2026-11-04（Asia/Shanghai）。本报告集中记录本轮离线事实；当前短状态只在 [REVIEW_STATE](REVIEW_STATE.md)。运行提案见[新审批草案](../openspec/changes/validation-preparation/proposal.md)，机器可核对清单见[候选清单](validation-candidate-20261104.json)。**离线候选已固定，真实执行未授权。**

## 1. 工作区、来源与审核关系

- 主工作区 `/Users/asaki/Documents/ChatGPT/Kaggle` 开工为干净的 `deepseek/m4-r1-r2-repair@83e0ceb`；可复用隔离工作区为干净的 `codex/r1-r2-reviewed@3270e8d`。保留旧分支及隔离工作区，不往已合并分支追加。
- 刷新远端后，`origin/main=0625c26dc9da453a3ac13bf537d156cad57dd940`；GitHub API 独立确认 [PR51](https://github.com/xsw932187210-cell/chi-agent/pull/51) 已合并，merge SHA 相同。从此主线新建 `codex/validation-preparation`，没有强制回退 main。
- 开工只读进程名检查未发现 Python/pytest/DeepSeek/Gemini 项目执行器，Docker 无运行中容器。此为开工快照，不宣称能够证明所有编辑器永远没有写入者。本轮只有主代理写文档，固定 `git archive` 快照用于执行；没有派实现代理或要求 Gemini 重审。
- `83e0ceb22f79c88699d6e44fdbfc85290e2445fa..0625c26` 只有 `tasks.md`、`REVIEW_STATE.md`、`project-cumulative-review.md` 三份文档差异。生产代码、测试、profile 无新增未审差异；两端 scripts tree=`aac7b81916a37dbcbeb85e13085edc4924b19ae3`，tests tree=`4c522d9c2985114f6cd8d3c1d6e6fd40dde73139`，profiles tree=`41efabf0cd01f3d1efd7d63140c31404be793832`。
- R1/R2 的限定离线通过证据沿用[累计报告第6节](project-cumulative-review.md#6-r1r2独立复审2026-11-04)。原 `0a8449e` 初审失败、全部旧候选/真实结果及未知保留；本轮文档提交不成为另一份生产实现验收。

## 2. 冻结清单与供应责任

源码固定为上述 merge commit，而非未来文档提交的 HEAD。由此快照重建，不使用未提交实现。候选 JSON 的原始文件 SHA-256 为 `1846d79cd276aee9cb8414e9e80b78ac9639f227c3a2ae1a97bcefb9f3f9b1d2`。

| 对象 | 本轮实际身份 |
| --- | --- |
| Go bundle | 41 个 allowlist 成员；manifest identity `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb` |
| Go runtime | `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559` |
| release manifest 文件 | `4b0c2f31553fac46cfa1ee1f6e8638e49e53377966e81267960f762518017d6a`，source_commit 绑定 `0625c26…` |
| release SHA256SUMS 文件 | `4464501696ab03ccbb9b8847cedc4ad864dca3b04399216889599226fe429f69` |
| release 内包 | 与单独 Go 包 manifest 字节相同；42 个文件为 41 成员加 manifest |
| 旧 evaluation 包 | 14 个 allowlist 成员；manifest identity `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`；旧非 Go 离线入口保持 |
| 模型与路由 | `deepseek-v4.1-flash`；`https://opencode.ai/inference/go/openai/v1/chat/completions`；thinking enabled、reasoning_effort high、0 自动重试 |
| 上游/平台 | clean vendor `4444a07fa68a4f1623f841a292a54e284fc8e7f7`；Linux arm64 / Python 3.12.15 |
| 检查镜像 | `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3` |
| 固定依赖 | Agents 0.13.6、OpenAI 2.36.0、httpx 0.28.1、httpcore 1.0.9、mcp 1.30.0、jsonschema 4.26.0、pydantic 2.14.1/core 2.50.1、pypdf 6.20.1 |
| 锁文件 | model `47e00d40985e682e40c3e36cf7f74c0a10886935ff4c4e6d25fe8d3aaa08927d`；PDF `61c09a5c1cff09003ef2e5b09842cfcc6ef0ef0a86a36ba5f507833e16570202` |

表中 bundle manifest identity 使用既有 builder 的规范化身份算法，**不等于 manifest 文件原始字节 hash**；候选 JSON 同时给出成员/文件 hash、SDK source hash、PDF wheel/package hash，避免混淆。

固定入口是包内 `scripts/go_chi_entry.py` 的 `preflight/coding-b/live`。正式适配为包内 `go_chi_harness.GoChiHarness`；它不表示 stock harness 自动选用。CHI system 使用固定上游 `SYSTEM_PROMPT`（字符串 SHA `f6db1a146efe771b73a2415948b725570b374833724b584d8d8e12f9d3ac7084`），预算反馈由固定 `request_budget.py` 生成；coding 指令/工具、摘要 system/schema/notice、恢复 partial/regenerate 常量及所有包成员 hash 详见候选清单。公开任务 instruction 和工具参考另绑定资源身份。

动态工具由固定 `go_chi_mcp.py`/`go_chi_tools.py` 与上述 vendor 产生，能力为 `f0-f3-v1`；payer 角色目录 canonical hash=`cca921b6fba9e536489a6a6184502747c89dcbba34434129b7f6ebb72443deb4`。本轮未连接 MCP，未取得现场完整工具 schema/description wire hash；执行前必须保存实际 list_tools 与转换后定义，检查角色/重名/schema/来源，不能将固定目录 hash 冒充现场工具 schema 已验证。

| 层 | 负责供应和范围 |
| --- | --- |
| 运行包/release | 只供应 allowlist 自有代码、profile、锁和 runbook；不含 Key、数据、手册、vendor、账本、轨迹或开发患者模拟器 |
| 包外开发操作者 | `role_operator.py` 负责新 world/输入/状态/捕获/清理，`role_runner.py` 负责生命周期；它们的源码 hash 已记录，不能算进包内闭包或官方 harness 已验 |
| 开发患者模拟器 | `dev_patient_*`/broker 是包外开发资源，本轮方案选 payer 不用患者；CM 后续若采用须单列同账辅助额度和模拟器条件 |
| 官方环境 | 固定官方源码、world 镜像、角色 MCP；Anthropic 默认患者路径保持。本轮未启动、不替换、不注入判分凭据 |
| 调用方/有权限的资源提供者 | 供应 vendor、固定依赖、受限手册、任务资源、MCP、可写 state/log、运行时模型凭据及持久化/清理；release 的 example plan 仍是占位示例，不是完整生产供应 |

默认关闭 `input_summary`、`output_recovery`、Y shadow；摘要/恢复首版互斥，也不与 shadow 组合。主/确认/summary/continuation 共享 50；确认子限额2；患者辅助独立10且不占上述50，因此一般 CM HTTP 上界60。主/summary/continuation 输出8192、确认32768、患者8192、coding-B 1024；无流式、无上限/模型/思考强度调整。context 仍是 UTF-8 byte 上界估计（3,500,000 chars / 1,000,000 estimated tokens，按用途输出预留），不是实测 tokenizer/1M 可用性保证。

## 3. 实际离线检查与保留失败

全部 Python 在 Docker/Python3.12，`--pull=never --network none --read-only --tmpfs /tmp`、`PYTHONDONTWRITEBYTECODE=1`。无 Docker socket、凭据或 `.env` 挂给检查容器；只有指定输出目录可写。原始脚本/输出集中本机忽略目录 `chi-agent/runs/validation-preparation-20261104/{audit,evidence,exports,snapshot}`，不上传。摘要/恢复响应来自 MockTransport，不能当成真实端点。

| 检查 | 本轮实际结果 | 本地 evidence 文件 |
| --- | --- | --- |
| 固定快照 Go/evaluation/release 构建并校验 | exit0；身份见第2节；release `plan_checked=false` | `build.log`，成员清单 `exports/inventory.json` |
| 隔离 release 实际 CLI preflight | exit0，`identity_verified`，runtime 完全匹配交接 | `preflight-release.json` |
| 隔离旧 evaluation 真实 `_runtime_identity()` | exit0，`verified_for_offline_integration`；旧预算模块 hash 匹配 | `isolated-evaluation.log` |
| 隔离 Go 实际 SDK 摘要/恢复/诊断 | **29 passed、9 subtests**，exit0，无 skip | `isolated-sdk.log` |
| 固定快照打包/release/delivery/harness 抽验 | **22 passed**，exit0，无 skip | `packaging-tests.log` |
| 非秘密候选元数据及凭据缺席断言 | exit0；提示/文件/策略 hash 留证 | `metadata.json` |
| payer 公开输入/world 文件 hash、包外脚本身份 | exit0；未解析 expectations 正文 | `resources.json` |
| 实际资源路径的 `validate_plan` + `check_plan` | exit0，`valid`；手册/角色目录 hash 已取 | `supply.log`、`supply-plan.offline.json` |
| C1 两个指定 accounting 元数据/hash | exit0，两者与既有 C1 hash 一致；读前后字节相同 | `admission.json` |
| 文档链接/候选与实际证据一致性 | exit0；本地链接、候选SHA、preflight/日志hash及请求上界一致 | `docs-check.log` |

隔离 SDK 容器只挂导出包、5个指定测试/辅助文件、固定依赖/vendor；没有源码 checkout 可补包内漏依赖。打包测试另在只读源码快照中运行，不能冒充隔离包证据。数量不和既有全量回归相加。本轮无生产改动，未重跑全仓；PR51 的 885 passed/11 skipped/259 subtests 及 unittest 实际554项、2个既有 anthropic 导入错误/11 skipped 保持原证据范围，不写全绿。

保留两项环境故障：最初镜像标签 inspect 一次返回 No such image；随后 image ls 和固定 digest inspect/run 证明原镜像存在，没有下载/换镜像。打包抽验首轮因快照缺空 vendor 挂载点而 Docker exit125、零测试，原日志 `packaging-tests-mount-failure.log` 保留；只补空挂载目录后同代码通过。没有把环境启动失败计为业务结果或覆盖原日志。

本轮未重装依赖：锁未变、实际版本/source hash 与已审身份一致；[旧Z6空卷安装](z6-clean-repro-review.md)仅保留其原候选历史含义。本轮证明当前包能在这些固定卷运行，不证明当前候选重新在空机器安装或跨架构通过。controller 的 `docker`/`huggingface_hub` 未锁风险、Harbor overlay/官方 CLI 缺口仍在。

可复核执行步骤（下列 Python 均在上述 Docker 限制中，不在宿主执行）：

```text
git archive 0625c26dc9da453a3ac13bf537d156cad57dd940 → snapshot/
/audit/build.py → Go + evaluation + release，validate_bundle/verify_release
/package/scripts/go_chi_entry.py preflight --bundle-sha256 de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb
/audit/legacy_identity.py（PACKAGE_KIND=evaluation）
python -m pytest -q -rs -p no:cacheprovider /audit/tests/test_go_chi_summary_sdk.py /audit/tests/test_go_chi_recovery_sdk.py /audit/tests/test_go_chi_diagnostic_causes.py
python -m pytest -q -rs -p no:cacheprovider tests/test_go_chi_bundle.py tests/test_go_chi_release.py tests/test_go_chi_delivery.py tests/test_go_chi_harness.py
/audit/admission.py；/audit/resources.py；/audit/metadata.py；/audit/supply.py
```

`build.py` 只读 `/source`、写 `/out`；隔离包的 `PYTHONPATH=/package/scripts:/audit/tests:/model-deps:/pdf-deps:/package/vendor/chi-bench/src`。依赖卷为 `chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`；vendor 仅只读挂相应包路径。供应检查单独只读增加公开 instruction/reference、受限手册与包外 `go_chi_delivery.py`，因此供应检查不是“仅运行包可独立完成全部配送”的证明。临时 state/log 父目录位于容器 `/tmp`，无真实 journal/收据生成。

## 4. 只读准入矩阵

先复用[C1/C3报告第2–3节](c1-c3-admission-package-review.md)及[累计报告](project-cumulative-review.md)，本轮只增加两份明确 accounting 文件的 hash/元数据复核，未重读全部账户、请求正文、隐藏 expectations 或完整历史轨迹。以下区分客户端账目、可信用量和授权：

| 对象/条件 | 可证明事实 | 当前准入判断/所需决定 |
| --- | --- | --- |
| 旧 Q/S 已明示留档链 | 既有特定 acknowledgement/来源迁移保留，旧未知未变为结算 | 仅适用原请求/原后继；不自动覆盖 payer-010 或本候选 |
| external v2/v3 已对账、v4–v6 已知结算 | 复用各原报告；已知 token 与 USD 记录不等于账户全史核清 | 不重新试跑，不复用其 B 收据认定新包通过 |
| state-abl-on / payer-010 round1 | 文件 SHA `1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef` 未变，pending 仍指向原 run/round | 结果/token 未知；不推断零发送、成功或费用0；保留阻断 |
| state-abl-on2 后继 | SHA `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9` 未变、pending=null；B009/payer012/013 元数据同 C1 | 本root内部完整不处置旧unknown；两root均无 acknowledgement/reconciliation/source_transition。所选来源仍缺特定后继授权佐证 |
| 可信 token、费用字段缺项 | 可记录 `null`/warning，list/allowance/charged USD 分列；旧 CNY 独立 | 不是新 unknown 的解除理由；不因单独费用缺项要求重复开通/确认 Go |
| 本轮 frozen identity | 离线身份/依赖/包校验通过，无新真实 B | 旧 B 不适用；须具体 B 许可及历史准入决定 |
| Go 用途/隐私取舍 | 用户既有决定保持，不再重复确认 | 不写成官方许可或十一月 ZDR 已核验；此准备轮未查外部条款 |
| C5 交流陈述 | 原机械依赖与来源核查保留，缺会话支撑仍缺 | 不从21/22、note或MD字段推断业务/临床通过；不阻塞无业务coding-B，但限制后续结论 |
| 摘要/恢复探针 | 包内CLI开关存在；真实触发、语义和费用效果未验 | C1/B/具体用途批准 + 包外操作者接线后才可执行 |
| Harbor/F.5 | 旧真实组件+合成HTTP接点证据存在 | 官方CLI、真实Go Trial、完整配送/状态回收/清理仍未验；另冻结清单，不由本草案启动 |

后续有两条合法准入路径：提供与单请求匹配的可信结算证据，走原受审处置；或由用户明确保留该 unknown、限定后继 evaluation/候选/次数的风险处置决定。后者必须附原root/hash/run/round及本次权限关联，**不是费用核销、原账修改或请求重发许可**。不默认为同账户另开root就可继续。本轮未调用 acknowledge/reconcile/rebind/init，未改 pending/旧账。

## 5. 探针资源及调用接线缺口

两个协议探针均拟用已见 payer 开发题 `pa_t030_t030_o002_p01_triage_payer`，每次新世界、各一次新 attempt，互斥开关。选择固定已见资源是为端点协议验证；不作为未见集，不根据隐藏答案调动作。资源已只读哈希核对：

| 资源 | 路径/身份 |
| --- | --- |
| dataset（相对项目） | `runs/representative-role-baseline-root/resources/dataset` |
| manifest | `runs/representative-role-baseline-root/evidence/role-resources-payer-t030.json`；SHA `6518225bd1c91525c17ff4f735173baaf1bf9433ad1b479093c096f2c16d3ba2` |
| instruction | `prior_auth_um/tasks/pa_t030_t030_o002_p01_triage_payer/instruction.md`；SHA `8abfcba1eac2de06fae0959f78e09a20132708af297835cadc12214a6bf2d723` |
| tool reference | 同任务 `tool_reference.md`；SHA `e7a7655dc189a18ddbb1a44cd26feb56554221ca934be2e92d5fceb63b20ce48` |
| world 文件（只哈希，不解析结果） | `prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json`；SHA `fbf01417941c7042f8774bd46f8a110c6cff58cb88ebdda297bb23367d9be1b5` |
| 手册 | `data/skills/managed-care-operations-handbook`；按现有 `_handbook_digest` SHA `3508bc8c723b1f701c9ebefe3e8edd76e89cfe00af2dbf53a0668e5809cc0689`，本地受限、不分发 |
| runner/world 镜像 | runner `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`；world `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`；本轮只确认存在/arm64，未启动 |

`role_runner.py` 原样转发 argv 给包内入口，已能承接两个CLI开关；但是 `role_operator._config()` 的可选字段只有 history/state/local_q_root，生成 runner argv 时没有 `--input-summary`/`--output-recovery`。因此直接改配置会被拒绝，不改配置则仍关闭；不能把这种 C 当成能力探针。`GoChiHarness` 同样没有两开关透传；默认关闭正式路径可另验，若最终采用能力则须另列 harness 接线并产生新包身份。

本轮不补生产功能。第8节给 DeepSeek 的唯一必需有界任务是开发操作者显式透传、互斥/用途检查和定向 Docker 验证；不重写 journal/runtime，不造绕过准入的探针。若只改包外 operator，重新证明内包身份不变；若触及任何包成员，重建/新 B，旧 frozen 清单失效。当前 B 入口不受此缺口影响。

## 6. 最小验证提案的结论边界

详细输入、入口、计数、用量、收尾和批准语句只维护在[新草案](../openspec/changes/validation-preparation/proposal.md)。顺序为 C1决定 → 新身份 coding-B → 包外接线离线通过 → 单独摘要探针 → 审阅其收尾 → 单独恢复探针；后两者也可择一或都不采用。**当前推荐只审批第一步B，最多6个物理HTTP；不一次申请旧计划全部可选实验。**

两探针各最多1逻辑CHI run/50物理HTTP，包含确认/summary/continuation，payer患者辅助0。若以后分开批准全部三步，条件总上界为106，非额外各加50+摘要/续写，也非本轮授权。首轮自然未触发则“未覆盖”，不追加 run、不降低预算/输出、不提高强度、不追加到触发为止；恢复只取实际出现的A或B模式，不凑另一个模式。端点兼容、模型摘要忠实度、净费用收益分别判定，后两者不由一次兼容探针自动通过。

## 7. Z4–Z8交付对接及材料提纲

| 阶段 | 必要项 | 可选/可延期与边界 |
| --- | --- | --- |
| Z4业务/效果 | 最终实际采用配置的工程/业务闭环、全部失败/unknown/未运行分母、角色支持范围和负结果；复用身份适用的历史，无法复用的明确缺口 | F1–F6最多12C不是必跑；Y off/shadow未决保持off；摘要忠实度/净费用只在拟采用或主张收益时必须另取证，不必为默认off冻结做全套实验 |
| Z5未见集 | 项目既定9题/每角色3题仍未完成；采用前从公开索引登记污染记录、资源/检查/同候选并获具体许可，新世界各一次，所有结果入分母 | 非官方强制75题公开包；如果缩减9题计划，必须明确用户裁剪及泛化限制，不把已见t030改名为未见；本轮没有选/打开9题答案 |
| Z6正式路径/F.5 | 最终release、依赖/镜像/资源供应、显式Harbor agent注册、非秘密配置、空state/B准入与日志持久化、真实Trial输入/工具/结果/trajectory/context、失败传播和owned清理；最终默认off/采用配置须一致 | 可将正式每角色一次与符合条件的Z5同次取证（计一次）；其他架构、全量75题、硬daemon故障扩展非本轮必跑。CM若用开发Go患者须如实标记；官方Anthropic患者和judge授权/环境单列 |
| Z8材料 | 精确候选/复现入口/资源责任、方法架构、实验分母/负结果/费用/unknown、内容与官方未评、用户验收和最终交付动作 | 先形成下列结构，不声称Writeup、技术报告、正式运行、评分或投递已完成；公开全量结果依历史规则核对为可选，提交前需重核现行规则 |

Z8 现可使用的提纲：①任务与三角色边界；②入口→身份/供应→SDK→wire计量/guard→reserve/settle→整批工具→终态/清理；③输入保护/摘要和输出恢复的默认off与失败设计；④分层证据（原Q–W真实开发、Y离线shadow、F/M/C及PR51离线可靠性、本轮包冻结）；⑤全分母实验表（源码/包、角色/任务、模拟器、物理请求/token、三项USD、工程/业务/内容/官方各列）；⑥旧unknown、C5/临床充分性、端点/Harbor/依赖限制；⑦安装/外部资源、AI分工、许可和最终回执。历史数值只从对应报告取，不合并成新候选成绩。

本轮只更新学习账本的下一入口，不作新功能教学或掌握认证。后续新接线/重大修复验收后，再按学习约定集中讲解；普通准备和测评不默认小测。

## 8. 给DeepSeek的有界执行Prompt（离线，尚未派发）

> 先读AGENTS、COLLABORATION当前方式、REVIEW_STATE、本报告第5节及新审批草案。核对本PR用户合并和实际origin/main，从最新main新建deepseek/validation-probe-wiring；仅一个写入者，有并行工作就隔离工作区/测试目录。只做包外role_operator配置与argv接线，不恢复真实调用。
>
> 新增可选input_summary/output_recovery，值只接受对应固定policy version，缺省不传；二者互斥，并拒绝与Y shadow组合、非CHI或非法用途。保持所有模型/端点/thinking/high/主确认辅助额度/输出/context/时间/0重试不变。不要把开关加进已固定go-chi-entry profile，避免无必要的包身份变化；显式验证落在journal.launch及实际guard路径，防止只在配置宣称开启。
>
> 在Docker/Python3.12、禁网无Key/world完成配置错误在创建world/读取凭据前拒绝、旧配置argv不变、两种合法开关分别只透传一次、互斥和shadow拒绝、实际role_runner→包内entry接线的合成证据；复用现有SDK MockTransport摘要/恢复，保留未触发/取消/未知和清理限制。停止生产写入后固定候选、给diff/精确命令/退出码/包身份比较。只变operator时41成员必须逐字不变；若发现必须动包/harness，先报告具体缺口和新身份/B影响，不顺带扩大。
>
> operator/controller的既有未锁依赖风险单列，不全面重构，不修改旧账/pending/authorizations，不读Key/.env、不发模型/summary/continuation、B/C/Trial/world/judge。不得解析隐藏expectations选动作或改结果，不重问Go用途/隐私，不恢复Y实验。将实现与证据交GPT定向审核，用户最终合并。完成离线接线也不取得真实探针许可；仍逐阶段按具体审批执行，未知立即停止。

## 9. 未完成项与收口

此冻结仅为后续验证的离线交付候选：缺新B、C1处置/特定授权来源、包外开关透传、真实摘要/恢复兼容、摘要忠实度及净费用、C5会话支撑、最终角色业务/未见证据、正式Harbor/配送/F.5与Z8实物材料。所有开关默认off，`official_reward=null`；真实模型/摘要/续写/B/C/Trial/world/判分/发布均为0。本轮不重写旧审批包或历史结论，不merge、不auto-merge。
