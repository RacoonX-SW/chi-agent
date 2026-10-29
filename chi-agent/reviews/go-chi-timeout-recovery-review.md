# T：Go 确认超时与未结算证据检查

日期：2026-10-30（Asia/Shanghai）。按[有界规格](../openspec/changes/go-chi-timeout-recovery/design.md)完成独立离线修复验收；旧未知未核销，未恢复真实调用。

## 基线与证据

GitHub核对PR #23 closed/merged，merge/latest origin/main=`25336ed774be934af1d7fc4765884d837e62ff15`；旧工作区干净，从该点建立`codex/go-chi-timeout-recovery`。原S记录不改。一个既有Terra/high实现者先完成只读分析，主代理制定规格、独立审核及Git；真实模型调用仍被未知占位阻断。

源码核对：`local-confirm-patient`复用Go runtime的AsyncOpenAI，未覆盖默认`httpx.Timeout(60.0, connect=10.0)`，因此read/write/pool各60秒、连接10秒；read是等下一数据的间隔，不是总墙钟时限。确认输出上限为32768。用户已登录的官方Console对应时段最后记录显示约88秒后HTTP200；单靠此信息不能补账。

主代理只读使用官方Console已有会话，未改订阅/隐私/权限/Extra Usage。当前可见26条记录及Extra Usage=Off；未调用推理API。Copy JSON未能从浏览器剪贴板读到内容；Download JSON动作后下载事件等待超时，不能据此断言导出失败。用户随后提供同名实际文件，确认导出已落盘。只读Docker解析的两种挂载均成功，原文件字节一致；一开始直接Downloads挂载等待较长，另复制到忽略工作区再解析，无安装/新依赖。

用户文件原字节1592 bytes，SHA-256 `7baff44917627c01f472fe1945ca5a4115a4d74daf1b73dea283b95f71eb40aa`。event显示模型/路由正确、非stream、attemptCount=1、HTTP200/outcome=succeeded；duration=88269ms、首次token约87568ms，input39957/output15799（含reasoning14759）、cache读写0、Console cost精确`0.01547295`。导出没有响应usage.cost/opencode.billing_source/list_cost/allowance；不能将该cost复制到三项USD或按比例补allowance。原JSON仅放本轮provider-source忽略目录，账户/user/session/位置等不上传。

