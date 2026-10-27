# 真实 B/C 接入与首次试跑审核

日期：2026-10-27。最终交付候选 `ba6786717a624d328d3f9bc1296392f9637888da` **独立离线验收通过**。真实 B 在前一固定候选上成功；唯一 C 尝试在官方 bootstrap 阶段失败、模型未启动，暴露的挂载问题已修复并离线复验，未重跑真实 C。代码、自测和真实运行的结论分别记录，不以合成材料代替真实回执。

## 授权与基线

用户在本对话明确同意恢复真实模型 API 小额 B 联调，以及 B 成功且预算足够后的一次官方任务无评分 C。两项共享 5 CNY，代码开发费用另计；官方判分继续暂停，F.5 最终冻结留待真实反馈后处理。真实试跑以自主系统执行，不人工代选业务动作或修改结果。G/H 与原评测包 record_only/null cap 保留；新增本地真实入口，不放开旧 live 门禁。

主代理通过 GitHub API 核对 PR #12/#13 均已合并，fetch 最新主线 `9b917f08a465091456329a1dd2d14c2f47a8b266`，从干净工作区建立 `codex/real-b-c-ungraded`。一个 `gpt-6-luna` / `high` 子代理负责实现/离线自测，主代理负责规格、固定候选独立审核、真实运行、教学和 GitHub。子代理不读取凭据或发送真实请求。

## 实际前置核对

