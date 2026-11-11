# 真实 B 运行准备独立审核

2026-10-26（Asia/Shanghai）。基线 `3d4f9db09d0a623b925ec0a3c43e29ff7f06e0db`；已核对 PR #7 由用户合并，fetch 后从最新 origin/main 建立 `codex/live-b-preflight`，写入前干净。

结论：**真实 B 运行准备代码通过内部离线独立验收**。最终已审/已通过实现为 `2244220638830dec3ef1bba36d562d7258870e79`；首审与后续返工身份保留在下文。用户明确选择“先完成真实 B 运行准备，继续暂停实际调用”；本轮没有真实模型 API、C 任务或官方判分，不消耗/重置 B/C 共享 5 元规划，也不将准备完成写成真实 B 已通过。

验收后提交 `511f438` 仅删除四个新增 Python 文件各一个 EOF 空行。主代理核对该提交只有四行空行删除，基线到最终内容的 `git diff --check` 通过；未改行为，因此没有重复运行测试，行为验收身份仍为上列 `2244220`。

## 范围与依据

一个 `gpt-6-luna` / `high` 实现子代理，主代理负责规格、独立审核、教学、文档和 Git。复用既有固定 SDK/官方 runner 的离线接入，不把通用传输准备、profile 或预检结果当作真实 provider 验证。

主代理通过内置浏览在当日读取官方资料：

