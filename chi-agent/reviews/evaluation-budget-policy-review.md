# 本地与评测预算策略分离独立审核

2026-10-26（Asia/Shanghai）。基线 `ab4cd870cc2fea2e32fd5cdf99ee7e513b5994cc`；主代理核对 PR #9 merged=true，fetch 后从最新 origin/main 建立 `codex/evaluation-budget-policy`，写入前干净。一个 `gpt-6-luna` / `high` 实现子代理，主代理负责规格、独立审核、教学、文档及 GitHub。

结论：**F.2–F.4 的代码与离线独立验收通过**，最终已审/已通过实现 `5c65d15a05e39c194b1efbddf14683eedeac3ded`。首审 R1–R4 和第二轮路径规范化回归均独立复验关闭，历史候选与证据保留下文。该结论仅涵盖 identified evaluation-policy rehearsal；F.5、真实 API/C/判分及正式提交运行仍未完成。上一阶段身份保留在 [B 准备审核](b-live-preflight-review.md)，文档/存储提交不替代实现验收。

## 范围与环境

用户授权 F.2–F.4 的代码及离线验收：provider 配置与执行成本策略分离；默认本地首轮 B/C 仍共享 5 元；评测策略演练支持 record_only 与显式每 trial capped，并按 evaluation/task/attempt 隔离身份和状态。真实 API、任务世界、真实 C、官方判分及 F.5 最终提交冻结均未恢复或完成。规则来源与设计只维护在 [预算策略设计](../openspec/changes/bootstrap-baseline/design.md#本地开发预算与正式私有评测)。

复用固定 dev 镜像 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，Python 3.12.15/Linux arm64 与 `chi-model-deps` 只读卷（openai-agents 0.13.6、openai 2.36.0、httpx 0.28.1）。vendor 仍为 `4444a07fa68a4f1623f841a292a54e284fc8e7f7` 且干净，身份继承已有接入层验收。本轮没有安装/下载/重建镜像，没有修改 C、baseline、官方源码或依赖锁。

所有运行在 `--network none --read-only --tmpfs /tmp` Docker，源码快照与 SDK/vendor 只读，审核输出单独可写，不挂 `.env`、凭据、Docker socket、手册、病例或任务 fixtures。SDK/官方 runner 真实加载，HTTP 和工具均为合成边界；真实 usage/cost/reward 保持 null。

## 首候选独立结果

实现停写后，主代理显式暂存八个实现/配置/测试文件；仅删除新增 policy 模块一个 EOF 空行后固定 `c2de856`。主代理 Git archive 导出只读快照，自测日志与主代理证据分别保留。

| 主代理独立检查 | 实际结果 |
| --- | --- |
| 模型依赖卷全项目 pytest | 215 passed、105 subtests，退出 0 |
| 基础 dev 无可选 SDK 全项目 pytest | 153 passed、62 skipped、38 subtests，退出 0 |
| 实际 CLI 补查 | 10/10 通过，退出 0；合法高用量同链路、本地 cap、record_only、显式 6/7 元、unknown 隔离、重复身份、策略冲突、只读与 live 拒绝 |
| 组件/进程/故障补查 | 10 项中 4 通过、6 失败，退出 1；归并 R1–R4，候选未通过 |

CLI 补查从固定快照复制允许的 scripts/profiles 到各自隔离容器内工作目录，绑定同一固定 vendor/SDK，实际通过生产 CLI、真实 SDK 和官方循环。合法三请求 fixture 报告每次 1,000,000 input + 8,192 output，累计文档价格上界估算 6.196608 元；record_only 和显式 7 元完成，本地 5 元与显式 6 元在第三次发送前停止。这是合成用量/估算，不是实测账单。

首审发现：

- **R1：发送前策略重验与金额类型。** Guard 构造后把 local journal.policy 替换为 raw/hash/cap 仍为原值、mode 派生字段改成 record_only 的对象。初始 prior=4，下一笔约 2.16 元预留本应阻断，实际 lower 发送 1 次且未报错；reserve 没有重验 policy。另显式 capped=1 时，`cap_cny=True` 因数值相等被 Guard 接受。需按真实类型与持久绑定逐请求核对，不能仅在初始化时校验。
- **R2：独立任务的冷启动目录竞态。** 两个真实 spawn 进程初始化同一 evaluation 的不同 task，在共同目录 mkdir 前同步；一个成功，另一个被误报为 attempt claim 已存在。共同目录的检查/创建不能把其他合法进程的创建当成重复尝试。
- **R3：构造失败的 FD 所有权与安全错误。** 在 EvaluationJournal 的父类初始化后，第 2 次 `_persist_run` 注入失败，原始 OSError 泄出且 namespace 锁仍占用；单独注入 registry flock 获取失败，实测泄漏一个 FD。需要在整个构造生命周期释放自己拥有的资源、保留已有 claim/证据且安全分类错误。
- **R4：完整祖先路径检查。** base 的第 8 层祖先是 symlink 时，固定检查 5 层未拒绝，实际在目标目录新增 12 个证据路径。需在任何写入/claim 前检查完整相关祖先，本地同类固定层数逻辑一并核对。

另 4 项通过：真实 `os._exit(17)` 在 lower 退出后的 claim/pending 保留且另一 task 可初始化；registry provider profile 冲突拒绝；关闭 owner 零发送且不释放另一 attempt 的锁；静态 policy 派生篡改与非法 cap 拒绝。R1 动态替换不被这些静态测试覆盖。

首候选证据集中在忽略目录 `runs/evaluation-budget-policy/review/`：`candidate-c2de856.tar`、`snapshot-c2de856/`、`pytest-c2de856.log`、`base-pytest-c2de856.log`、`independent-policy-cli.py`、`cli-c2de856/`、`independent-cli-c2de856.log`、`independent-policy-boundaries.py`、`boundaries-c2de856.log/.json`。子代理自测另在 `runs/evaluation-budget-policy/impl/`，不代替上述证据。原始脚本/日志/轨迹不上传。

## 第二候选复验

同一实现代理返工后停写，主代理固定 `de69e7de9afdd872917cd48dc853af3771f27e39`。只改 transport 与对应测试；逐请求重验 policy/cap、并发共同目录安全创建、registry/attempt 构造失败清理和完整祖先检查均补入回归。

主代理从新只读快照独立取得：模型全量 220 passed、105 subtests，基础 dev 153 passed、67 skipped、38 subtests，实际 CLI 10/10 与原组件补查 10/10 均通过，退出均为 0。R1–R4 的原复现关闭；观察到动态篡改零发送、两个独立任务都初始化成功、构造错误安全分类/锁释放、registry FD 无泄漏、深层 symlink 零新增证据。

另一个 R4 定向回归未通过，退出 1：新祖先检查先 `os.path.abspath`，在检查前把 `alias/..` 折叠掉。以 `start/alias -> external/child`、root=`start/alias/../chosen` 调用，虽然最终受控报 `synthetic_journal_unavailable`，却已经在 external/chosen 创建目录及登记/claim；不能将事后拒绝当成创建前路径验证。已交回同一代理修正未折叠路径检查或拒绝含父目录跳转的根，不删除历史证据。

证据仍在同一忽略目录：`candidate-de69e7d.tar` / `snapshot-de69e7d/`，对应 pytest/base/CLI/组件日志与 JSON，以及 `path-normalization-boundary.py`、`path-normalization-de69e7d.json/.log`。本候选尚未通过本阶段整体验收。

## 最终独立复验

同一实现代理仅补修路径检查：先拒绝原始路径中的 `..`，再检查每个已有目录组件，避免规范化隐藏 symlink；本地和评测 journal 共用该边界。主代理固定 `5c65d15`，从新 Git archive 只读快照独立运行：

| 最终独立检查 | 实际结果 |
| --- | --- |
| 模型依赖卷全项目 pytest | 221 passed、105 subtests，退出 0 |
| 基础 dev 无可选 SDK 全项目 pytest | 153 passed、68 skipped、38 subtests，退出 0 |
| 实际 CLI 补查 | 10/10 通过，退出 0 |
| 组件/进程/故障补查 | 10/10 通过，退出 0 |
| 路径规范化定向补查 | 1/1 通过，退出 0；未创建外部或 lexical 目标目录 |
| README 最小挂载演练 | record_only 高用量链路三次发送、complete，退出 0 |
| 无 SDK 基础 dev 实际 evaluation plan / preflight / live | 分别退出 0 / 0 / 2；SDK unavailable、开发预算 not_read、认证未验证、执行暂停均明确报告 |

共 21 项主代理补充检查通过。evaluation preflight 的退出 0 表示策略只读检查结束，其 readiness 明确是 identified rehearsal not frozen；即使 SDK unavailable 也不代表完整运行就绪。计划/预检不创建 client/transport/账本/claim，live 在 profile、策略与身份访问前拒绝；原本地预算语义仍保留。实际 README 只挂 scripts/profiles、固定 SDK/vendor 和单独合成输出，没有项目全目录、凭据或任务资源。

最终原始证据仍在 `runs/evaluation-budget-policy/review/`：`candidate-5c65d15.tar` / `snapshot-5c65d15/`，各 `*-5c65d15.log/.json`、`cli-5c65d15/` 和 `readme-5c65d15/`，以及基础 plan/preflight/live 日志。前两轮快照/失败证据保留，不被最终结果覆盖。子代理本轮 focused 自测与首轮/full 记录分别留在 impl，不冒充上述主代理结果。

实际复验从项目目录使用以下布局；先将对应 archive 解包并补空 vendor 挂载点：

```sh
f_review_root="$PWD/runs/evaluation-budget-policy/review"
f_snapshot_root="$f_review_root/snapshot-5c65d15/chi-agent"
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e F_REVIEW_LABEL=5c65d15 \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro -v "$f_snapshot_root:/workspace:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$f_review_root:/review:rw" -w /workspace \
  sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3 \
  /opt/venv/bin/python -m pytest -q -p no:cacheprovider
```

同布局分别执行 `/review/independent-policy-cli.py`、`independent-policy-boundaries.py` 和 `path-normalization-boundary.py`；CLI 脚本输出目录独占，复验另换 F_REVIEW_LABEL，不覆盖历史。基础全量去掉模型卷/vendor/PYTHONPATH。README 最小挂载命令单独实际执行并保存日志。所有 Python/进程/文件故障注入均发生在 Docker 内。

## 保留限制

F.2–F.4 通过不等于正式评测入口就绪。策略/registry 是本地文件系统内、同一 root/evaluation 身份的约束，不是跨主机账单服务或对任意新 root 的全局幂等；任务/attempt 的外部合法性由未来正式调度提供。文件锁只验证 Linux Docker，未验证其他架构、恶意并发改目录、主机断电或任意阻塞调用的硬取消。

旧账本缺 policy 身份或 provider hash 不匹配时受控拒绝，不自动迁移/删除/清零。评测演练仍使用日期固定的 provider 候选、文档峰值估算与合成工具；官方价表、实际 response.model/usage/账单不由此确认。F.5 最终规则/资源核对、完整系统冻结及正式启动/提交说明，以及真实 provider/认证、任务执行和 judge 仍需后续独立授权及验收。
