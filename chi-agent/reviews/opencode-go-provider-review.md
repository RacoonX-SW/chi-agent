# OpenCode Go / DeepSeek V4.1 Flash 适配审核

日期：2026-10-28（Asia/Shanghai）。PR #20 已在 GitHub 核对合并；fetch 后基线 `dac0f2459718231aa7d1c67666ae85874d1227c6`，写入前从干净主线建立 `codex/opencode-go-provider`。同一个 gpt-6.1-terra/high 实现；主代理负责规格、独立审核、教学及 GitHub。此报告只记录 Q，不改写 P 的已见题证据。

最终实现 `5ea044dcefe1bad88fecb69c078078d22df06182` 已完成独立离线验收与真实 coding 工具闭环。两个真实 attempt 中首次因本地终止响应契约过严失败，修复并显式接续后第二次完成；全部失败、用量与账目保留。结论仅为 Go 接入和固定 coding 探针，未将 CHI 正式任务或临床评审切到 Go。

## 范围与官方资料核验

用户在本地 `.env` 新增 `OPENCODE_API_KEY`；禁网 Docker 仅输出两个 Key 的存在性，确认原 `DEEPSEEK_API_KEY` 与新增项均存在，未打印值、长度或前缀。新 Key 不替代旧 Key，凭据不进入 Git。新 Go provider、USD 核算和固定 coding SDK 工具探针供下一阶段正式入口使用，本轮不迁移 K/J/临床评审或打开正式 `live`，不重复 t013/t019/Claude/F.5。

2026-10-28 读取一手资料：

