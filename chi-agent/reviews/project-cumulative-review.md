# 全项目累计审核：固定主线初审

日期：2026-11-04。固定主线`0a8449ea410aafa74001141360c51f7d85c060d5`（PR49合并），M4实现`450e574`。**初审未通过候选冻结：R1必须修复，R2须在只读汇总收口前修复。** 本报告不把合并或作者自测当作整体验收。生产源码未改；DeepSeek仍负责返工，用户最终合并。

## 1. 范围与证据分工

PR41、42–49的交付已进入主线。按用户安排，M5/M6既有Gemini复审结论保留，不重复原包验收；本轮在全部实现合并后检查集成边界，补充独立故障反例及固定包验证。

累计范围：以既有阶段报告为历史证据入口；独立检查M4/M6新增代码、入口→SDK→guard/contract→reserve/settle→diagnostic/inspect的调用链，补读辅助transport、summary/recovery、发布allowlist、配送和Harbor启动边界。用全仓可用离线测试、独立反例、旧v1合成证据、静态依赖闭包与隔离包抽验相互核对。没有将65个模块全部逐行重审，也不把旧阶段真实结果扩大为新版本已实跑。

没有安装/下载新依赖、读取Key、真实模型/摘要/续写、world、B/C/Trial或判分。历史真实账、费用、pending和未知处置不改、不换根。只挂固定vendor源码，未挂原运行账户或临床资料。

## 2. Findings

### R1 [P1] 辅助请求错误分支缺少导入，覆盖原错误并丢诊断

位置：`scripts/go_chi_auxiliary.py:97–99`，调用`cause_for_code`却没有导入。正常返回分支不触发，因此正常SDK/包身份可以通过；任何已reserve的辅助错误进入这里都会发生NameError，被同层except误判为`chi_evidence_persistence_failed`。实际无文件系统写入失败，诊断函数还未被调用。

独立MockTransport实证：

| 原场景 | 实际对外码 | 请求状态 | diagnostic引用 | pending |
| --- | --- | --- | --- | --- |
| 辅助ReadTimeout | chi_evidence_persistence_failed | pending | null | 原r/1保留 |
| 辅助响应length，可信usage | chi_evidence_persistence_failed | settled | null | null |

现有pytest函数`test_cancelled_auxiliary_keeps_pending`也直接失败：pending正确保留，但transport.error应为`chi_aux_cancelled`却变成持久化失败。取消异常仍向上传播，没有证明发生重复请求或丢失已知费用；问题是原错误/诊断语义被破坏。

返工：补齐实际导入，并给辅助取消、网络、未知usage、可信usage但非法响应分别断言原安全码、有限cause、诊断留证、共享/辅助计数及settle/pending。真实诊断写入故障另测，不能和NameError混为同一结果；每次下层至多一次，不重试/清账。

### R2 [P2] M6验证与投影不使用同一账本快照

位置：`scripts/go_chi_run_summary.py:162–164`。`inspect_history`持锁校验旧账后释放锁，随后`_state_object`重新打开当前账但不再校验预期hash/完整历史，再把新内容和旧inspection拼接输出。

独立确定性反例：第一次真实`inspect_history`完成后，在第二次读取前由另一个真实`ChiJournal`写入者合法追加并结束一个新run；两个journal均使用原严格API和同identity，无打桩校验成功。M6返回旧`accounting_sha256`，runs却包含`new-uninspected-run`。这证明的是一致性窗口，**不是M6自己写了输入文件**；推进账本的动作来自反例中的独立写入者。

实证旧hash=`911da14607c57e428cafea9496e237ebc0d482f15367d93042324d94a8861334`，实际投影账hash=`482eac9c9236326e79d32c900121f954dd6d888e1aa5916ce66ad1b5c66b8d6f`。返回`validation.status=inspected`和旧hash不能证明新投影已验证。

返工：投影必须绑定同一份已校验的不可变快照；或在同一只读锁范围重读、按预期hash及严格规则校验所投影的同一字节。不能仅在释放锁后再次解析，也不能用无限重试掩盖并发。保持原CLI/输出schema、execution_allowed=false与只读性质；新增确定性并发写入/拒绝反例，结果应为完整旧快照或明确安全失败，不能混合两个版本。优先包外最小修复，若改变包内reader接口需实际比较新身份并记录。

### R3：验证命令覆盖缺口与短状态过期

作者报告的`unittest discover`没有收集pytest函数/参数化用例；这次R1正由原有pytest函数检出。不能据553个unittest结果将全部pytest路径写成通过，2个既有anthropic错误也不是本次取消失败的原因。返工必须跑适用pytest集合，并保留环境错误和skip，不能删掉失败用例。

主线REVIEW_STATE仍写M4“仅契约/未实现”、PR48 open、实现分支未同步；与PR49已合并相矛盾。本轮短状态更新只修当前事实，旧报告原结论保留；“tasks已勾选”不代表累计冻结通过。

## 3. 环境与独立结果

Python3.12.15/Linux arm64；镜像`chi-agent-a-control:latest`，digest=`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`。模型/PDF只读卷`chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`；vendor干净固定`4444a07fa68a4f1623f841a292a54e284fc8e7f7`。SDK与固定_identity校验一致，未安装anthropic/Harbor/controller依赖补齐环境。

