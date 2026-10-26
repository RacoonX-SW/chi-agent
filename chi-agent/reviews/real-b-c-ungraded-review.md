# 真实 B/C 接入与首次试跑审核

日期：2026-10-27。开发/返工中；首候选 `0a0d69d233226305474160690c1ecdd3ead3a825` 独立首审未通过，R1–R5 待修复。尚未发送真实模型请求、初始化生产真实账目或占用 C。代码、自测和真实运行的结论在本报告分别记录，不以合成材料代替真实回执。

## 授权与基线

用户在本对话明确同意恢复真实模型 API 小额 B 联调，以及 B 成功且预算足够后的一次官方任务无评分 C。两项共享 5 CNY，代码开发费用另计；官方判分继续暂停，F.5 最终冻结留待真实反馈后处理。真实试跑以自主系统执行，不人工代选业务动作或修改结果。G/H 与原评测包 record_only/null cap 保留；新增本地真实入口，不放开旧 live 门禁。

主代理通过 GitHub API 核对 PR #12/#13 均已合并，fetch 最新主线 `9b917f08a465091456329a1dd2d14c2f47a8b266`，从干净工作区建立 `codex/real-b-c-ungraded`。一个 `gpt-6-luna` / `high` 子代理负责实现/离线自测，主代理负责规格、固定候选独立审核、真实运行、教学和 GitHub。子代理不读取凭据或发送真实请求。

## 实际前置核对

- 复用 Python 3.12 dev、controller 与固定官方 world 镜像，没有重建、安装新依赖或重新下载受限资源。主代理检查时没有遗留 CHI 容器。
- dev ID：`sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`；controller ID：`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`；world ID：`sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`，均 Linux arm64。
- SDK 复用 H 安装验收的新卷 `chi-h-root-model-deps-20261027-v1`；固定 vendor 为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，版本来源见 [H 审核](official-launch-reproduction-review.md)。
- 起初项目 `.env` 与进程环境均无 DeepSeek Key。用户回复已配置后，主代理只在禁网 Docker 内输出文件可读/Key 已配置两个布尔值，核对成功；没有打印密钥值，也没有因此发送请求或自动取得 C claim。
- 重新核对官方 [价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)、[模型元数据](https://api-docs.deepseek.com/zh-cn/api/list-models/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode) 和 [请求契约](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)，既有 Flash/thinking/high、容量和 CNY 峰值价仍符合文档；认证、实际 metadata/model、真实 usage 和账单尚待实际调用验证。
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

主代理已独立执行与候选无关的环境/SDK预检：固定卷中实际 SDK 版本与 H 相同，MCP constructor 支持 `max_retry_attempts=0` 与异常传播配置，而 OpenAI 客户端默认重试为 2，真实适配必须显式设为 0。证据位于忽略目录 `runs/real-b-c/root/evidence/sdk-contract.json`；这只是接点检查，不能代替真实循环验收。

另在实际 Docker 引擎上用空合成 HTTP server 验证计划网络布局：server 只连 internal bridge，runner 先连默认 bridge 再连接该 internal 网；runner 可访问内部 HTTP（200）及官方文档外部 HTTPS（200），进程退出 0，两个容器和网络全部清理。没有密钥、官方世界或模型请求，不能当成 MCP 协议/真实 trial 通过。命令由 controller 镜像在容器内执行 `root/check_isolated_network.py`，socket 仅给此操作程序；脱敏结果为 `root/evidence/isolated-network.json`，脚本/原始证据不上传。

## 真实 B

未执行；尚无真实模型用量或费用。

## 一次无评分 C

未创建；C claim 未占用。必须先取得符合条件的真实 B 证据。

## 交付与限制

本地原始轨迹、手册、数据、vendor、凭据和导出包不上传。验收范围和未决项按实际结果更新；官方判分、主办方私有评测、F.5 最终冻结和其他架构仍须独立处理。不会因环境/工具/模型错误填写 reward=0 或声称官方通过。
