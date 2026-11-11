# 评测专用入口与干净目录包独立审核

2026-10-26（Asia/Shanghai）。主代理核对 PR #10 merged=true，fetch 后从最新 origin/main `07c377cb173ce2a3eb5447742e547f97547c0610` 建立 `codex/evaluation-entry-bundle`，写入前干净。一个 `gpt-6-luna` / `high` 实现子代理，主代理负责规格、运行说明、独立审核、教学和 GitHub。

当前结论：**G 的专用默认入口与干净目录包离线验收通过**。首候选 `0369182fe6bf4485c42857680bef3f3580794c73` 未通过 R1–R3；修复候选 **`d4003cac37cad5396ef9b977914ff07c5367a0e1`** 经主代理独立复验通过。实际包输入 runbook 已包含在候选提交中，其余规格/状态文档不作为被测包输入。既有 F 的验收身份保留在 [策略分离审核](evaluation-budget-policy-review.md)。

## 授权与环境

本轮 G 解决“底层可选 record_only 但交付默认仍可能落回本地”的缺口：独立 entry 固定 evaluation record_only/null 金额上限，导出固定允许文件的独立目录包，从无原仓库挂载/不同 cwd 实际启动。真实 API、官方任务世界、真实 C、judge、正式配送和 F.5 完整最终系统冻结均未恢复或完成。规则/行为依据只见 OpenSpec 的 [G 设计](../openspec/changes/bootstrap-baseline/design.md#g评测专用入口与干净目录包)。

复用固定 dev `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`、Python 3.12.15/Linux arm64、`chi-model-deps`（agents 0.13.6/openai 2.36.0/httpx 0.28.1）及 vendor `4444a07fa68a4f1623f841a292a54e284fc8e7f7`。本轮不安装/下载/重建，不改依赖锁、官方源码、C 或 baseline。

所有 Python、进程和故障检查在禁网/只读根文件系统 Docker 内完成，临时目录或审核输出单独可写。模型层测试挂只读 SDK/vendor，基础层不挂 SDK。干净包运行只挂包、SDK、独立 vendor 和合成输出，不挂原仓库、凭据、socket、病例、任务 fixtures 或手册。HTTP/工具仍为合成输入，不产生真实 usage/cost/reward。dev Dockerfile 只复制 pyproject/基础锁，未把项目脚本 baked into 镜像；程序来自本轮导出的包。

## 首候选固定与独立结果

实现停写后，主代理显式提交八个实现/配置/测试及实际 runbook 输入，导出 `0369182` 的 Git archive；从只读快照独立复验并重新导出包，没有复用子代理 package-v3。

| 主代理独立检查 | 实际结果 |
| --- | --- |
| 模型层全项目 pytest | 229 passed、107 subtests，退出 0 |
| 基础 dev 无模型卷全项目 pytest | 160 passed、69 skipped、40 subtests，退出 0 |
| 基础 dev 实际 build | 13 个允许文件加 manifest，退出 0 |
| 干净只读包默认 task-a / task-b | 各 3 次发送、complete，退出 0；无策略选择参数，环境里的开发预算值不改变 record_only/null cap |
| 干净包 unknown / 独立 task / 同 attempt 换 run-id | 分别退出 1 / 0 / 2，保留原尝试和隔离语义 |
| 实际专用 preflight（SDK/vendor 完整） | 退出 0，technical_ready=true，认证未验证/执行暂停仍分别报告 |
| 无 SDK 基础包 plan / preflight / live | 分别退出 0 / 1 / 2；缺依赖不冒充技术就绪 |
| 组件/导出/故障补查 | 9 项中 6 通过、3 失败，退出 1；归并 R1–R3，未通过整体验收 |

三请求合成链每次报告 1,000,000 input + 8,192 output，单 trial 文档价格上界估算 6.196608 CNY。默认 task-a/task-b 都超过 5 元仍完成，证明专用入口不继承开发金额限额；它不是服务商计量或主办方真实账单。输出与 package/config digest 实际登记进 evaluation 的 registry/claim，内容身份不是签名/执行许可。

首审问题：

- **R1：输出根与程序包的祖先重叠。** `_safe_output_root` 只拒绝 output 位于包内，接受包父目录。令 evaluation-id 与包目录名相同，后续真实 EvaluationJournal 会在临时可写包里新增 11 个状态路径。需在任何 claim/client 前拒绝双向重叠，不能依赖容器包只读时的事后报错保护身份。
- **R2：失败发布的完成状态。** manifest 已写后注入 target 目录 fsync 失败，再让清理 manifest 的 unlink 失败；build 抛错，但随后的 validate_bundle 仍成功返回 complete。需可靠的未完成/完成发布协议，不能仅依赖尽力删除 manifest；保留失败目标占用和旧文件，不自动覆盖或重建。
- **R3：实际文件长度的有界读取。** 验证器约束 manifest 声明 size，却在核对真实长度前调用 `Path.read_bytes()`。将允许文件扩为 MAX+1，补查拦截观察到整文件读取入口被调用。需在读取前核对真实类型/大小与声明，并有界读取；相关配置读取保持同样边界。

另 6 项通过：不同输出路径导出内容身份一致且无开发文件；源 `.env`/runs 不读取或复制；源 symlink 拒绝；恶意 manifest 外部路径拒绝；重新计算 hash 仍不能更改金额策略/授权/布尔字段类型；已存在目标与父目录跳转拒绝。故障检查只操作容器内临时目录和合成文件，不触碰用户原始资料。

证据集中在忽略目录 `runs/evaluation-entry-bundle/review/`：`candidate-0369182.tar`、`snapshot-0369182/`、`pytest-0369182.log`、`base-pytest-0369182.log`、`build-0369182.log`、`package-0369182/`、`output-0369182/`、各实际 CLI 日志、`independent-bundle-boundaries.py` 与 `boundaries-0369182.log/.json`。子代理自测另在 impl，不能代替上述主代理证据；原始包、日志和轨迹不上传 GitHub。

## 修复候选与主代理独立复验

同一实现代理返工停写后，主代理审查五个修复文件，显式提交固定 `d4003ca` 并再次 Git archive 到只读快照。以下均由主代理重新执行，不复用代理的 final-r123-v2 结果或 package；先等每次实际 trial 返回，再启动下一个依赖其状态的 trial。

- R1 关闭：输出根同时拒绝包自身、祖先、后代及原始路径中的 symlink/`..`。补查不再能通过 evaluation-id 向包写入，实际 CLI 的祖先路径也在 claim 前拒绝。
- R2 关闭：先持久创建 `.bundle-incomplete`，文件/manifest 同步后才删除标记作为完成提交点。对“manifest 后 fsync 失败 + manifest 清理失败”同样注入故障，后续验证为 `bundle_incomplete`，失败目标继续占用。
- R3 关闭：`O_NOFOLLOW` 打开后用 `fstat` 核对真实类型/长度，按上限或声明长度有界读取并复查长度；bundle/source/entry config/provider profile 均不再依赖无界 `Path.read_bytes()`。

| 主代理独立复验 | 实际结果 |
| --- | --- |
| 固定快照模型层全项目 pytest | 233 passed、111 subtests，退出 0 |
| 固定快照基础 dev、无 SDK/vendor 全项目 pytest | 163 passed、70 skipped、44 subtests，退出 0 |
| 主代理组件/导出/故障补查 | 9/9 通过，退出 0；原 R1–R3 均有失败再通过证据 |
| 基础 dev 从固定快照 build、干净包 verify | 各退出 0；13 个允许文件及 manifest，无开发 policy/账本/凭据/数据/vendor 内容 |
| 无原仓库挂载、只读包、cwd=/tmp，默认 task-a 后 task-b | 各退出 0、3 次发送、complete、record_only/null cap；均未传策略选择或 scenario 参数，环境 BUDGET_CNY=0/CHI_MODEL_RUNS_DIR 不能触发开发回退 |
| missing-usage task-a 后独立 task-b | 分别退出 1/0，unknown 保留本 attempt，另一合法 trial 完成 |
| 同 attempt 换 run-id | 退出 2，保留 claim，无新增 trial 文件或工具效果 |
| 同 evaluation 换内容已重算 manifest 的包 / 同内容换存放路径 | 分别退出 2/0；前者 evaluation_policy_conflict，无新增 claim/运行；后者相同内容身份，合法 task-c 完成 |
| 改 cap 并重算 manifest / 文件篡改 / duplicate manifest | 均退出 2，分别 config_invalid / digest_mismatch / manifest_invalid |
| budget-evidence、execution-scope、evaluation-cap-cny 覆盖参数 | 三个实际 CLI 均退出 2，unrecognized arguments，不能切回本地策略 |
| 包祖先作为 output root | 退出 2，output_path_invalid；没有新 evaluation 目录 |
| 完整依赖专用 preflight | 退出 0、technical_ready=true，认证 unverified、execution paused 继续单独报告 |
| 无 SDK/vendor 的 plan / preflight / live | 分别退出 0/1/2；只读无写入/client/transport/claim，缺依赖明确报告 |
| 删除配置/manifest 后 live | 退出 2、real_execution_paused，bundle/config/凭据/client/transport/claim 均未访问 |
| README 最小文件挂载 build + 从导出包目录 verify / plan | 均退出 0；再次导出与固定快照包内容 digest 相同 |

四条完成链（最初两个默认 trial、unknown 后的独立任务及相同包迁移后的 task-c）均从本 attempt 的零合成 prior 开始，最终合成上界估算各为 6.196608 CNY。记录中的 retry_policy 四层均为 0，真实 usage/cost/reward 均为 null；观察到两次合成工具效果及三次请求。registry、claim、run evidence 实际记录同一个包 manifest digest，配置也包含在该身份内。

验收包 manifest：`59259e27cf7cfd08426a17e2956a660aa8c21500537b0b553bc33eb222cfdbbe`；entry config：`3b55775ee22ec4cf67e463805aa429a803cdd550d059242c7da5409a0c61b413`。manifest 标识内容一致性，不验证发布者身份，也不恢复真实执行许可。

### 实际命令与证据入口

以下为本轮实际命令的等价挂载写法，均在本机现有 dev 镜像中执行。`g_review` 为本项目忽略的 `runs/evaluation-entry-bundle/review` 绝对路径，`g_snapshot=$g_review/snapshot-d4003ca/chi-agent`，`g_vendor` 为现有固定 vendor 的绝对路径；镜像身份以本报告环境段为准。基础 pytest 移除 SDK/vendor 两个挂载、把 PYTHONPATH 改为 `/workspace/scripts`。

```sh
docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro -v "$g_snapshot:/workspace:ro" \
  -v "$g_vendor:/workspace/vendor/chi-bench:ro" -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python -m pytest -q -p no:cacheprovider

docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -v "$g_snapshot:/workspace:ro" \
  -v "$g_review:/review:rw" -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python scripts/evaluation_bundle.py build --target /review/package-d4003ca

docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/package/vendor/chi-bench/src \
  -e CHI_MODEL_RUNS_DIR=/forbidden-development -e BUDGET_CNY=0 \
  -v "$g_review/package-d4003ca:/package:ro" -v chi-model-deps:/model-deps:ro \
  -v "$g_vendor:/package/vendor/chi-bench:ro" \
  -v "$g_review/output-d4003ca:/output:rw" -w /tmp chi-agent-dev:latest \
  /opt/venv/bin/python /package/scripts/evaluation_entry.py rehearse \
  --output-root /output --evaluation-id root-default --task-id task-a \
  --attempt-id attempt-1 --run-id root-task-a
```

主代理原始证据仍在同一忽略目录：`candidate-d4003ca.tar`、`snapshot-d4003ca/`、`pytest-d4003ca.log`、`base-pytest-d4003ca.log`、`boundaries-d4003ca-root.log/.json`、`package-d4003ca/`、`output-d4003ca/` 及各 `*-d4003ca.log`。`prepare-cli-variants.py` 只创建一次性审核副本，`inspect-entry-results.py` 独立核对合成账目/claim/registry/CLI 记录，结果为 `entry-evidence-d4003ca-root.json`。README 实际命令日志为 `readme-build/verify/plan-d4003ca.log`；独立导出结果另在 `runs/evaluation-entry-bundle/exports/evaluation-entry-001/`。这些源快照、导出包和原始材料均不上传。

## 通过范围与限制

G 通过只覆盖固定默认入口、目录包和既有依赖中的 Docker 离线行为。构建失败检查覆盖提交点前的明确故障注入，不作任意存储硬件故障或断电恢复证明；新机器依赖安装、跨运行身份及完整官方启动未补验。F.5 的完整最终冻结、真实 provider/认证、官方任务/判分、正式材料配送和用户完整运行验收继续未完成；所有真实入口仍暂停。
