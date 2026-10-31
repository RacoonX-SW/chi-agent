# W：统一角色操作者与完整 CM 开发链路

日期：2026-10-31（Asia/Shanghai）。用户本轮显式授权离线实现、独立审核，以及满足前置条件后的三题各一次真实开发；本规格不恢复 Claude、临床评审、F.5 或官方判分。

## 基线与固定条件

GitHub 已核实 PR26 merged，merge commit 为 `5a621dc67afd8f0e26088b3b993615066a993229`；本轮 fetch 与 ls-remote 核实最新 origin/main 仍为该 SHA，而非仅采用交接摘要。新分支 `codex/unified-role-cm-lifecycle`。开始时已有 AGENTS.md、COLLABORATION.md 两项用户文档改动，保存原 patch 并完整保留，不将其算作 W 实现。

V 的固定实现、失败与有限通过范围只查 [V报告](../../../reviews/representative-role-baseline-review.md)。固定官方源码 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`、数据 revision `5ce88104df2a91e057619eb70fb51f56fc5949eb`，复用 V 的三角色资源 manifest、shared worlds、公开 PDF 投影、Python3.12 镜像及原 SDK/PDF 锁和卷。不更新 vendor 或依赖，不重做 G/H。

## 目标与接口

包外统一操作者接受显式、hash 绑定的配置：包/运行时/镜像、唯一 run/evaluation/task/attempt、角色资源 manifest、输出目录、等待策略及开发模拟条件。资源与角色、路径/hash/闭包在创建世界和读取凭据前预检。provider/payer/cm 使用实际 family、actor、MCP 端口及捕获契约；不将旧 provider 常量直接替换成其他角色。

操作者复用 `role_resource_preflight.validate()`、原 Docker/世界启动、`go_chi_entry` 身份/公开输入校验、Q→CHI 锁/历史审计/当前 B 门禁、`run_chi()`、SDK 工具循环/预算反馈及原封存。允许提取最小公共函数或默认关闭的注入接口，不能建立跳过这些控制的新运行路径。原包 CLI 不暴露开发 broker 开关，原 `evaluation_entry` live 拒绝、官方 Anthropic 默认与评分器不改；开发操作者、bootstrap、broker 不进入参赛 bundle。

CM 计费所有者与 broker 必须在同一个 runner 进程，共用一个 `ChiJournal` 和 billing mutex。Q→CHI 仅取得一次；工具派发持 MCP 锁等待世界时，回调只取 billing，不重入派发锁。患者请求保留独立 purpose、parent tool、稳定会话 header 和 wire/usage/诊断，不能伪装 Agent 请求或影响其剩余反馈。所有 main/confirmation/aux 失败门禁沿用并传播到整次运行；普通 MCP 错误不能屏蔽 broker fatal。

world 只有本轮 internal bridge，无公网网络、发布端口或模型 Key。runner 同时连接外网 bridge 与本轮 internal bridge。世界只通过随机短期能力 token 调用固定内部 broker；不做任意代理。能力文件仅供应必要进程、不可进入 Agent workspace/工具日志，持久记录只留 hash。世界启动继续使用原 entrypoint/venv；仅 CM 开发容器只读 bind `dev_patient_cb` 到 `/workspace/.venv/bin/cb`，同进程装入适配器。PA 不启用患者替换。

原 fixtures/persona/expectations 只供 world 初始化与运行后操作者。Agent 仅取得本题 instruction、公开 reference、手册和本角色 workspace；payer 恰为原冻结的四份公开 PDF，由原 service 物化后逐字核验。CM 导出保留原 bytes，无 world_id 字段时从实际挂载的初始化 manifest/world 文件核验来源，不补造字段，不削弱 PA 捕获。

## 预算、时间与终态

固定 `deepseek-v4.1-flash`、SDK base URL `https://opencode.ai/inference/go/openai/v1`，无 `[1m]` 或长上下文实测主张。主/确认共享最多50次实际请求、确认最多2次，主输出8192、确认32768；CM患者独立最多10次、每次8192；B最多6次/1024。零自动重试/回退。

沿原主请求 read60/I/O120、确认 read360/I/O420、main 新请求准入900秒；患者 read360/I/O420、world→broker430秒、MCP HTTP/SSE/ClientSession450秒。新开发 runner 总执行期限1500秒，取消/期限到达先阻止新工作，再有界收尾：broker/HTTP 最多450秒，操作者 runner 等待2040秒（1500+450+90）。次数是上限，不保证全部上限能在期限内完成。上述是本地开发策略，不冒充官方限时；不只延长单层等待。

正常和取消路径均在关闭账与封存前收束 broker/HTTP；若结果未知则保留 pending/失败证据，不能为成功退出强行结算。操作者先确认 runner 静止，再确认世界在途操作已收束；异常时必要的有界 drain 等待必须记录。只有静止后抓完整 provider/payer resources、权威初末导出、CM transcript/业务状态和容器日志，再清理精确 owned 容器/网络并用 ID 核验不存在。主错、捕获错、清理错分别保存；任何清理或终态证据缺失不能宣称完整通过。