官方[Inference计费字段](https://opencode.ai/v2/docs/console/api/inference/)区分余额实扣、list_cost和allowance；[API说明](https://opencode.ai/v2/docs/console/api/)列有Usage读权限，但未给出可用于补齐该单次响应费用的公开接口。本轮不猜测私有API、读取浏览器cookies、扩充Key权限或新建Key。确认用途与十一月隐私仍按原限制处理。

## 实现与首轮审核

`go_chi_policy.TIME_POLICY` 纳入固定profile和包身份。`run_chi()` 保存运行起点；`ChiGuard.handle_async_request()` 完整校验后，在单调准入窗口内durable reserve，再按可信purpose覆盖HTTP timeout extensions并限定发送/读取总时长。主/B read60、I/O120秒；确认read360、I/O420秒，connect10、write/pool60不变。B/C准入180/900秒，窗口耗尽不reserve；已发请求不因准入窗口结束立即取消。operator先校验B360、C1380至3600秒等待范围，再创建资源/读Key；非日历门禁。

新request evidence保存`dispatch`版本/purpose/session SHA/UTC毫秒/原文bytes，账目保存dispatch_version并在完整审计交叉核对，hash保护元数据，旧request/wire/seal不重写。哈希是本地持久性证据，不代表提供方认证或签名。`inspect_history()` 先持Q→CHI锁并校验预期账身份/hash，完整验证合法pending/halt，再列出已知费用完整性及缺件；`inspect_provider()` 只读校验外部JSON/SHA，不调用模型或补账。Console cost用Decimal作为独立观察，不填三项费用；新记录可报告尺寸/session/time一致性，仍不声称唯一绑定或授予运行权限。

主代理首轮差异审核发现并交同一实现者修正四个边界：event.id与requestID不一致应拒绝；legacy虽无dispatch仍可核对已保存原文字节数；pending=null但halt=billing_details_unknown要列实际缺失费用字段；reserve的dispatch长度范围应与后续审计一致，非法输入不能先留下inflight。实现者修正后停写，未接触真实题文/账/JSON/Key。自测通过不代替独立审核。

## 固定候选与独立验证

候选 **`c587b446a54833393c1feb7deaeb3ac6fca47bfb`**；主代理从Git archive提取独立快照，禁网、源码/vendor/SDK/PDF只读、data/runs/tmp隔离，无Key/真实账挂载。最终独立包31个allowlisted文件，manifest **`a63e3b751e3218ffa998ae322b971a2d9d9df8fe5fb1de8117c31a8edb34c767`**，运行身份 **`1dfff8fb6bf78fcdfe9155597a8584ae333d8d0c126d346a84b7f2579609751d`**。33个运行/操作者源文件hash与时间条件冻结在忽略的`evidence/frozen-candidate.json`；实际模型请求和账内容写入的本轮预算均为0。

复用dev镜像`b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`、controller镜像`24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Python3.12；实现者使用的controller别名与主代理镜像ID相同。SDK卷、PDF卷及固定上游的全部身份字段与S逐字段一致，仅bundle manifest变化，无安装/改锁/重建/G/H重做。

| 验证 | 实际结果 |
| --- | --- |
| 实现者逐次Go回归 | 63 passed/2 skipped/20 subtests/2.17s；增加场景后63/3 skipped/20/2.12s，再91/3/20/2.33s、92/3/20/2.38s、94/3/20/2.89s；全部禁网合成，无失败测试 |
| 实现者controller及包 | controller两次均4项通过，最终0.005s；自测包build/preflight通过但为首审前临时产物，未用于正式验收/运行。日志完整保留 |
| 首审修正后目标回归 | 39 passed、15 subtests、0.54s，覆盖上述四个边界；一次apply_patch上下文不匹配在写入前拒绝，拆分后应用成功，无生产运行 |
| 主代理全量独立回归 | **425 passed、3 skipped、168 subtests、18.22s**；controller专用4项/0.004s通过，覆盖dev中依赖controller的跳过场景 |
| 主代理独立SDK八例 | 主/确认extensions和总时限、HTTPX timeout、外部取消、新请求过窗零reserve、已发请求跨窗完成均通过。使用真实锁定OpenAI SDK和MockTransport；7次模拟请求，真实请求0；未知新attempt阻断，秘密/会话原值不写wire |
| 完整旧历史副本CLI负例 | 坏主账hash、坏提供方JSON hash、未结算rebind三例均明确拒绝，副本主账原字节不变、无migration marker；原历史只读，不在真实账试写迁移 |
| 真实只读历史与用户JSON | 新包inspect-history exit0，完整Q/CHI/归档/请求/工具/seal/receipt结构审计通过；正文长度133919与导出相同，原缺dispatch/response/三项费用仍列出。execution_allowed=false、correlation unavailable、unique_match=false，费用完整性仍false |
| 独立归档 | allowlist归档真实解包、无Key/禁网且原源码不可见preflight通过，与原包identity JSON完全相同 |

独立脚本先以原S包核对：用户JSON的模型/路由/用途相关参数、字节数、服务端开始在本run窗口内、完成在客户端run结束后等十项候选关系均相符；原本地请求SHA `a40e691302ad3b0805ce035da78124c86f6056a7fc684976eb13fabffbe89d55`。旧请求没有持久会话关联元数据，时间/大小相符不自动构成唯一提供方绑定。也没有确认业务内容返回，不能把旧失败或未确认患者改成成功。证据仅在本轮`provider-forensics.json`和新包`actual-inspect.json`，不反馈参赛Agent。

最终主代理审计首命令漏挂现有SDK卷，入口import因缺httpx失败，尚未读取账；补回只读SDK/PDF后继续同一候选核验，原日志保留。浏览器的未派发读取/空剪贴板解析和下载事件超时见前文；真实模型/业务工具均未因这些尝试调用或重试。

## 用量、交付与限制

本轮 **真实模型请求0、业务工具调用0、Claude0**；新增余额实扣/价目价值/套餐消耗均为0 USD。旧Q/R/S仍为26发起、25已结算、1未结算；已知费用及历史CNY沿用S原账，不与Console观察cost合并、不把未知尾项改0。开发/审核Codex自身token账单未核实，不并入Go运行账。

独立归档 `runs/go-chi-timeout-recovery-root/exports/chi-go-entry-c587b44-bundle.tar.gz`，**125888 bytes**，SHA-256 **`e05f4736977b27ad8260ae12cc87ea245c7c1fb94f23e576c76f566ada25d4ef`**，含31文件+manifest和必要空目录；不含provider原JSON、任务、手册、vendor、Key、控制器或轨迹。外部依赖/公开输入/角色MCP仍由调用方提供，完整Harbor/F.5与官方评分没有验证。

代码在上述离线/故障/只读证据范围通过，尚无新来源的真实B/C，也未验证真实88秒确认在新配置下的结果、硬取消/daemon故障或完整计费恢复。旧主账identity不改为T；pending阻断来源迁移和模型调用。要恢复须取得可核验、可关联的完整费用来源，再制定独立结算/恢复方案；本轮没有实现或暗中启用人工回填/自动核销。

最终Docker核对旧 **49230文件/30链接** 全部原字节不变，旧范围无新增/删除路径；Q/CHI全部归档/wire/工具/seal/receipt完整，主账仍SHA `0832f113ccb8dd5342f06e6ae211af3eaf87e9e9d8032d65d1c85d705e0aa55b`，pending仍为S第9请求。33冻结源文件和归档身份不变；两种原Key存在、没有准备运行Key文件；342个新文件/18086444 bytes扫描无配置秘密，原JSON原字节不变。完整输出为忽略的`evidence/final-audit.json`，最终上传另按显式源码/文档清单和patch扫描，不上传该JSON或原始轨迹。

上传24份受审代码/合成测试/配置/职责文档，完整patch及路径秘密扫描通过；分支已推送。首次GitHub创建因连接中断未得到结果，先查询确认无open PR再补建，成功创建并附加base=main的[PR #24](https://github.com/xsw932187210-cell/chi-agent/pull/24)。这是GitHub传输重试，不是模型请求重试；由用户审核合并，未merge/auto-merge。文档提交和PR不替代上列c587b44源码验收身份。

## PR费用反馈修订（2026-10-30）

用户明确要求充分利用Go订阅推进开发/实验，不因金额或费用精度缺项反复暂停。PR #24实际核对仍open/unmerged，在原分支继续反馈修订；原c587b44离线通过与当时零真实调用事实保留。主代理将新版费用策略与旧严格策略分开，保持旧Q/native源码/账、Extra Usage关闭和零自动重试。

另因用户最初要求未知用量全局阻断，主代理只就“已有官方后台tokens但未完整响应的这次旧超时能否留档继续”澄清，用户明确选择**允许留档后继续新试次**。规格据此只授权一次精确目标的未结算留档：不settle、不改旧失败/wire/seal/费用、不重发旧请求；后续采用新候选、新B、fresh world，固定最多1B+1次t012+原冻结t014/t017各一次，总请求上限156。实际实施/独立复验及运行结果在本节接续，不预填通过。
