# S：Go CHI 混批恢复与完整终态验证

日期：2026-10-29（Asia/Shanghai）。本轮按[有界规格](../openspec/changes/go-chi-batch-recovery/design.md)推进；在实际证据完成前不预填通过。

## 起点和范围

GitHub 实际核对 PR #22 closed/merged，合并提交 `575b6d1ae5d1f7944166e92a22ce33d3f9e46fc9`；fetch 后最新 origin/main 一致，旧分支干净，从该点建立 `codex/go-chi-batch-recovery`。R 失败/账目/原世界终态缺口保留，不追加开发到已合并分支。

用户批准上一轮提出的混批恢复、可靠捕获与账目接续方案，以及最多一个新 B、两次 t012 开发回归、两道预先冻结新题各一次。Go 额度按充足规划，不受 native 避峰限制；模型/共享50请求、零自动重试/回退、未知阻断、Extra Usage 关闭、USD/CNY 分账继续。Claude、Go 付费临床评审、t013/t019 和完整 Harbor/F.5 不在范围。

一个 `gpt-6.1-terra / high` 实现子代理已成功启动，当前先只读接点分析。主代理规格/独立审核/教学/Git，单一实现写入者；全部测试/运行在 Docker，已有引擎 29.5.3 / linux aarch64，不安装或改锁。

## 开发前冻结与旧证据

Docker 只按固定 tasks.jsonl 的五个兼容字段选择，排除原八题与 R 的 t012，从剩余四条取字典序前二，冻结 t014/t017；索引、规则和完整排除清单见 S 设计和忽略的 `runs/go-chi-batch-recovery-root/evidence/task-selection.json`。未读取 title/instruction excerpt/fixture 内容选题。仅从固定数据版本下载十个必要文件，约 10 秒完成，全部哈希和 provider/agent 服务元数据检查通过；不打印或交实现者/参赛 Agent 隐藏材料。

开始时保存旧 48,552 个文件与 30 个链接；两种 Key 仅检查存在，均为 true。用原只读 R 独立包完成旧 CHI/Q 全部请求、工具证据、seal 和 B receipt 审计，旧 CHI 主账原字节 SHA-256 `c6b69c6d73d6d507ae7f224625adfb9616d16675e9af984d7d935da8b1b52eb3`。旧两个 CHI attempts 的内容/失败/claim 保留，pending/halt=null；native 两账 pending=null。基线/旧账审计/资源预检均在 Docker 禁网且未调用模型，原始证据在本轮 evidence。

实现者接到 S 完整规格后才开始代码/测试/runbook 写入；主代理发现固定 export 部分字段仅限目标案件，按源码补明确的运行前/后只读资源快照要求，避免将局部导出计数称为完整非目标审计。尚未固定候选或执行本轮付费调用。