静止证据依据实际MCP请求生命周期：完整返回（包括普通工具错误）后无未决/不确定请求，且broker已收束，才允许捕获；不以模型成功或exit0替代该证明。模型在工具完整返回后失败，仍须捕获已确认静止的原终态；工具超时/断开/取消后无法确认服务端结束，则标明终态未确认，不把固定等待时长当证明。共享派发锁内也检查患者fatal，防止同批后排业务工具或本地写入在患者失败后继续。

费用采用 record_only/null cap。余额实扣、价目价值、Go套餐消耗各自 USD 记录，不相加、不混旧 CNY、不清零历史。可信 tokens 而精确费用缺项继续，保留 null/warning；新结果/tokens 未知、损坏证据、明确非Go来源/额外余额实扣或资源未清理立即停止后续真实调用。Extra Usage 保持用户已确认的关闭状态，不修改设置。

## 历史与独立验收

真实调用前完整审计 Q/CHI 原账、唯一旧 S 第9请求 ack、source archive/迁移、wire 与 seal。旧超时已获明确批准留档、仍未结算，当前有效 pending/halt=null；不重复留档、结算、重发或删除。离线在完整只读历史副本上验证当前身份/有效 B、合法嵌套、取消/新未知与篡改拒绝；原目录逐字核验不变。身份改变时沿原显式 source rebind，不能更换账根或伪造 B。

一个 Terra/high 实现者负责 scripts/tests 与 Docker 自测，停写固定候选；主代理检查基线/候选差异及真实调用代码，再从独立快照在 Docker 复验。必须包含：三角色配置/资源/可见性拒绝；真实官方 world、真实 SDK/MCP 与合成模型 HTTP 的跨容器正常 CM 对话/STOP/持久化；能力/重放/并发拒绝；患者故障不再发主请求；取消/期限与收尾；终态和精确清理；完整旧历史链及默认/包隔离回归。不得用 FakeDocker 单测替代实际跨容器验证。

## 固定最小真实清单

独立离线通过后先固定实现/包/运行时身份、配置 hash、run/attempt、资源 hash、历史清单及人工隐私复核证据，才可按下表顺序串行执行。包身份完全相同且完整审计证明 V 的 B 对当前身份仍有效，则复用，不为刷新状态重跑；身份变化最多一次新的当前身份 B（6/1024）。

| 顺序 | runtime role | 唯一任务 | 次数 | 资源 manifest SHA256 |
| --- | --- | --- | --- | --- |
| 1 | provider | pa_t032_t032_o002_p01_new_referral_provider | 最多1次C | `7e3be9e6df8568d85ff31b847a46548a1754a39e941f126834e6adfb72ef42d8` |
| 2 | payer | pa_t011_t011_o003_p01_intake_payer | 最多1次C | `9d1c51b8e517cb30970334ac2dd9e597f9c1c7db9d148f3a64bb0ce359b09f95` |
| 3 | cm | cm_afib_moderate_anxious_001 | 最多1次C，辅助最多10 | `3c947fb0ba70aff0839d7c404fc4bd1265534245c84f284e1baf828a5a9b85dc` |

医院仍属 provider_new_referral 的不提交/关单分支，不称另一任务族。固定条件不按已见题文/隐藏评分调策略；不在 trial 内人工代选动作/修结果。每题一个新世界、唯一持久 claim，失败保留且不重复真实试验。业务未达目标但账目已知、证据和清理完整时，可按原清单继续下一题；工程前置/未知/异常来源/损坏/未清理则停止后续真实调用，不自动留档放行。未用次数不转移、不因额度充足扩量。

不重跑 t012/t014/t017/t013；t019例行复测、Claude、Go付费临床评审、F.5、配送和官方判分继续暂停，official_reward=null。程序性检查使用固定 `collect_all_verifier_checks(include_semantic_judge=False)`，保留 false/NA/覆盖不足；不能把合成模型、真实组件、真实模型业务、临床 verdict 或官方分数混写。

2026-10-31 人工查阅 [Go官方隐私说明](https://opencode.ai/v2/docs/console/go/#privacy)，当前 DeepSeek 月度 ZDR 仅明确到10月31日。十一月尚未获得确认；真实调用前按实际 Asia/Shanghai 日期再次人工复核，跨日不得沿用旧结论；无程序时钟门禁、后台等待或自动唤醒。用户已知 Go 非编码用途尚无官方明确许可并授权本轮开发使用，不声称官方许可。OpenCode 不受 DeepSeek 官方直连避峰限制。

## 文档与交付

README 写配置/命令/产物；本 OpenSpec 写边界与验收；唯一 REVIEW_STATE 校正 PR26 已合并并简记 W；详细环境、候选、所有失败/费用/耗时/清理集中一份 `reviews/unified-role-cm-lifecycle-review.md`；学习账本仅更新新功能教学和下一入口，不记用户已掌握。完成后显式暂存允许文件、commit/push 并创建 base=main PR 交用户合并，不 merge/auto-merge，不上传凭据/数据/vendor/原始轨迹/受限材料。