| 事实 | 来源与结论边界 |
| --- | --- |
| Go 模型及路由 | [Go 官方文档](https://opencode.ai/v2/docs/console/go/)列 `deepseek-v4.1-flash`、`https://opencode.ai/inference/go/openai/v1/chat/completions`；pay-as-you-go 路由不同，不能静默替换 |
| 上下文 | [DeepSeek 规格](https://api-docs.deepseek.com/quick_start/pricing/)与 [OpenCode 模型元数据](https://opencode.ai/data/deepseek/deepseek-v4-1-flash)标为 1M，输出最高 384K。标称容量不等于本轮路由实际长上下文验证 |
| `[1m]` 说法 | [DeepSeek Claude Code 官方示例](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)确实用 `deepseek-flash[1m]`；这是其客户端/Anthropic 接入配置，不是 Go Chat Completions 的正式模型 ID，不作通用扩容开关 |
| 客户端身份与用途 | Go 要求自身 UA、每会话稳定 `x-opencode-session`、typical coding agent traffic；CHI 非编码任务与独立临床评审支持未确认，不假称已禁止或已许可。本轮仅固定自造代码样例 |
| 用量与费用 | [Inference API](https://opencode.ai/v2/docs/console/api/inference/)区分余额实扣 `cost`、价目价值 `list_cost`、套餐消耗 `allowance`（均 USD）。订阅月费另计，余额扣费为 0 不等于推理无成本；不与原 CNY 相加 |
| 套餐与隐私 | 当前 Go $10/月，V4.1 Flash 额度按月及滚动窗口限制，并非无限。DeepSeek 当前 ZDR 标明仅至 2026-10-31，十一月须复核；当前文档没有绑定 Go 到 native 的 1017 快照 |

## 固定实现与离线审核

当前 OpenSpec 为 [Q 设计](../openspec/changes/opencode-go-provider/design.md)。实现子代理首轮停止后，主代理完整阅读新模块、profile、测试及其调用的旧 SDK 历史兼容/usage helper，发现空目录预检、历史覆盖、固定工具描述和诊断留证需要补强，交回同一实现者。首轮没有真实 API；其旧测试一次因未挂 vendor 而失败，补齐只读挂载后通过，不能当成源码缺陷或省略失败。返工后的固定身份及实际复验见下文。

首次固定候选 `ef249f6f6c332d7608ec8a1143bbc6372f450aac`：新增 Go 模块、profile 和合成测试，不改 native 生产源码、profile、锁或镜像。`create_client()` 提供当前 coding 契约下的 SDK client/model；`GoGuard` 同时约束请求、历史与核算，不是可直接发送任意 CHI 指令的通用入口。`_run_probe()` 使用锁定 Agents SDK 的 `Agent` / `Runner.run`，两个纯工具分别读取自造错误函数与对修改后的 AST 校验，不执行模型生成的 Python。SDK 空历史 helper 复用旧实现，reasoning 只对同 Go 路由/模型回放，tracing 在运行期间禁用后恢复。

GoJournal 在唯一 namespace 中先持久预留，再调用真实下层 transport。可信 token 和三项 billing 在验证消息/工具前结算；HTTP/未知用量保留 pending，未知 billing 或异常账源保留已知部分并 halt。run 保存受限本地 request/response JSON、usage 细目、hash、工具事件与最终输出，不保存认证头或 session 原文，正文中的秘密会被拒绝且不落原文。旧 CNY 全程不参与新账累计。

复用 dev `sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`（Linux arm64、Python 3.12.15）、H SDK 与 K PDF 卷。无安装/下载/改锁，G/H 未重做。主代理用 `git archive` 固定候选，只读源码/vendor/依赖，空 tmpfs data/runs、禁网、无 Key/socket，全量 **348 tests / 143 subtests** 通过（pytest 18.49 秒，包装总 19.184 秒）。初次两条 Docker 命令因 archive 中不存在空 data/runs 挂载点而在容器初始化失败；补齐空目录后重跑通过，第一次没有执行 Python 或 API。

主代理独立脚本另通过 7 组检查：空目录/孤儿历史、真实 SDK 空 content/reasoning 保留、删历史/改描述/额外消息字段拒绝、redirect 一次即停、estimated 不当实扣、响应秘密安全停止、结算证据落盘与 pending 释放之间中断后阻断。命令采用 README 同镜像与卷，在受审快照运行 `python -m pytest -q -p no:cacheprovider tests` 和本地 `check_independent.py`；证据为忽略目录 `runs/opencode-go-root/evidence/{pytest.log,independent.log}`。

## 真实接入与完整尝试

真实执行前，用户确认 Extra Usage 已关闭；主代理核对 23:05 起处于允许时段，旧 K/review pending 均为 null。禁网加载配置仅核对存在性、对固定 SDK 三条合成 request 正文检查两个配置秘密均不在正文，并保存身份/hash/布尔元数据 `payload-preflight.json`。再在禁网容器准备只含 Go Key 的 0600 临时 env 文件；外网运行只挂受审源码、SDK 和 Go 输出，不挂 `.env`、任务、手册、vendor、旧 runs 或 socket。Key 仅发往官方 Go endpoint 的 Bearer 认证。

实际固定命令为：

```sh
docker run --rm --name chi-go-q-coding-20261028-001 --read-only --tmpfs /tmp \
  --env-file /tmp/chi-go-auth-20261028/go.env \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/scripts:/model-deps \
  -v /tmp/chi-go-ef249f6/chi-agent:/workspace:ro \
  -v "$PWD/runs/opencode-go-development:/workspace/runs/opencode-go-development:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro -w /workspace \
  chi-agent-dev:latest /opt/venv/bin/python scripts/opencode_go_provider.py \
  smoke --run-id q-go-coding-20261028-001
```

| attempt | 结果 | 请求 / 工具 | input / output（含 reasoning） | 秒 | 余额实扣 USD / 价目价值 USD / 套餐消耗 USD |
| --- | --- | ---: | ---: | ---: | --- |
| `q-go-coding-20261028-001` | 本地最终响应校验失败；两工具已返回/验证 | 3 / 2 | 1,372 / 106 | 4.621 | 0 / 0.00015650 / 0.00011737 |
| `q-go-coding-20261028-002` | complete，验证并正常收尾 | 3 / 2 | 1,372 / 108 | 7.430 | 0 / 0.00015770 / 0.00011828 |

首个真实 attempt 三次均为 `deepseek-v4.1-flash`、`billing_source=go`，可信用量已逐请求结算；cache 768、reasoning 19（已含 output），没有 pending/halt、没有自动重试。inspect_code 和 verify_patch 各一次，代码修改验证通过；最终 `stop` 消息仅含 role/content，没有 reasoning_content，且 reasoning_tokens=0，被过严的本地响应契约拒绝为 `go_response_invalid`。这属于接入工程故障，不是业务决策或 API 超限，也不把它从历史中改写成成功。

据此补规格：终止消息允许可选 reasoning 字段缺失/null，工具阶段仍严格；新源码需显式 rebind 保留旧账。没有百万 token 实测，没有 CHI/评分调用。

## 兼容修复、源码接续与最终独立复验

最终候选 `5ea044dcefe1bad88fecb69c078078d22df06182` 只在 Go 新模块内修复终止响应检查并增加显式源码接续；native 模块/profile/锁保持原字节。`rebind_source()` 持原锁，要求 profile SHA/SDK 不变、无 pending/halt、各项用量及 billing 完整，先审核历史；写 `.rebind-pending` 后归档原 accounting 字节并 fsync，登记 before/after、原账 hash、每份旧 run hash，最后才释放标记。中途失败保守阻断，后续不会自动清标记/恢复；新尝试审核整条归档与身份链，旧 run 不被改写成新源码运行。

实现者受影响 Go/SDK 自测为 52 tests / 50 subtests。主代理再次从新 Git archive 独立通过全量 **354 tests / 143 subtests**（pytest 17.86 秒，包装 18.468 秒）及前述 7 组独立边界；新增 `check_replay_rebind.py` 只读复制真实 Go 账目，在临时目录完成：

- 三份实际响应经新 SDK/guard 回放，工具闭环和最终回答通过，三条 request 正文与首次真实发送逐项完全相同；无外网调用。
- 新 identity 未接续时拒绝，显式接续后 token/三项 USD 原值保留；原账字节归档、旧失败 run 字节不变；之后可在同累计内继续。
- 篡改旧 run 字节或中断源码转换时拒绝后续；中断保留标记和旧原账，不能自动回滚清零。

证据为 `evidence/{pytest-final.log,independent-final.log,replay-rebind.log,replay-rebind.json}`。首次原账 SHA-256 `da0ec781d1ff385a62fcb1ee99ea99d10ba3b8082afe6c71006577f77b5acd78`，旧失败 run SHA-256 `7b09f40ac3dd0588327132d9eb99e13f5a548c1cdc3f4bcac009c0e85c758d88`；以上只披露允许元数据，不上传原始响应。

23:16 后以最终快照禁网执行一次 `rebind-source --reason 'Accept optional reasoning_content on final Go stop replies'`，实际转换 `9b3c2066466b49fe9ba6a21e8375c553`，原账 hash 与独立副本一致。随后沿用上面的相同最小运行命令，将快照替换为 `/tmp/chi-go-5ea044d/chi-agent`、容器和 run-id 后缀替换为 `002`，做规格明确的一个新 attempt；没有自动重试。第二次实际完成，两个工具各一次，无人工代选。该次 final 带 reasoning 字段；缺字段兼容由第一份真实数据的离线回放验证，不能声称第二次也触发缺字段路径。

## 总用量、保留与清理

本轮所有真实尝试共 **6 requests / 4 tools**，input **2,744**、output **214**（其中 reasoning **34**），cache read **1,536**。两次运行内部耗时合计 **12.051 秒**，从 `_run_probe()` 建账后计时到收尾，不包含离线准备和审核。Go 返回的项目累计余额扣费 **0 USD**、价目价值 **0.00031420 USD**、套餐消耗 **0.00023565 USD**。三种数值不可相加；它们来自 provider usage，未独立对账到账单，订阅固定月费 $10 另计。真实探针已出现缓存命中；这不能推广为长任务的缓存命中率、费用或可靠性。

native 历史保守估算仍为 P 报告的 **121.571472 CNY**，原约 50 CNY 新增规划的口径和余额不因订阅自动重置。本轮不向它加美元或把 Go 的实扣 0 当作没有额度消耗。Go 账本标明 account_prior_history=unknown，只表示本项目已记录部分，不宣称账户历史消费或余量已核清。

主代理运行前保存的 **42,739** 个旧文件最终逐字节哈希相同，未清零或改写旧失败、费用、claim；Go q001 原文件也与接续前 hash 相同。最终 Go 账目在只读副本的完整历史审核通过，pending=null、halted=null，仅一次显式 source transition。所有 Go 新文件经禁网检查不含两项配置秘密。两次 `--rm` 容器均不存在，临时 Go Key env 文件及其专用目录已删除；没有创建世界/网络资源，没有修改 `.env`。证据 `evidence/post-audit.json`，原始运行留在忽略的 `runs/opencode-go-development/`。

首次推送前对当时明确的 13 个变更文件禁网检查：无两项配置秘密、本地 Markdown 目标存在；不含 `.env`、vendor、数据或原始运行，证据 `evidence/upload-audit.json`。`git diff --check` 通过，文档补齐不改变受审 provider 源码身份。

## 下一步

正式评测入口及提交包仍需独立接线、源码身份和部署验证；先核对 Go 的 CHI 非编码用途支持、十一月隐私条件，再扩展当前固定 coding 请求契约及官方 harness 的角色/工具边界，不能只更换 Key 或删除 `live` 拒绝判断。若该用途不在套餐支持范围，保留的 native 路由仍可作为明确的备选，不静默 fallback。下一通用改进优先为提供方协议回归样本：对可选终态字段和工具阶段必需字段分别建契约，用已留存响应离线复现，避免为了排协议问题反复付费。

这次教学已结合“标称上下文/客户端后缀/单次输出”和“工程拒绝/模型修正验证/正式任务成功”展开；没有新增用户亲自修改或运行 SDK 的证据。t013 收束、t019 付费暂停、Claude/正式 live/F.5 原边界继续保留。Q 已推送并创建 base=main [PR #21](https://github.com/xsw932187210-cell/chi-agent/pull/21)，交用户审核，不自行 merge/auto-merge。

用户随后澄清避峰仅针对官方 API，OpenCode 可全天安排已授权工作；现行规则见[协作约定](../../COLLABORATION.md#deepseek-api-调用时段2026-10-28)。已在同一待合并 PR 更正文档，不改变以上实测时刻、源码身份、原始证据或账目；本次修订没有新增模型调用。