- [人民币价目](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：候选 DeepSeek Flash 的高峰未命中输入 2 元/百万 token、输出 8 元/百万。准备层使用该峰值上界，直接 CNY 核算，不伪造汇率或实测账单。
- [模型元数据](https://api-docs.deepseek.com/zh-cn/api/list-models/)：文档示例 context_window=1048576，表示输入与输出的总 token 容量。整窗作为输入预留，再加有限输出，是基于服务端遵守文档的保守推断，不是本地 tokenizer 精确计数。
- [思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)：tools 历史携带 reasoning 字段；沿用原模式，不静默降级。
- [Token 用量](https://api-docs.deepseek.com/quick_start/token_usage/)：字符比例只是估计，实际以响应 usage 为准；本轮不下载 tokenizer。

来源/核对日期需在 profile 和证据中可追溯，陈旧或缺失依据不放行。账户认证、真实响应模型与 token/账单仍未观测。

## 环境与实际检查

复用 `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`、Python 3.12.15/aarch64 开发环境及 `chi-model-deps` 卷（固定 openai-agents 0.13.6、openai 2.36.0、httpx 0.28.1）；版本/原环境证据见 [上一接入层审核](model-runner-integration-review.md)。本轮没有安装包、下载 tokenizer/官方资源/浏览器或重建镜像；两份原锁、可选模型锁、vendor、C 控制器和 baseline gate 未改。

| 本轮文件/接点 | 最终行为 |
| --- | --- |
| 公共 provider profile / loader | 固定模型/路由/high/生成上限、CNY 源价与 context 依据，严格匹配原始事实及派生字段；文件 hash 与核对日可追溯 |
| `plan` / `preflight` | 只读核对 profile、SDK/source、显式 prior evidence；默认真实账目 unknown、认证未验证、执行暂停，缺可选依赖也可受控报告 |
| 通用 `GuardedTransport` | 注入下层 HTTP transport，验证实际 SDK wire 的路由、text/非流式/单候选/生成限制及历史，再持久 reserve；响应 usage settle 后才进入协议/整批工具校验 |
| `SyntheticJournal` | synthetic namespace 的 cap/prior/profile/pending/settled/unknown 持久化、fsync/原子替换与 flock 所有权；旧对象不能释放他人锁或在关闭后写账/发送 |
| 既有 SDK/官方循环的 prepared 接点 | 最小注入新 guard 与 fixture lower，保留旧默认路径、empty/None history、零重试及 scoped 恢复；工具 effect 逐条写盘 |
| 收尾证据 | 锁内写 finalizing，解锁后专用 writer 只更新本 run 独占终态；清理失败落 incomplete，保留主错/清理错/持久化错 |

合成演练默认 cap 对齐 5 元，state 的已持久化 cap/prior 不随新 run-id 提高或清零。真实预算文件只读验证，不初始化真实账本；认证变量只报告名称，不读取值。profile 的 30 天失效策略不等于动态价格监控；真正恢复 API 前仍须复核最新来源和许可。

首候选停止写入后由主代理显式提交，导出 Git archive，只读源码并挂固定 vendor/模型依赖卷，在禁网 Docker 独立运行全量：198 passed、92 subtests，退出 0。基础 dev 不挂 SDK 卷时，新增测试顶层 httpx import 导致 collection error，退出 2，未通过原基础入口回归。

主代理补充 9 项中 1 项通过、8 项失败，另补合法 gzip 响应失败，退出均为 1。按 R1–R5 归并返工：

- R1：官方 usage 示例只有 nested cached_tokens、direct hit/miss，误被要求 nested miss 字段；输入加输出超过 context 的总量未阻断；已解压响应连原 gzip header 重建导致重复解压。
- R2：raw/hash 匹配但派生价格/预留被改小的 profile 仍可发送；guard 可把 journal cap 改为 Infinity；默认演练上限为 10，要求对齐本轮 5 元目标，主代理已实证 5 元演练可正常三轮完成。
- R3：同一 journal 的 pending 可被新 guard 覆盖；磁盘布尔金额被 Decimal 当作已知 1；关键身份/金额/cap 须以严格、持久状态为准，不自动迁移开发中间文件。
- R4：旧对象 finish 释放锁后，另一个对象取得锁，旧对象 close 会删除新对象锁；需按所有权释放。
- R5：基础 dev 的可选测试导入失败及文件末尾格式问题。

原始记录集中在忽略的 `runs/b-provider-preflight/review/`：`candidate-fbafa81.tar`、`snapshot-fbafa81/`、`pytest-fbafa81.log`、`base-pytest-fbafa81.log`、`independent-fbafa81.py/.json/.log`、`gzip-boundary.py` / `gzip-fbafa81.json/.log`。子代理自测不代替独立验收，不上传凭据、数据、vendor、手册或轨迹。

第二候选 `0e4dc4317bbbba313fbd43f0c74a967ad378ce42`：模型层独立 206 passed、96 subtests；基础 dev 独立 153 passed、53 skipped、38 subtests。首审 9 项和 gzip 全部通过。另 8 项生命周期补查中 7 项通过，包括真实 `os._exit(17)` 中断后 pending 保留、真实进程间锁接力、只读入口、预算/prior 重启保留和 prepared SDK 的空/None 历史。剩一项发现已 closed 的 journal 仍可被新 guard 使用，在另一个 owner 持锁时发送，交回同一代理作 R4 生命周期返工。

第三候选 `42f9d616e1dee418b836c48efa7cff121a081c2c` 修复 active-lock 门禁，但收尾顺序把 complete 先写盘；锁 FD 关闭失败后仍在磁盘留下 complete。主代理定向注入只作用于该锁 FD 的 close 错误独立复现，交回修正本 run 最终证据与 namespace 所有权的收尾，不放宽 shared-state 的门禁。各轮完整快照、日志和补充脚本保留在同一忽略目录。

最终候选停止写入后，主代理从新 Git 快照独立取得结果：

| 最终独立检查 | 实际结果 |
| --- | --- |
| 模型依赖卷全量 pytest | 208 passed、98 subtests，退出 0；新旧模型路径均实际加载 |
| 基础 dev 全量 pytest | 153 passed、55 skipped、38 subtests，退出 0；无可选 SDK 的模型测试按条件跳过，基础/profile 只读检查仍执行 |
| 原首审补查 + gzip | 9/9 + 1/1 通过，退出 0 |
| 生命周期/进程/账目补查 | 9/9 通过，退出 0 |
| 收尾磁盘终态定向检查 | 1/1 通过，退出 0 |
| README 最小挂载 rehearsal | 正常三次发送、两次合成工具，退出 0；只保存 synthetic 证据 |
| 基础 dev 实际 plan / preflight / live | 分别退出 0 / 1 / 2；缺 SDK、真实 prior 缺失、认证未验证与暂停均明确报告，无 client/transport/账本/凭据读取 |

20 个补充边界包括实际 `os._exit(17)`、实际跨进程锁接力、关闭 journal 零发送、pending 不覆盖、persisted cap/prior 重启保持、已知超额返回仍保留账目并阻止下一发送、profile 派生篡改/非有限 cap、官方缓存字段、context 总量、gzip、空/None 历史、只读构造拦截和清理错的磁盘终态。以上以 mock 下层与合成 usage 验证，未使用真实 provider 计量。

实际命令可从项目目录复现，快照解包后补空 vendor 挂载点，脚本/结果目录为忽略目录：

```sh
b_review_root="$PWD/runs/b-provider-preflight/review"
b_snapshot_root="$b_review_root/snapshot-accepted/chi-agent"
git -C .. archive --format=tar 2244220638830dec3ef1bba36d562d7258870e79 chi-agent > "$b_review_root/candidate-accepted.tar"

docker run --rm --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e P_REVIEW_LABEL=2244220 \
  -e PYTHONPATH=/model-deps:/workspace/vendor/chi-bench/src \
  -v chi-model-deps:/model-deps:ro -v "$b_snapshot_root:/workspace:ro" \
  -v "$PWD/vendor/chi-bench:/workspace/vendor/chi-bench:ro" \
  -v "$b_review_root:/review:rw" -w /workspace \
  sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3 \
  /opt/venv/bin/python -m pytest -q -p no:cacheprovider
```

同布局分别执行 `/review/independent-fbafa81.py`、`gzip-boundary.py`、`lifecycle-boundaries.py` 和 `finalization-boundary.py`；基础全量去掉依赖卷/vendor/PYTHONPATH，保留源码只读与临时目录。进程检查实际从容器内创建隔离 Python 子进程，未依赖主机 Python。

最终原始证据同在 `runs/b-provider-preflight/review/`：前两候选 tar/快照、第三候选 `candidate-final.tar` / `snapshot-final/`、最终 `candidate-accepted.tar` / `snapshot-accepted/`，各 `*-<SHA>.log/.json` 结果，另有 `readme-2244220/` 的 journal/合成请求、`readme-rehearse-2244220.log` 与 `base-plan/preflight/live-2244220.log`。子代理首轮控制台/日志只保留为自测，不能替代上述主代理固定代码证据。没有上传原始材料。

## 保留的真实运行缺口

实际 API 许可未恢复，认证不读取/不验证，真实预算证据缺失不能按零处理。新的可注入边界只用无网络 mock 验收，合成账本不初始化或占用真实 B/C 预算。profile 文档来源、保守价格与上下文容量不能证明服务端账单硬封顶；真实 provider/任务和官方 reward 仍需另行恢复及验收。

文档 alias 与实际 response.model 的一致性未验证，当前严格匹配候选，不静默换模型/模式；cache/价格上界不是实收金额。journal 锁仅验证 Linux Docker 的本地文件语义，同一进程适配仍串行；未提供分布式账单服务、跨账本全局幂等、任意阻塞调用硬取消、主机断电保证或其他架构。旧/损坏 synthetic schema 拒绝，不自动迁移或删除历史。真实 C/判分、OpenSpec CLI 与用户完整运行验收仍未完成。
