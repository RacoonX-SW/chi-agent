# 有界修复设计

## 基线、范围与职责

PR #23 已通过 GitHub 核对 closed/merged，fetch 后最新 origin/main 为 `25336ed774be934af1d7fc4765884d837e62ff15`，工作区干净，从该点建立 `codex/go-chi-timeout-recovery`。S 的失败、费用、原世界捕获、封存和三次未运行保留。主代理维护规格/README/学习/唯一状态/一份 T 报告及 GitHub；唯一 `gpt-6.1-terra` / high 实现者修改自有运行代码/测试/runbook，停写后主代理固定候选独立审核。

已有 Go 模型 `deepseek-v4.1-flash`、端点、thinking/high、请求/历史/schema/患者及角色门禁、SDK turns50、主/确认共享50请求、确认最多2次、输出8192/32768、B6/1024均不改。record_only/null cap、三项USD分列、未知阻断、零自动重试/回退、Extra Usage关闭继续。Claude、Go付费临床评审、t013/t019、完整Harbor/F.5不恢复。本轮无真实模型请求计划；旧 pending 未有充分结算依据前不能取得新B或迁移来源，更不能另建账根。需要恢复时另行固定计划，不把旧未运行配额自动挪到新来源。

## 按请求用途限定等待

固定时间策略纳入包配置/来源身份，集中定义并由入口验证一致。B/普通主请求仍使用 HTTP connect10/read60/write60/pool60 秒；确认请求只把 read 提升为360秒，其余相同。实际 I/O 在 Guard 内根据已验证 purpose 设置，不能被模型或 SDK 传入的无限/任意 timeout 绕过。

Guard 在发送和完整读取响应的 I/O 边界，分别施加 B/主请求120秒、确认420秒的绝对时限，防止持续小块读取无限延长。时限不覆盖已收到响应后的可信结算；已知usage仍先记录/结算再校验业务。内置 TimeoutError 与 HTTPX timeout 都归为 chi_timeout；外部取消仍区分为取消，保留未知请求/原诊断，均零重试。

按运行开始的单调时钟限定新请求准入窗口：B180秒、C900秒。窗口耗尽在 reserve/发送前返回明确运行时间上限，不新增 pending；窗口内已发出的请求允许完成其有界 I/O，不在窗口末立即取消。它是进程运行时限，不涉及日期/调用时段，不实现避峰时钟门禁、等待或唤醒。

操作者 runner wait 必须覆盖准入窗口、最长单请求I/O和至少60秒启动/停止余量：B下限360秒、C下限1380秒，上限沿用3600秒。更短配置在创建输出、world/runner或读Key前拒绝，旧S配置保留、不覆盖；runbook明确新字段/下限。硬取消、daemon/持久化故障仍可能留下未知，延长等待不保证必然成功。

## 保存关联元数据

新 Guard 请求在 durable reserve 时一并写入原请求证据中的可选 dispatch 元数据：固定版本、purpose、session SHA-256、发送准入时 UTC 毫秒和请求原字节长度。不能保存Key或会话原值，不改变官方会话头/用户代理、不新增猜测的请求头；不改模型请求正文。

旧证据原字节和引用完全兼容，无 dispatch 的历史保持原样。新元数据必须与同一请求用途/原文长度/类型一致并被既有 evidence hash 保护；缺件/篡改仍阻断。hash只证明本地持久性，不冒充提供方签名或认证；旧请求缺少的元数据不能事后补写。

## 未结算历史的只读检查

提供 `inspect-history`：先验证当前独立包/SDK/上游，再按 local 模式持旧Q→CHI锁，要求预期历史identity和当前主账SHA，执行完整结构/请求/工具/归档/seal/收据审计。允许合法的 pending/halt 作为被检查对象，明确报告 execution_allowed=false、已知费用的完整性、pending请求定位和缺少的证据。现有 audit-history/rebind-history 的 settled 要求不放宽。

可选外部 `--provider-record` 和 SHA 参数只作离线检查，解析用户提供、操作者核对出处的官方 Console单请求JSON。严格有界/无重复键/无链接/无NaN，核对event成功状态、端点/模型/方法、非stream、合法时间/次数/tokens、请求大小等。输出原始导出hash、精确Console cost及token观察，保留字段原本语义；不得将event.cost自动当作响应usage.cost、opencode.list_cost或allowance。原始account/user/session/location等只留本地，不放stdout。

新证据若有dispatch，则检查session哈希/请求大小/时间窗口与purpose的关联；旧证据缺少时明确 unavailable，不凭body hash、时间/金额近似或聚合总量声称唯一对应。官方导出缺少响应中的charged、billing_source、list_cost、allowance时逐项列出，不靠价目比例估算。即使Console显示HTTP200和tokens，也不改本地请求状态、run/seal/失败/claim或费用，不清pending。

本轮不实现泛化的人工收据结算或自动对账导入。只有完整可信、可唯一关联的计费证据及独立受审的结算方案才能解除阻断；只读检查的exit成功仅代表证据检查完成，不表示可运行。

## 验收

全部安装/测试/运行在已有Python3.12 Docker和锁定SDK/PDF/vendor中，禁网、源码只读、data/runs/tmp隔离，.env遮蔽。实现者不读取真实题文/轨迹/账本/Key，不操作Git或创建子代理。主代理保留全部旧data/runs文件hash（本轮新目录除外），真实账只允许只读检查，不作迁移/结算。

覆盖实际SDK的main/confirmation用途超时、正确HTTP extensions、总时限及取消诊断、零重试/未知阻断；准入耗尽不reserve、已发请求过准入窗口仍可完成；controller上下限在资源/Key前拒绝；旧/新证据校验、元数据篡改、pending/halt历史检查、坏hash/链接/缺件/并发、Console导出缺字段/错用途/模型/参数/数值/关联均不放行。可缩短测试用时或模拟时钟，但不实际等待数分钟。适当回归全部Go与受影响包测试，独立导出/解包预检，不重复G/H安装。

固定候选后主代理独立差异/调用链检查和Docker复验，用真实旧历史/用户JSON只读验证missing-field结论并证明主账/旧证据字节不变。所有成功/失败、工具/费用/耗时写一份T报告，代码/规格/说明显式提交推送、base=main PR由用户合并；不merge/auto-merge。
