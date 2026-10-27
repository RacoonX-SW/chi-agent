# DeepSeek 本地开发评审独立审核

基线：`b44ce46384c37353c11f90044e696d7daceadbdb`（PR #15 已合并）。工作分支 `codex/deepseek-development-review`。用户要求在没有 Claude 的情况下使用 DeepSeek；实现为一个 GPT-6.1 Terra / high，主代理负责规格、独立审核、实际调用、教学及 GitHub。

## 契约与结果口径

原版 [WorkspaceJudge](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/verifier/judge/workspace_judge.py) 接受 runner 注入，但 [官方说明](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/docs/judge.md) 固定 Claude 模型。L 复用固定 PA adapter、评分条目、原始判定提示及部分确定性检查，以 DeepSeek 做本地诊断；不修改 vendor，不生成冒充官方的 reward/scorecard。内联证据、无工具、直接返回 JSON 的补充提示有独立版本与 hash；这是改动后的开发协议，official_reward 始终 null。

单次结构化请求比再构建一个文件工具 Agent 的边界更小，适合本轮固定终态证据；超出大小限制时拒绝，不截掉材料继续评。原版可选 bundle/policy tree 查找被禁用，防止读取未绑定资料；参考来自已捕获 expectations 和目标患者的原始 chart 切片，不能据此声称完整官方协议等价。

上次 C 未导出完整业务状态，SQLite 已随旧 world 删除，不能从 trace 补造权威 export。新捕获发生在成功 K C 的 runner 退出后、world 清理前；export、固定 expectations 和原始 shared world 写 controller 独有目录，与 participant/world 挂载分开。capture ready 仅表示文件捕获，评审还要验证终态/来源、完整材料、目标患者与原始文档。旧尝试和费用保留。

## 固定候选与独立证据

主代理从提交导出只读 Git 快照，分别挂载固定 vendor、模型/PDF 只读卷和独立合成输出，禁网、无密钥、无 Docker socket。自测结果与主代理复验分开。

| 候选 | 主代理回归 | 独立故障检查 | 结论 |
| --- | --- | --- | --- |
| `d70a7e1edb71a5c6054af8b4bf4f7eef2d04bb47` | 279 passed / 143 subtests | 11 项中 8 过，3 失败 | 首审未通过，R1–R3 返工；未真实调用 |
| `81007ffbbdcdf9dc52ccdc91d7903bfaa4f5f092` | 284 passed / 143 subtests，1 个测试子进程导入失败 | 原 11/11，新增捕获 9/9 | 生产修复通过；测试入口依赖返工 |
| `cea979fa708e753a9eb8103ab183f7e496020819` | 285 passed / 143 subtests | 与上行生产文件完全一致，保留 20/20 独立范围 | 离线通过，在该 participant 身份完成新 B/C 与捕获 |
| `e084b89bc02db5935a9eb03c9e3d79958541b2d8` | 286 passed / 143 subtests | 原 11/11 重复通过，捕获源码未改 | 修复真实审计 journal 大于读入上限；确定性检查成功，首笔评审用完生成预算 |
| `c275bd5a5688d7736c70ea929cbb2286746d256e` | 287 passed / 143 subtests | 原 11/11、独立预算/截断/接续 4/4，保留未改捕获的 9/9 | 最终离线通过，同一 C 的第二笔 DeepSeek 开发评审实际成功 |

证据位于忽略的 `runs/development-review-root/evidence/candidate-{1,2,3,4,5}/`，含 pytest、independent、capture-checks、review-settings-checks 与静态输入预检记录。主代理故障脚本为 `runs/development-review-root/{check_independent.py,check_capture.py,check_review_settings.py}`，只用自造文件、FIFO、模拟 Docker/HTTP 与崩溃点；24 项独立范围分别随对应生产文件验证。两次最后修复只改独立评审器，participant scripts/profile/锁与真实 C 的身份一致，因此复用捕获，未重跑 B/C。

| 问题 | 可重复证据与影响 | 当前处理 |
| --- | --- | --- |
| R1 非普通文件 | `_read()` 在 fstat 前以阻塞方式 open FIFO；独立子进程 1 秒仍挂起，审核器终止自己的测试子进程 | 已关闭：O_NONBLOCK 后 fstat，独立原故障通过 |
| R2 祖先路径链接 | 合成完整捕获位于父目录链接下时仍通过，最终层 is_symlink 不能覆盖祖先 | 已关闭：输入、来源账目及输出逐层检查，原故障通过 |
| R3 结算崩溃窗口 | 在 aggregate 已 settled/pending=null 后中断，run 目录尚无逐请求 usage 记录 | 已关闭：settlement 先 fsync，再清 pending；后续核对 claim/receipt/累计总量 |
| 捕获总时限 | Docker 默认 30 秒请求空闲超时不等于整个 archive 流的总截止 | 已补 60 秒单调截止、API 超时和流 finally close；单次在途读取可额外超过约一个 API 空闲超时 |
| 真实日志容量 | C 的审计 journal 为 2,803,396 bytes，超过评审器最初的 2 MiB 读取界限；禁网预检拒绝，未因此发送评审请求 | 本地 journal 改为 32 MiB 有界读取，3 MiB/超限/身份篡改合成回归通过；内联仍限 2 MiB |
| 思考生成预算 | 第一笔评审 8,192 个 completion tokens 均为 reasoning，finish_reason=length、最终 content 为空 | 保留 incomplete 与费用；独立评审上限改为 32,768、总截止 360 秒、socket read 60 秒，body/plan/identity/预留同步；第二笔完成 |

## 环境与实际运行