候选由`git archive 0a8449e`生成，Docker只读挂载，无本地未提交实现混入。日志和复现脚本集中忽略目录`runs/project-cumulative-review-20261104/`，不上传原始轨迹或vendor。

| 检查 | 本轮实际结果 |
| --- | --- |
| 全tests pytest | 2个收集错误：dev_patient_adapter、dev_patient_network导入anthropic失败；收集中止，不能算完整执行 |
| 显式排除上述2模块后的全仓pytest | **1 failed、879 passed、11 skipped、259 subtests passed**，24.50s。失败为R1辅助取消；原日志保留 |
| 11 skip | 5 Harbor overlay、3旧Go operator Docker SDK、3role operator controller依赖；不是通过 |
| 独立R1/R2脚本 | 2个辅助故障及1个并发窗口重现成功；脚本成功退出表示缺陷已证明，不表示被测系统通过 |
| 静态import inventory | 65模块、35进包Python模块，closure_gaps=[]、unknown_imports=[]；docker/huggingface_hub仍为既有未锁外部风险，命令exit1，不能写整个检查通过 |
| 隔离Go真实身份 | 41文件；manifest `8cb711fe77eb7a346fe71f64a005a52e979f97643de3e13aff12e461f01c9f0b`；identity `b4741cce241291d68c6c2761c12f892da95f9057487b06e8bb68dd7faafd202a`，与M4报告相符 |
| 无项目源码挂载的隔离SDK | summary SDK、recovery SDK、M4坏批检查共**29 passed、9 subtests passed**；固定真实SDK+MockTransport，未触发真实端点 |
| 旧evaluation隔离身份 | 14文件manifest `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`保持，真实_runtime_identity通过 |
| 基线旧v1证据 | 复用此前由旧主线21ec34c生成的closed/unknown/recovery合成材料，共21文件；新reader inspect前后hash/文件集合不变，unknown仍拒绝新attempt；未读取真实旧账 |

套件重叠，数量不相加。隔离包仅挂包、五个测试辅助文件、固定依赖/vendor；测试导入的go_chi_*均来自包，未挂整个项目源码。包身份通过不证明辅助失败分支正常。

## 4. 关键复验命令与失败留存

统一Docker限制：`--network none --read-only --tmpfs /tmp`，`PYTHONDONTWRITEBYTECODE=1`；候选挂`/workspace:ro`，结果挂`/workspace/runs:rw`，模型/PDF/vendor只读。`PYTHONPATH=/audit:/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src`。固定镜像的`/opt/venv/bin/python`执行：

```sh
python -m pytest -q -rs -p no:cacheprovider tests
python -m pytest -q -rs -p no:cacheprovider \
  --ignore=tests/test_dev_patient_adapter.py \
  --ignore=tests/test_dev_patient_network.py tests
python /audit/repros.py
python scripts/import_inventory.py --root /workspace --json
```

`evidence/full-pytest.log`保存原收集失败；`available-suite.log`保存实测1失败；`repros.log`保存缺陷结果；`import-inventory.json`保存未锁项。复现脚本首轮漏挂固定依赖卷导致httpx导入失败，`repros-missing-overlay.log`保留；补足原只读overlay后复现成功，没有安装依赖或修改生产代码。

隔离包使用`/package/scripts:/audit`及原依赖/vendor路径，运行`audit/package_identity.py`（分别PACKAGE_KIND=go/evaluation），以及：

```sh
python -m pytest -q -p no:cacheprovider \
  /audit/test_go_chi_summary_sdk.py /audit/test_go_chi_recovery_sdk.py \
  /audit/test_go_chi_diagnostic_causes.py
```

旧合成材料及基线hash来源见[输入摘要报告](input-summary-review.md)第3/4节，不生成新账绕过原未知。当前只读复验日志为`legacy-v1-compatibility.log`。

## 5. 项目剩余工作及执行顺序

| 优先级 | 工作 | 本轮判断 |
| --- | --- | --- |
| 立即 | DeepSeek修R1/R2、按R3补实际pytest验证，Gemini复审 | 有具体证据的收口返工，不新增M7或重做M1–M6；保留失败，重新比较包身份 |
| 随后 | GPT针对返工差异复验并关闭累计阻断，冻结最终候选 | 不重演全部历史付费任务；冻结结论依新候选，不倒写本次未通过 |
| 真实验证前 | 历史unknown处置/后继特定授权及新身份准入 | C1缺口仍在，不清账、换根或复用旧B声称新版本通过；需具体方案和授权 |
| 获授权后 | 最小真实新B/summary或recovery端点兼容探针，再决定必要的开发回归/未见集 | 本轮零真实调用；两能力首版互斥，不能测试同时启用后写成通过 |
| 正式交付前 | Z4/Z5所需效果与分母、Z6真实Harbor配送/Trial/清理、Z8 Writeup/技术报告/复现材料 | 尚未全部完成；不能用代码包已合并代替正式可复现交付或官方评分 |

Y shadow采用效果、C5交流陈述来源、provider/payer业务充分性、摘要忠实度/净费用、依赖未锁、真实Harbor/控制器硬故障等维持既有未验证边界。默认off保持；不为勾完旧任务无条件启动全部可选实验。没有把用户个人实践/掌握或官方reward升级。
