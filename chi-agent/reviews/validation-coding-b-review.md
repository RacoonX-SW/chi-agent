# 冻结候选最小真实coding-B：执行与核验

日期：2026-11-04（Asia/Shanghai）。接续[PR52准备报告](validation-preparation-review.md)和[绑定候选的审批草案](../openspec/changes/validation-preparation/proposal.md)。本报告记录**后继已获准B**，不改写准备轮零真实调用或此前失败。短状态只在[REVIEW_STATE](REVIEW_STATE.md)。

## 1. 授权、工作区与候选

本次唯一授权为用户在当前对话的明确决定：

> 同意按PR52草案，保留payer-010的未知结果/token及旧pending，不核销、不重发；限定本轮候选与eval-vprep-20261104，执行vprep-b-001一次coding-B，最多6个模型HTTP，异常或新未知立即停止。暂不授权其他真实运行。

采用草案G0路径2：保留旧unknown，限定允许特定后继B；**不是结算、零发送确认或账户全史清零**。旧 `eval-abl-on2` 历史授权佐证缺口仍保留，本决定不回写过去已获准。原始决定及新旧root/run/hash/候选/次数关联保存在本地 `runs/validation-live-20261104/admission-decision.json`，SHA-256=`784cdca2028255df032ec45457f0d4fa6af716078ca1096377ce04273f9d5ea3`。

