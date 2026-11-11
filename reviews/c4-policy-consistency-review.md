# C4用途参数一致性：固定候选及独立审核

日期：2026-11-02（Asia/Shanghai）。短状态只见[REVIEW_STATE](REVIEW_STATE.md)，用途及权威来源只见[参数边界契约](../openspec/changes/project-completion/policy-boundaries.md)，本报告保存实际证据。

## 1. 范围与结论

用户确认合并PR43后要求继续开发；主代理现场核实[PR43](https://github.com/xsw932187210-cell/chi-agent/pull/43) merged=true，merge/main为`4495937b5b9e2c1c89392d76c39e3864f05766c8`，从最新origin/main新建`codex/c4-policy-consistency`。原目录`codex/reliability-boundaries`仍在`7984b60`且未提交改动为空；本轮不写其目录，不接管DeepSeek M包。

**C4登记与限定离线一致性检查通过，未发现本范围需要修改的数值漂移。** 只新增`tests/test_c4_policy_boundaries.py`及规格/审核/学习文档；无生产源码、profile、依赖、PACKAGE_FILES或预算策略改变。实际固定实现提交 **`9fc41ca964caeec2a8b0c83b8955727a31a4b83a`**，测试文件SHA-256 `e86dd4bdc799236d2ae9052e6a76f98a0050bd0db0ae4c3dc759bb05a4473d1b`。

仍为主代理规格/任务拆分、独立审核、教学及Git，一个沿用的显式`gpt-6.1-terra/high`实现子代理（最初`fork_turns=none`）编写测试并Docker自测。实现停止后由主代理固定快照、检查差异/调用链、独立复验；作者自测不等于独立验收。

**Key读取0、真实模型/摘要/续写请求0，未启动world、真实B/C、Trial或判分。** C1的payer-010未知及特定后继授权证据缺口保持，不换账根、不清账、不改旧报告，不因合并或本轮通过恢复准入。C2默认关闭/原额度不变，输入自动摘要仍未实现；C5、M2、全面重构均不在本轮。

## 2. 冻结用途与调用链

主代理独立阅读入口CONFIG/profile、go_chi_policy、runtime、guard、journal/load、context、request_budget、患者确认工具及auxiliary/broker/probe、旧及统一operator等待链，冻结上述[契约](../openspec/changes/project-completion/policy-boundaries.md)。同数值按用途分开，未将全部参数集中到一个可自动放宽的配置。

- 入口声明必须经合法manifest和真实`go_chi_entry._identity()`的精确字段/类型比较；`TIME_POLICY`/`RECOVERY_POLICY`与入口JSON严格同步。仅有hash正确不能证明配置可接受。
- SDK负责构造参数，guard独立校验最终wire/response，journal独立约束reserve与历史重载。main/confirmation/continuation共享50，辅助独立10，probe2；合计60不表示主请求可发60次。相同8192输出也不代表同一用途或同一额度。
- 实际输入有效预留为`max(wire.max_tokens, 最低预留)`，确认输出不能只留主循环的最低预留。UTF-8 byte估计、文档context容量和返回usage安全界是不同事实，不称为精确tokenizer或已测可用容量。
- 正常链为声明/身份 → SDK构造 → guard最终wire及context → journal先reserve → 合成下层响应 → 可信用量留证结算 → 响应/工具判断 → 历史重载。坏请求在reserve/派发前拒绝；已发且返回可信usage的超限响应先结算再停止，不能回写为零次或未知。
- 时间参数按socket read、单次总IO、派发准入、运行等待、清理、broker等待分层。新请求准入过期与已准入请求稍后完成不是同一事件，不把所有窗口强行设成相等。

本轮教学沿这条正常与失败链解释了配置声明、独立硬门禁、混合计数和包身份，不安排默认小测；没有用户源码复述/实践证据，不升级为掌握。

## 3. 新增检查及覆盖边界

新增51项参数化测试，独立期望值为冻结用途值，避免从另一实现常量推导同一个错误预期。

| 领域 | 实际检查 | 边界 |
| --- | --- | --- |
| 真实配置漂移 | 源文件复制后改坏数值、bool等值类型、多余字段、嵌套time/recovery，再build/validate出合法manifest；真实_identity拒绝chi_config_invalid；有效包真实SDK/upstream预检通过 | 只改变文件系统ROOT位置，不打桩_identity、_sdk_identity、_upstream_identity；不是只让checksum失败 |
| main/B/confirmation wire | 合法上限及邻值、bool、float、str；实际ChiGuard+MockTransport，journal记录用途/上限 | coding-B以合成length终止并保留结算，不冒充完整真实B |
| 返回usage | 上限及上限+1，含continuation | 一次派发、先settle、再拒绝超限；pending=null，不吞掉已知费用/用量 |
| 中文输入边界 | 实际raw JSON字节和主/确认用途预留，跨越门限时零派发 | 检查启发式byte估计，未运行真实tokenizer/摘要 |
| 患者输出类型 | int成功、float等值/str/bool整链拒绝 | float在context层拒绝，不能误报已穿透auxiliary |
| 用途超时 | 实际request.extensions及asyncio.timeout参数，main/confirmation/patient/continuation | spy调用原timeout，不删除超时；未等待真实数百秒，也未发真实请求 |
| 混合请求账 | 2 confirmation + 1 continuation + 47 main + 10 patient =60总/50共享；多余确认/辅助/主请求拒绝；真实journal重开通过 | 有效恢复许可/parent关联；未跳过load或篡改私有账来凑计数 |
| 思考/重试与旧入口 | 改坏thinking/effort、额外重试字段零派发；旧128/3与Go探针分离 | 不更换运行模型或思考强度 |

既有测试还覆盖probe2、每链1/run2、共享第50次后的length不得追加、取消/未知、准入过期及先准入后完成、SDK/工具门禁。主代理受影响回归实际运行这些测试；没有仅凭作者列出名称认定通过。

## 4. 失败、返工与作者自测

最初静态观察到AuxiliaryTransport比较`8192`时没有在该行显式检查int，作者怀疑`8192.0`可发送。主代理在固定main快照独立复现实际完整链：

| max_tokens | 结果 | reserve / dispatch |
| --- | --- | --- |
| 8192（int） | accepted | 1 / 1 |
| 8192.0（float） | chi_context_budget_invalid | 0 / 0 |
| "8192"（str） | chi_aux_request_invalid | 0 / 0 |
| true（bool） | chi_aux_request_invalid | 0 / 0 |

因此是局部代码观察不足以判断整体漏洞，不是数值漂移，也没有修生产代码。作者`selftest/c4-initial.log`保留**1 failed、27 passed**：测试错误预期更早的chi_aux_request_invalid，实际被context拒绝；改为准确的整链断言。作者最终`c4-final-3.log`为**155 passed、6 subtests passed**，无skip；此前37/38项定向和早期最终日志均保留，不求和。

主代理独立包反例脚本初次错误地用源路径读取导出包runbook，得到8个subtest错误（2个其他测试成功）；修正PACKAGE_FILES源/目标映射后通过。原脚本和失败日志`independent-package-policy-mapping-failure.log`保留，不修改候选、不放宽核心检查。

## 5. 主代理独立环境与结果

所有执行均Docker/Python3.12，禁网、只读源码/包、tmpfs临时目录、专用证据输出；无Docker socket挂入测试容器，无auth/world/真实账户state挂载，无安装/下载/升级。

镜像`chi-agent-a-control:latest` digest `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Linux arm64/Python3.12.15。复用只读model/pdf卷：Agents0.13.6、OpenAI2.36.0、httpx0.28.1；固定vendor clean commit `4444a07fa68a4f1623f841a292a54e284fc8e7f7`。详细环境继承[C3固定环境](c1-c3-admission-package-review.md#5-docker环境与固定身份)，未重装依赖。

固定候选archive SHA-256 `fe8b9255c49c63874470a374469b3c257a5909b1287106a06e7243267a472d63`；独立日志、脚本、快照、两种包在忽略目录`runs/c4-policy-20261102/independent/`，只上传本报告元数据，不上传原始轨迹/vendor。

| 主代理检查 | 实际结果 | 日志 |
| --- | --- | --- |
| 固定main患者类型完整链 | 确认int成功、float/str/bool零派发 | root-evidence/aux-type-baseline.log |
| 固定候选受影响回归 | **382 passed、11 skipped、61 subtests passed** | root-evidence/independent-regression.log |
| 无源码checkout挂载的包独立反例脚本 | **3 unittest通过**，含8种重新合法打包后的配置变异、3种输出预留精确byte边界、真实包身份及独立字面声明 | root-evidence/independent-package-policy.log |
| main基线与候选两包重建/validate | 两种manifest分别逐一相同 | root-evidence/build-baseline.log、build-candidate.log |

11 skips为5项Harbor controller overlay、3项旧Go operator Docker SDK、3项统一role_operator依赖缺失；不当作通过。未锁controller依赖风险保持，不为本包安装或扩大运行权限。上述检查相互重叠、不求和；独立脚本的3 unittest数也不冒称pytest subtests数。

主代理检查了全部新增测试及相关入口，确认ROOT重定位仅为读取真实临时包，不替换身份校验函数。独立包脚本只挂包、审查脚本、依赖和固定vendor，单独追加的坏包有有效manifest，错误码必须为chi_config_invalid。

### 包身份比较

| 对象 | main基线与C4候选共同结果 |
| --- | --- |
| Go包 | 39文件，manifest `e3585b651d443c98ef7e46d17f69ef43617a318456fa9abe2825dac637df9674` |
| 旧evaluation包 | 14文件，manifest `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc` |
| 实际Go runtime identity | `035e3e65d351c40443d5f1b3c2c41c24eb45240efb277b0f54127b587540ee60`；独立脚本实际_identity计算匹配 |

不只因为测试文件在包外就声称身份不变：主代理从基线及候选分别重建，两个manifest实际匹配。C3新身份本来没有新B，本轮身份不变也不能凭空补出新B或解除C1未知阻断。

### 可复现命令

候选及脚本位于`/private/tmp/c4-work`、`/private/tmp/c4-audit`；均已复制到上述忽略证据目录。受影响回归：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v /private/tmp/c4-work/candidate/chi-agent:/workspace:ro \
  -v /private/tmp/c4-work/root-evidence:/workspace/runs:rw \
  -v /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/vendor/chi-bench:/workspace/vendor/chi-bench:ro \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -w /workspace --entrypoint /bin/sh chi-agent-a-control:latest -c \
  '/opt/venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  tests/test_c4_policy_boundaries.py tests/test_config_limits_consistency.py \
  tests/test_go_chi_*.py tests/test_patient_identity_binding.py \
  tests/test_request_budget.py tests/test_role_operator_config.py'
```

无源码checkout挂载的包反例：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/model-deps:/pdf-deps:/package/scripts \
  -v /private/tmp/c4-work/candidate-packages/package-go:/package:ro \
  -v /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/vendor/chi-bench:/package/vendor/chi-bench:ro \
  -v /private/tmp/c4-audit:/audit:ro \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  --entrypoint /opt/venv/bin/python chi-agent-a-control:latest /audit/independent_package_policy.py
```

## 6. 限制及下一步

本包没有真实端点负载、真实tokenizer、模型遵守提示、业务效果、临床批准、真实Harbor Trial/官方评分或干净安装证据。未新增role_runner运行/清理、role_operator等待及bootstrap broker等待的动态时钟测试；契约表相应行是源码核对，不冒充计时验收。未全面审计所有资源容量/所有历史参数，未实施常量归并。

后续离线入口为C5公开P2P实际调用链核查，保留原false，不用隐藏expectations调参或预定业务修法；C2自动摘要另开独立规格。真实运行仍须先补C1未知处置/后继授权证据，再冻结明确候选、用途、次数及停止条件。本PR留用户审核合并，不merge或auto-merge。