- 复用 Python 3.12 dev、controller 与固定官方 world 镜像，没有重建、安装新依赖或重新下载受限资源。主代理检查时没有遗留 CHI 容器。
- dev ID：`sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`；controller ID：`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`；world ID：`sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`，均 Linux arm64。
- SDK 复用 H 安装验收的新卷 `chi-h-root-model-deps-20261027-v1`；固定 vendor 为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，版本来源见 [H 审核](official-launch-reproduction-review.md)。
- 起初项目 `.env` 与进程环境均无 DeepSeek Key。用户回复已配置后，主代理只在禁网 Docker 内输出文件可读/Key 已配置两个布尔值，核对成功；没有打印密钥值，也没有因此发送请求或自动取得 C claim。
- 重新核对官方 [价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[模型元数据](https://api-docs.deepseek.com/zh-cn/api/list-models/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode) 和 [请求契约](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)，既有 Flash/thinking/high、容量和 CNY 峰值价仍符合文档。离线验收后才以真实 Key 执行固定域名的 GET `/models`、`/user/balance`，均 HTTP 200；Flash 名称为 `DeepSeek-V4.1-Flash`，context 1,048,576、output ceiling 393,216，支持 high，余额覆盖本轮 5 元。模型别名仍非不可变快照，不把文档中的构建后缀冒充 provider 已回报的具体版本；账单金额没有核验。
- 已读 Agent 可见 instruction/tool_reference 与固定 local-tool 源码，没有读取 hidden expectations。所选任务是 `pa_t018_t018_o001_p01_new_referral_provider`；官方本地工具原样提供任意 shell/Python/路径操作，因此选择独立 runner + 受限资源工具。这是自有受控配置，与原版全部本地工具能力不同，不能声称性能等同。

## 规格与证据边界

行为契约见 [J 设计](../openspec/changes/bootstrap-baseline/design.md#j首次真实-bc-的受控接入)、[J 任务](../openspec/changes/bootstrap-baseline/tasks.md#j-first-real-model-integration-and-one-ungraded-official-task) 和 [J 契约](../openspec/changes/bootstrap-baseline/specs/benchmark-readiness/spec.md#requirement-bounded-real-development-model-and-official-task-runs)。

新 real 账目必须与 synthetic/evaluation 独立；首次 prior=0 来自本项目此前没有任何真实 B/C 的审核事实，需显式初始化并保存来源。B/C 的固定预算根与 C claim 不随 run-id、日志根或重启清零。请求先持久 reserve，再发送；响应先核算用量，再验证整批工具；unknown/pending 停止并保留。provider usage 是实际响应中的回报，按文档价得出的金额仅为估算，不是账单。

真实 B 目标为模型自主发起至少两次有依赖工具往返并给出非空最终响应。只有真实 B 成功、身份一致且预算足够才创建 C。C 使用新官方世界，模型自主操作 provider MCP；runner 与 controller 隔离，工具不可读凭据/socket/vendor/fixtures，世界不接收模型/judge 凭据。记录业务观察与运行结果，官方 reward 为 null。

## 固定候选与独立离线审核

实现代理停写后，主代理显式提交三个生产/测试文件，固定首候选 `0a0d69d233226305474160690c1ecdd3ead3a825`，从 Git archive 导出只读快照。独立检查没有挂载项目 `.env` 或旧运行账目，也没有网络/Docker socket；SDK/vendor 分别只读挂载，测试 `runs` 挂到本轮独立审核目录，全部状态都是合成外部边界驱动的测试材料。

首次启动测试容器时因快照内缺少 data 挂载点而退出 125；补建空挂载点后实际重跑。固定快照全项目结果为 **240 passed / 124 subtests，退出 0**。主代理随后针对差异独立编写故障驱动 `root/check_candidate_faults.py`，借用测试 Fake 类型作外部刺激，但由主代理独立设置故障/预期；七项全部复现缺陷，驱动退出 1，不能据全量测试通过验收。

| 首审问题 | 独立证据与影响 |
| --- | --- |
| R1：入场账目浅校验 | 将 cap 改成 50，preflight 仍 known；C controller 用该 cap 算余额，worker 才拒绝坏状态，会浪费一次 C claim/世界创建。要求完整、无副作用的状态验证先于 claim/资源 |
| R2：碰撞时误清理 | 在资源 preflight 注入同名世界冲突，没有 claim/create，finally 仍调用按 run-id 清理。真实 helper 可能删除已有其他运行资源；要求只清理本次已确认归属的资源 |
| R3：日志/账目失败误报成功 | 分别注入缺 trace、run_log 写失败、journal finalize 失败，三种 C 都仍 completed_ungraded/退出 0。要求完整必需产物及持久化/清理成功，失败非零、不发布 B 成功凭据，主错与附加错分开 |
| R4：B 依赖往返验证不足 | 首轮同批 lookup+猜中输入的 transform，第二轮 final，仅两次模型请求也被记成功。要求首个结果实际回传模型后才允许依赖工具，至少两次不同轮的往返 |
| R5：单次用量混入累计 | Mock B 为 21 input/9 output，C 自己为 14/6，但 C run_doc 报 35/15；费用也混成 campaign 累计。要求每 run 与共享 campaign 分栏、receipt 同步准确 |

首审实际检查命令均在 Docker 内：`/opt/venv/bin/python -m pytest -q -p no:cacheprovider` 与 `/opt/venv/bin/python /checks/check.py`；只读源为 `root/candidate-1/chi-agent`，后者驱动/完整结果为 `root/check_candidate_faults.py`、`root/evidence/candidate-faults.json` 和 `candidate-1-faults.log`。正常测试日志为 `candidate-1-pytest.log`。原始内容在忽略的 `runs/real-b-c/` 下，不上传。R1–R5 已交回同一实现代理，另要求 claim 目录持久化、本地工具 dispatch 关联和 worker 内部参数边界修正；没有因此开启真实调用。

### 首轮修复复验

实现代理停写后，主代理读取修复差异并固定 `e481379130f20c45e557280bf0760eeb31f4c6d0`，再次从 Git archive 导出只读快照，使用新的隔离测试目录重跑相同七项，**7/7 通过**。预算前置完整校验、精确 handle 清理、产物/持久化失败非零、B 不接受同批预猜依赖和 run/campaign 用量分列已实际复验。claim 文件增加父目录 fsync；local dispatch 关联真实 call-id；worker 内部参数固定校验。证据为 `root/evidence/candidate-2/candidate-faults.json` 与 `faults.log`。

继续核对修复后的证据语义时，主代理用两个小型故障场景复现：**R6** reserve 后 unknown/finalize 时 usage 为 null，但运行 estimated_cost 仍是 0，缺少 known_prefix 字段；**R7** 网络创建主错后，claim 失败记录再次写盘出错会覆盖 primary_error_code。要求未知完整总额为 null、已知前缀独立保留；原始主错与附加持久化错误分开。两项结果均为失败，驱动退出 1，详见 `root/check_remaining_evidence.py`、`root/evidence/candidate-2/remaining-evidence.json` 与 `.log`；已交回同一代理作最小修正，尚不验收 J 或恢复实际请求。

### 首次真实运行的固定候选与独立验收

最终修复 `c4bf950818e71a21d849d7a6e745b75d4f6b6c42` 只改真实运行证据与针对测试。主代理读取差异后再次 Git archive 到 `root/candidate-3/chi-agent`，用三份新的隔离输出独立执行全项目、原七项故障及 R6/R7 两项检查。结果为 **244 passed / 124 subtests**，九项独立故障全部通过，三个驱动均退出 0。命令沿用前述 Docker 禁网/只读源，无真实凭据；SDK/vendor 分开只读，普通回归额外挂授权 data，故障检查只使用最小合成投影与 Mock Docker/MCP/HTTP。

R6 已将 per-run/campaign 完整 totals 与 known_prefix 分栏，unknown 的完整用量/费用为 null，已知前缀及 pending 保留；重复 finalize 不丢前缀，重启仍拒绝。R7 原始网络错误保留在 primary_error_code，claim 状态持久化失败另记 persistence_error_code。R1–R5 的先前七项未回退，B 依赖轮次、真实 local/MCP dispatch、精确资源归属与失败非零均实际复验。

证据为 `root/evidence/candidate-3/pytest.log`、`faults.log`、`candidate-faults.json`、`remaining-evidence.log`、`remaining-evidence.json`；快照与测试账目均在本轮 root 目录，不复用实现代理证据。独立只读凭据解析检查也确认生产 helper 与用户文件的解析结果一致，仅输出布尔值，未输出密钥。正式调用前再次确认三份被测代码与固定 HEAD 无差异；此后真实 B/C 使用相同实现身份，文档更新不替换被测源码。

主代理已独立执行与候选无关的环境/SDK预检：固定卷中实际 SDK 版本与 H 相同，MCP constructor 支持 `max_retry_attempts=0` 与异常传播配置，而 OpenAI 客户端默认重试为 2，真实适配必须显式设为 0。证据位于忽略目录 `runs/real-b-c/root/evidence/sdk-contract.json`；这只是接点检查，不能代替真实循环验收。

另在实际 Docker 引擎上用空合成 HTTP server 验证计划网络布局：server 只连 internal bridge，runner 先连默认 bridge 再连接该 internal 网；runner 可访问内部 HTTP（200）及官方文档外部 HTTPS（200），进程退出 0，两个容器和网络全部清理。没有密钥、官方世界或模型请求，不能当成 MCP 协议/真实 trial 通过。命令由 controller 镜像在容器内执行 `root/check_isolated_network.py`，socket 仅给此操作程序；脱敏结果为 `root/evidence/isolated-network.json`，脚本/原始证据不上传。

## 真实 B

实际运行 `b-smoke --run-id j-b-20261027-001`，控制器退出 0，状态 `smoke_completed`。初始化前核对真实生产根没有账目/claim/receipt、此前阶段没有真实 B/C，随后显式执行 `init-prior --source reviewed_project_campaign_history_no_real_B_or_C_calls_2026-10-27`，只把该审核历史作为 prior=0 的来源，不读取任何 synthetic 账目。preflight 核对身份与 5 元共享 cap 后发送真实请求。

模型自主执行三轮：第一轮选择 `smoke_lookup`，结果实际进入第二轮请求；第二轮才选择 `smoke_transform`，把前一工具原值作为输入，结果实际进入第三轮；第三轮返回非空最终响应。两个真实 call-id 均有 validated/started/returned 证据，结果历史的 observed round 分别为 2、3，不是同批猜中输入的伪依赖。真实 provider 响应的累计用量为 **4,976 input / 214 output tokens**，SDK 另回报 cached 2,944；保守估算不扣 cache，以峰值价得到 **0.011664 CNY**，并非账单金额。

请求全部 settled，`pending=null`、`usage_complete=true`。输出、trace、run_log、run_result 与 journal 都保留，B 成功回执绑定相同代码/profile/vendor/SDK 及五项产物哈希；runner 退出 0 且已删除，没有清理错误。真实元数据/预检证据在 `root/evidence/provider/`；运行 journal 为 `runs/j-b-20261027-001.json`，原始产物为 `j-b-20261027-001/runner-logs/`，成功回执为 `b-success.json`。本报告所有相对原始路径均在忽略目录 `runs/real-b-c/` 下。

## 一次无评分 C

真实 B 通过后重新执行只读 preflight，已知剩余估算预算 4.988336 CNY，可覆盖一次最大请求预留 2.162688 CNY。随后启动唯一一次 `c-once --run-id j-c-20261027-001`，代码仍为 `c4bf950818e71a21d849d7a6e745b75d4f6b6c42`；控制器退出 **1**，`status=failed`、`primary_error_code=orchestration_failed`、`exception_type=AEnvironmentError`。world 已创建并启动，但官方 bootstrap 退出，未到 MCP ready；runner 未创建，模型没有收到任务或发起 C 请求，不能称自主 Agent 执行通过。

**R8：官方 workspace 重建与 bind mount 冲突。** 保留的 `runs/a-environment/j-c-20261027-001/container.log` 显示固定 `core/context.py::_reset_workspace_root()` 先 `shutil.rmtree(self.workspace_root)` 再 mkdir；controller 将 `/logs/artifacts/workspaces` 本身作为挂载根，删除该挂载点时触发 **OSError errno 16 / EBUSY**。这是本次真实运行发现的集成缺陷，先前 Mock Docker/合成网络没有覆盖官方目录重建与实际 bind 的交互。

从 claim 时间 `05:11:40.732449 UTC` 到清理后终态 `05:11:46.490095 UTC` 为 **5.758 秒**，仅是该区间，不代表含投影准备的端到端时长。B 没有独立持久化端到端计时，本报告不补造数值。世界/网络精确 handle 均在 finally 删除，日志捕获成功、清理错误为 null；主代理又按回执中的精确资源 ID 核对没有遗留。C claim 为 `failed_or_uncertain_claim_retained`、`replay_allowed=false`，没有 C provider journal。B/C 共享账目仍只有 B 的三次 settled 请求，累计估算 **0.011664 CNY**，无 pending；official reward 保持 **null**。

实际编排结果为 `j-c-20261027-001/orchestration.json`，唯一 claim 为 `c-once-claim.json`，provider 运行前后预检在 `root/evidence/provider/`，均属忽略的真实证据。失败没有自动清 claim、重置账目或换 run-id 再试。

### 启动失败后的最小修复与独立复验

同一实现代理只改真实入口和针对回归，停写后主代理读取差异并固定新候选 `ba6786717a624d328d3f9bc1296392f9637888da`。world/runner 改为共享本次专属 artifacts 父目录，bind 到 `/logs/artifacts`；`workspaces` 是其可删除重建的普通子目录。本地文件工具仍只接受 `/logs/artifacts/workspaces/<case>/{provider,shared}`，未放开 artifacts 兄弟日志、payer、路径上跳或符号链接。新增测试调用固定官方 `ServiceContext._reset_workspace_root()`，并检查两个容器的同源父目录 bind。

主代理另写独立 `root/check_workspace_mount.py`，只使用合成文件、固定官方方法 AST 和实际 Docker bind，不运行官方世界/任务、MCP、模型或判分。首次检查误将 world 根设置只读而得到 EROFS，调整为与真实 world 相同的可写根后：直接挂 `workspaces` **实际复现 errno 16**；挂父目录时官方方法成功删除/重建子目录、保留父目录兄弟文件；随后只读根 runner 看到 world 标记并写入 shared，两个容器均删除。结果为 `root/workspace-reset-check-v2/result.json` 与 `root/evidence/workspace-mount-check-v2.stdout.json`。

从新 SHA 的 Git archive 导出 `root/candidate-4/chi-agent`，禁网、只读候选、独立输出、无真实密钥/socket/生产账目，主代理全项目结果 **245 passed / 124 subtests**，R1–R7 的九项独立故障全部通过，退出均为 0。补充驱动首次漏挂 `/evidence` 而写结果失败；补上输出挂载后用新隔离目录重跑，保留前后日志。最终证据为 `root/evidence/candidate-4/pytest.log`、`faults-final.log`、`candidate-faults.json`、`remaining-evidence-final.log` 与 `remaining-evidence.json`。独立复验后没有继续修改代码。

真实调用仍只属于旧候选；新 SHA 的验收范围是 **R8 修复的离线代码与实际合成 bind 检查**，不是新候选真实 B/C 成功。原账目、B 回执和 C claim 保留旧源码身份；修复后的只读 preflight 拒绝继承该运行身份。再次真实尝试需要另行明确授权和可审核的身份/累计费用接续方案，不通过删除状态绕过。

## 交付与限制

本地原始轨迹、手册、数据、vendor、凭据和导出包不上传。真实 B 成功说明认证与模型工具闭环已连通；本次 C 未进入业务执行，所选任务效果、修复后的真实 C、官方判分、主办方私有评测、F.5 最终冻结和其他架构仍未验收。不会因环境错误填写 reward=0 或声称官方通过。交付使用 base=main PR，由用户决定合并。
