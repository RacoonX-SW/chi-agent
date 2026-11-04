# 摘要专用生成预算修正（离线实施契约）

日期：2026-11-05。用户明确要求：从PR57移除E摘要续写卡，GPT主代理使用一个Terra/high子代理单独修正摘要生成预算，Docker测试、独立复审并开PR，用户合并后其他任务再交DeepSeek。本提案不启动真实模型/B/C/摘要/续写、world/Trial/judge，不读取Key/.env，不改旧账/pending/证据。

## 固定改动

- 新显式版本`chi-input-summary-v2`仅将**单次summary生成上限改为32768**。旧v1仍8192；两版本都默认关闭、每run最多一次摘要、占共享50；与主请求输出恢复/Y互斥。没有`summary_continuation`、新purpose、额外请求、重试或Runner重启。
- 主请求、主恢复continuation及患者8192，确认32768，coding-B1024不变；模型/Go端点、thinking enabled/high、system/task instruction、选区、阈值、来源/保护、候选JSON≤32768 UTF-8 bytes、节省量及所有时间窗口不变。摘要目标仍短，较大生成额度可被reasoning使用，不放宽最终schema。
- 摘要请求构造、guard请求与响应usage检查、journal reserve/settle/严格历史/inspect、策略profile及必要entry/runtime/trace版本判断同步按用途及摘要版本处理，避免全局替换8192。预算取值可用有界共享策略，但独立测试期望不能从同一策略函数生成。
- 现有context算法已按请求max_tokens预留；验证v2实际预留32768及边界，不无故重写算法。大于新限额的usage仍拒绝，其他用途不得借summary版本放大。
- entry与包外operator支持精确v1/v2，默认不传、互斥和shadow接缝维持；v1不被静默升级。GoChiHarness仍默认off、无摘要开关，正式透传归后续A–D/C采用配置决定，本轮不扩大接口。
- 保留旧v1常量/语义或显式版本分派，旧summary request、saved source、evidence、seal和失败S可按原规则严格读取；新规则不重新解释旧8192请求。旧B不迁移到新identity，旧冻结包/候选JSON/exports不覆盖。

32768是本轮明确选定的、仅离线验收的生成候选值，扩大reasoning与正文共同空间；不是已实证的Go摘要上限/成功保证，也不证明忠实度或净费用收益。超过窗口仍length时保持原停止，不无限提高额度或接续。

## 必须验收

1. v2实际wire为32768/high/无tools；v1为8192；默认关闭且main/continuation/patient/confirmation/B保持各自上限。额外模型参数、坏版本/null/bool/数值/双开/shadow及错误用途仍早拒绝。
2. 真实SDK+MockTransport下v2摘要响应output_tokens>8192且≤32768、候选正文合法短JSON能settle/安装/checkpoint→下一main；v1同样usage必须拒绝。不能mock掉guard/journal/identity来证明路径。
3. v2 usage>32768、错max_tokens、坏/未知usage、length、schema/引用/保护失败与落盘故障按原规则停止；无第二摘要或恢复。用量已知而候选失败仍计入费用，未知pending不清。
4. context在32768预留下的适用与超限反例、剩余共享名额/每run一次、完整工具历史及旧主恢复两mode回归；候选JSON超过原32KiB仍拒绝。
5. 原v1合成历史及必要只读旧S实际证据严格inspect/summary通过其原历史验证，仍显示failed/length、20settled、pending=null、无checkpoint；原文件集合/hash不变，不上传其正文。
6. 适用配置/入口/算账/摘要/恢复集成回归、固定快照隔离Go包实际构建/identity/preflight、不打桩的profile一致性；Go新identity及wrapper变化如实记录，旧evaluation包适用hash比较。已知anthropic环境缺项/skip单列，不写全量全绿。

## 文档和交付

实现代理只写生产/测试并Docker自测；主代理负责相关说明、一次阶段报告`reviews/summary-generation-budget-review.md`和REVIEW_STATE短状态、固定候选独立复审、Git/PR。单写入者串行写同一checkout。必要包内runbook更新须在最终候选与身份核验前冻结；PR57规划不作为代码基线。

本轮独立分支从最新main建立，base=main PR；不merge/auto-merge。新候选所需真实B及任何摘要/九题运行另行具体批准，不复用已用S许可；离线模拟不冒充本次真实失败已被修复。PR57仅A–D后续任务，避免把摘要专项与新完成门禁/工具策略混为同一次实现验收。