开工检查原准备分支干净；进程名/运行容器快照未见并行项目执行。刷新远端及GitHub API确认[PR52](https://github.com/xsw932187210-cell/chi-agent/pull/52)已由用户合并，`origin/main=7103877af0000dcab55560eb82e387dfe0483101`。从此新建 `codex/validation-coding-b`，未续写已合并准备分支。没有实现代理或生产代码/测试/profile改动。

真实执行复用原封存release，不以当前文档HEAD重绑包身份：

| 项目 | 实际值 |
| --- | --- |
| 冻结源码 | `0625c26dc9da453a3ac13bf537d156cad57dd940`；[候选JSON](validation-candidate-20261104.json)文件SHA `1846d79cd276aee9cb8414e9e80b78ac9639f227c3a2ae1a97bcefb9f3f9b1d2` |
| Go bundle manifest identity | `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb` |
| runtime identity | `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559` |
| release manifest原始文件SHA | `4b0c2f31553fac46cfa1ee1f6e8638e49e53377966e81267960f762518017d6a` |
| evaluation/run/task/attempt | `eval-vprep-20261104` / `vprep-b-001` / `synthetic-coding-b` / `attempt-1` |
| 账根 | host `runs/validation-live-20261104/state` → 容器 `/state`，history_mode=`external`；启动前没有账本或该run日志，不靠改名绕过历史 |
| 模型/路由 | `deepseek-v4.1-flash` / `https://opencode.ai/inference/go/openai/v1/chat/completions`，thinking enabled / reasoning_effort high |
| 物理上限/输出 | 最多6次、每次max_tokens=1024；自动重试0；summary/recovery/confirmation/patient均关闭 |
| 环境 | Docker镜像`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`；Linux arm64 / Python3.12.15；固定SDK/PDF卷及vendor身份与候选完全相同 |

## 2. 实际准入检查和执行边界

全部Python均在Docker/Python3.12；无安装或依赖升级。本地脚本/原始产物集中忽略目录 `chi-agent/runs/validation-live-20261104/`，不进入Git。

1. **无Key禁网preflight**：只读挂封存release/package、候选JSON、固定vendor/依赖、新授权记录及两份指定旧accounting。逐包成员hash、release/SHA256SUMS、真实 `_identity()` 的详细SDK/source/PDF身份全部一致；新state/run路径未使用，原两份accounting hash匹配。`audit/preflight.py` exit0，`evidence/preflight.json`。
2. **最小凭据供应**：只检查既有专用 `runs/real-external/auth/go.env`，权限0600、单一 `OPENCODE_API_KEY`、无其他变量；禁网检查仅输出布尔结论，不打印Key/长度/前缀或其hash，不读取完整项目`.env`。真实容器仅通过Docker `--env-file`获得此变量，不挂认证文件本体。`auth_check.py` exit0，`evidence/auth-check.json`。
3. **单次启动**：先固定 `launch-intent.json`，仅启动一个有唯一名字/标签的容器 `chi-vprep-b-001`。只挂包、vendor、固定依赖和新state/log；无任务、手册、world、旧state或Docker socket。HTTP仅为包内自造代码题和两个合成工具结果；没有临床载荷或隐藏材料。
4. **限制与收尾**：保留原guard新请求准入180秒、IO300/read240及请求上限；外层 `timeout --signal=INT --kill-after=30s 360s` 为原B操作者时限加取消清理余量。没有修改运行包、提示、thinking/high、输出或预算。实际约6.695秒结束，未触发超时/取消/强杀。

Extra Usage沿用既有用户确认关闭的设置（见[runbook](../docs/go-chi-entry-runbook.md)）；本轮未登录控制台重新观测或更改设置。每笔真实响应均为`billing_source=go`且charged=0，原guard的非Go/正数实扣停止规则保留。这证明本次响应的计费来源，不是账户当前余量或所有控制台设置的独立核验。

实际入口argv（以下是**已消耗的一次授权的历史命令，不是可重跑许可**）：

```sh
python /package/scripts/go_chi_entry.py coding-b \
  --bundle-sha256 de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb \
  --evaluation-id eval-vprep-20261104 --task-id synthetic-coding-b \
  --attempt-id attempt-1 --run-id vprep-b-001 \
  --history-mode external --output-root /state --logs-dir /runner-logs/vprep-b-001
```

外层实际使用`/opt/venv/bin/python`，`PYTHONPATH=/model-deps:/pdf-deps:/package/vendor/chi-bench/src`。容器只读root、tmpfs `/tmp`、cap-drop ALL/no-new-privileges，Go网络仅在唯一真实B容器启用；前后审计容器全部禁网。

## 3. 实际结果、全分母与费用

**1个逻辑B、1次容器启动、3个物理模型HTTP，全部settled，0失败/0未知/0重试。** 准许6次是上限，剩余3次不是可继续调用的额度。用途为main=3；confirmation/summary/continuation/patient各0；无CHI业务C、world、Trial或判分。

北京时间容器开始 `2026-11-04 11:46:10.173959`，结束 `11:46:16.868782`，退出码0。固定工具事件为 `inspect_code started/returned` → `verify_patch started/returned`，两工具各执行一次，后者结果hash对应精确字符串 `verification:pass`；第三个响应正常stop。实际wire逐次核对原system/instruction、模型、thinking/high、1024上限及固定两工具schema，未加入其他输入。

| HTTP | 结果 | 输入tokens | 输出tokens | cache read（已含输入） | reasoning（已含输出） | list USD | allowance USD | charged USD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | tool_calls / settled | 399 | 29 | 0 | 0 | 0.0001545 | 0.00009270 | 0 |
| 2 | tool_calls / settled | 452 | 91 | 384 | 22 | 0.0001319 | 0.00007914 | 0 |
| 3 | stop / settled | 559 | 20 | 384 | 0 | 0.0000788 | 0.00004728 | 0 |
| 本次合计 | 全部HTTP200、go来源 | **1410** | **140** | **768** | **22** | **0.0003652** | **0.00021912** | **0** |

原响应cache_write_1h/cache_write_5m均0；非缓存input分项为399/68/175，合计642，与总input减cache一致。原响应`total_tokens`为428/543/579，共1550；cache/reasoning是input/output子项，不再次相加。三项USD分别为模型价目价值、套餐消耗和余额实扣，不相互相加，不与旧CNY混算。字段完整、billing warnings=0、unsettled=[]；本次实扣0不称为免费，也不推断套餐余额或跨前史总消费完整。

## 4. 独立只读核验、旧账及清理

容器结束后只收集其State、退出码和原输出日志；未读取Docker Config.Env或把Key写入命令。独立Docker禁网 `audit/postflight.py` 调用包内真实 `inspect_history()` 严格审计完整新账，另外逐笔验证request/response证据hash、固定wire参数、工具事件、成功结果hash和receipt/seal与实际run摘要一致。**15个state文件的集合/hash在审计前后及容器删除后相同**；state/run日志18个文件及container输出扫描无Go Key（无秘密值输出）。`inspect_history.execution_allowed=false`仅表示只读检查不授权执行，不能用它自动启动后继。

| 新证据 | 实际SHA-256/状态 |
| --- | --- |
| 新chi-accounting.json | `4b5e3d0ac20103014bcfc3b1970c6fc71e758648a7cc43bc8094ad1cac7a08f9`；pending=null、halted=null、仅该一次B |
| 新B receipt | `c762fa97670d71849d95e0d3db8e593d40c638bae0e9c95478a1ea0c57185c82`，绑定本候选runtime/run/evaluation/task/attempt及完整run摘要 |
| 新run seal | `c46d54ee8fb324147a51dbb2ebfec5ee45a54a1668707c486e27128ea84fa99c` |
| postflight.json | `73512f429f34d81e029ddea9c6384a739cb373501e66a920a43d9ed74fe62b80`，exit0、status=verified |
| 原response用量详情提取 | `usage-details.json` SHA `addb8cd16c2862c7686ec893842f648f6f54ad79555167377985efdbad8b819c` |
| cleanup.json | `71700146bb2560a8968f3bb934776e3b6fca0831a24700c6b711a82982cc3cdf`，confirmed |

旧accounting在前后两次均只读验证：

- `state-abl-on` SHA仍为 `1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef`，pending仍为 `real-ext-payer-010` round1；没有核销、reconcile、acknowledge、rebind或重发。
- `state-abl-on2` SHA仍为 `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9`，原内部pending=null；不因本次B把历史授权佐证缺口改成已闭合。
- 此轮只核对上述指定文件及既有C1证据，不声称重新完整审计所有旧账户/轨迹。新账 `account_prior_history=unknown` 保留，旧未知费用不填0。

唯一真实容器ID `fb60067d8892471dee845b299e4736f26602049333778a4ddb6d17060f53fe10` 已确认退出、无OOM、无restart后精确删除；查询该ID无遗留。只使用Docker已有默认网络，没有创建owned网络或world，不删除其他资源。日志、state、receipt/seal、授权与失败处置依据均保留可读；`audit/finalize.py` exit0再次检查清理和state字节。

本次所有项目检查成功，无需要补跑的失败；没有重跑全仓pytest/unittest，因为生产代码/测试/依赖没有变化。PR51既有anthropic导入错误和skip不因此变绿；旧失败日志及原0a8449e初审结论不改。

文档落盘后另在禁网无Key容器核对本地链接、三笔原usage/费用的Decimal求和、receipt/seal/accounting引用、cleanup及候选JSON未变，exit0，见 `evidence/docs-check.json`。Git只显式暂存本报告及短状态，不上传授权JSON、真实账/收据/wire、认证文件、vendor或原始日志。

## 5. 结论与下一边界

当前固定identity已有自己的真实coding-B成功收据，证明本次固定自造代码工具往返、原接点和可信用量/结算闭环；不复用旧B冒充此证据。**本次1次B授权已消耗完毕**，不再发模型请求。

这次没有验证CHI业务、真实摘要/恢复触发与端点兼容、摘要忠实度/净费用收益、Y shadow、患者、正式Harbor或官方评分；`official_reward=null`。旧C1历史授权佐证/C5会话支撑及正式交付缺口仍保留。可独立推进的下一项是准备报告第8节所列DeepSeek包外operator开关透传离线任务；本次没有派发或接管该生产实现。摘要和恢复仍各需接线审核、固定实际config/hash及各自具体真实许可；新B通过不会自动批准业务C或Trial。
