# T：Go 确认超时与未结算证据检查

日期：2026-10-30（Asia/Shanghai）。按[有界规格](../openspec/changes/go-chi-timeout-recovery/design.md)修复；实际通过范围待独立审核后记录。

## 基线与证据

GitHub核对PR #23 closed/merged，merge/latest origin/main=`25336ed774be934af1d7fc4765884d837e62ff15`；旧工作区干净，从该点建立`codex/go-chi-timeout-recovery`。原S记录不改。一个既有Terra/high实现者先完成只读分析，主代理制定规格、独立审核及Git；真实模型调用仍被未知占位阻断。

源码核对：`local-confirm-patient`复用Go runtime的AsyncOpenAI，未覆盖默认`httpx.Timeout(60.0, connect=10.0)`，因此read/write/pool各60秒、连接10秒；read是等下一数据的间隔，不是总墙钟时限。确认输出上限为32768。用户已登录的官方Console对应时段最后记录显示约88秒后HTTP200；单靠此信息不能补账。

主代理只读使用官方Console已有会话，未改订阅/隐私/权限/Extra Usage。当前可见26条记录及Extra Usage=Off；未调用推理API。Copy JSON未能从浏览器剪贴板读到内容；Download JSON动作后下载事件等待超时，不能据此断言导出失败。用户随后提供同名实际文件，确认导出已落盘。只读Docker解析的两种挂载均成功，原文件字节一致；一开始直接Downloads挂载等待较长，另复制到忽略工作区再解析，无安装/新依赖。

用户文件原字节1592 bytes，SHA-256 `7baff44917627c01f472fe1945ca5a4115a4d74daf1b73dea283b95f71eb40aa`。event显示模型/路由正确、非stream、attemptCount=1、HTTP200/outcome=succeeded；duration=88269ms、首次token约87568ms，input39957/output15799（含reasoning14759）、cache读写0、Console cost精确`0.01547295`。导出没有响应usage.cost/opencode.billing_source/list_cost/allowance；不能将该cost复制到三项USD或按比例补allowance。原JSON仅放本轮provider-source忽略目录，账户/user/session/位置等不上传。

官方[Inference计费字段](https://opencode.ai/v2/docs/console/api/inference/)区分余额实扣、list_cost和allowance；[API说明](https://opencode.ai/v2/docs/console/api/)列有Usage读权限，但未给出可用于补齐该单次响应费用的公开接口。本轮不猜测私有API、读取浏览器cookies、扩充Key权限或新建Key。确认用途与十一月隐私仍按原限制处理。