复用 Python 3.12 dev/controller/world、H 模型依赖卷和 K PDF 只读卷，不新增依赖或重建受限镜像。主代理在禁网、只读固定 world 镜像内预检元数据：当前任务 contract_v5，expectations 14,169 bytes、原始 world 2,279,710 bytes、6 个 baked evidence 条目；此为来源/容量预检，不是运行或判分。

静态来源预检以虚拟空 export 调用真实 adapter，不产生 trial/评分：得到 8 个 rubric（6 evidence、2 coherence）、17 个 workspace 文件、44,613 bytes 内联材料，chart_slice/evidence_index 均存在。此处不把预检当作真实终态评审。

本轮实际执行（所有费用均为 CNY 峰值保守估算，**不是扣费**）：

| 运行 ID | 实际结果 | 模型请求 | input / output tokens | 估算 |
| --- | --- | --- | --- | --- |
| `l-b-20261027-001` | 当前源码 B 工具闭环成功，2 项工具返回 | 3 | 4,888 / 175 | 0.011176 |
| `l-c-20261027-001` | 新世界自主完成、46 项工具全部返回、捕获 ready | 26 | 3,825,987 / 20,551 | 7.816382 |
| `l-review-20261027-001` | length / 空最终内容，incomplete；有效 usage 已结算 | 1 | 40,836 / 8,192 | 0.147208 |
| `l-review-20261027-002` | complete；DeepSeek 逐项 8/8 通过 | 1 | 40,836 / 20,103 | 0.242496 |

C 的业务终态回读为 submitted、付款方 intake in_progress；这是已提交和处理中，不是付款方最终批准。claim 到清理记录的间隔为 205.316298 秒，不冒充完整前置准备耗时。四份 runner 日志/结果均非空，provider 请求全部 settled。主代理向 Docker 引擎按精确 ID 另外核对新 B runner、新 C runner/world/network 均不存在，controller clean、pending=null。

权威捕获 manifest SHA-256 为 `27927d5f72825daa106ddbb8c8fc0abf94d7ba7d7a090709d7ee89dfd92748aa`；实际评审 workspace 为 17 文件 / 130,089 bytes，内联 prompt token 数 40,836。原版部分确定性检查 9/9 通过；DeepSeek 的 8 项为 6 个证据条目加 2 个 coherence 条目，全部返回严格 bool 和实际存在的文件引用，正向判定均有 Agent 产物引用。只核对结果结构和引用存在性，没有主代理再次独立裁决临床/规则判断。官方 reward 仍为 null，不生成官方 scorecard、通过率或论文可比分数。

评审两笔累计估算 0.389704；第二笔 provider 回报 input cache hit 40,702、miss 134。含所有历史成功/失败、旧 J prior 和本轮评审的总峰值估算为 19.102322。原先用户报告控制台约 1 元为其当时实际账单观察，本轮未登录控制台核对新扣费；不把保守估算当账单。

独立对账检查旧 J 的 2,192 个非 projection 文件指纹完全不变；旧 K 仅允许当前 accounting/controller/B-success 更新，旧尝试、claim、adoption 与费用证据未改。K namespace 的 75 个请求全部结算，加旧 J 的 3 个和评审的 2 个共 80 个已计量请求；逐 run tokens/cost、旧 prior、评审 settlement 与全局总量相符。两套账目均 pending=null，没有清零/删除失败以接续。

实际证据：`runs/development-review-root/actual/` 中的 B/C/评审安全 stdout、`review-001-metadata.json`、`review-summary.json`、`final-reconciliation.json`；原始 C 产物在既有真实运行目录，评审原文及 settlement 在 `runs/development-review/<review-id>/`。均在 Git 忽略范围内。

## 实际命令与复验入口

最终回归从 `git archive c275bd5 chi-agent` 快照执行（补空挂载目录，凭据/真实 runs 不在快照）：

```sh
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/pdf-deps:/model-deps:/workspace/vendor/chi-bench/src \
  -v "$PWD/runs/development-review-root/candidate-5/chi-agent:/workspace:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$PWD/data:/workspace/data:ro" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -v "$PWD/runs/development-review-root/pytest-5:/workspace/runs:rw" \
  -w /workspace chi-agent-dev:latest /opt/venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
```

实际入口遵循 [README](../README.md#deepseek-本地开发评审) 的 Docker 最小挂载与运行方法。以下为已执行的证据命令，不重复占用的 ID：

```sh
chi_live_control rebind-source --reason 'L independently reviewed cea979f terminal capture for DeepSeek development review'
chi_live_control k-b-smoke --run-id l-b-20261027-001
chi_live_control c-run --run-id l-c-20261027-001
chi_development_review deterministic --input-dir runs/development-review-inputs/l-c-20261027-001
chi_development_review review --input-dir runs/development-review-inputs/l-c-20261027-001 --review-id l-review-20261027-001
chi_development_review review --input-dir runs/development-review-inputs/l-c-20261027-001 --review-id l-review-20261027-002
```

第一笔评审使用 `e084b89` 的 8,192 上限；第二笔使用 `c275bd5` 的 32,768 上限，旧费用仍在同一评审账目。生产 Docker 图片和依赖身份沿用 [K 报告](c-development-retry-review.md)，实际 orchestration 再次核对了固定 image ID 与 SDK/PDF 身份，没有重新安装或重建受限镜像。

## 保留的限制

范围限当前 PA provider 任务与已支持契约，不代表其他领域、平台或架构通过。DeepSeek 与参赛模型来自同一 provider，判断可能有相关偏差；应结合确定性失败项和证据检查，不能把本地评审当独立官方排名。受限材料、凭据、原始轨迹和评审文本仅在本地忽略目录，不上传。
