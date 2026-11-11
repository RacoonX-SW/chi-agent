# M4：安全诊断 cause 实施契约

冻结：2026-11-03。用户确认M5/M6已由Gemini复审并合并PR47，要求节省Token、不重复验收，直接推进M4，全部完成后GPT统一审核。本文是Codex负责的M4前置契约；生产实现由DeepSeek承担、Gemini按既定方式复审，不把契约PR写成实现已完成。范围仅离线，真实调用/Key/world/B/C/Trial/判分仍禁止。

## 1. 目标与不变量

现有`chi_tool_batch_invalid`等对外安全分类保留，但诊断应能区别批次结构、重复ID、未知工具、参数JSON及参数schema错误。保留原整批验证/零派发、先结算可信usage、未知阻断和持久化失败停止语义；诊断不能影响是否授权、重试、恢复或继续执行。

不新增模型purpose、请求、开关或额度，不改模型/thinking，不修账，不扩大工具允许面。M4不解决C1旧unknown/后继授权、C5交流佐证或摘要语义忠实度。不给异常加自由文本日志，不把原载荷、参数、实体ID、工具名、路径、Key、session、堆栈或异常字符串写进cause。

## 2. 固定字段与版本

新写入的request diagnostic采用`chi-go-diagnostic-v2`，精确五个字段：

```json
{"schema":"chi-go-diagnostic-v2","kind":"diagnostic","code":"chi_tool_batch_invalid","elapsed_ms":0,"cause":{"schema":"chi-safe-cause-v1","stage":"tool_batch","reason":"arguments_schema"}}
```

- `code`继续现有安全码及其校验，含`ok`，不重命名、不将reason替换成顶层码。
- `elapsed_ms`为精确int、非bool、≥0，不改变原计时策略。
- `cause`成功`code=ok`时必须为null；错误时必须是精确`schema,stage,reason`三字段对象，不是数组/自由文本。其UTF-8 JSON≤256字节。
- stage/reason只允许下面的有限组合；未知版本/字段/类型/组合/过长输入拒绝，写入端报既有`chi_diagnostic_invalid`，读回按原历史损坏错误处理。
- 对不在精细映射内的既有安全错误，生产者使用`other/unspecified`，不从原异常文本推测。传给持久化接口的**无效cause对象必须拒绝**，不能被静默替换成unspecified。
- 旧`chi-go-diagnostic-v1`按原规则读取，保持旧文件及schema/校验历史含义；不补cause/null、不重写字节，不以忽略v2未知字段兼容。
- 不在accounting run/request对象添加新键或新launch许可；仍由原diagnostic_evidence_sha256绑定这份版本化证据。旧/新diagnostic可分别读回，但不重放旧run补诊断。

## 3. 精确stage/reason白名单

| stage | reason允许值 | 捕获位置/语义 |
| --- | --- | --- |
| tool_batch | assistant_shape, unfinished_batch, call_shape, call_id_invalid, call_id_reused, function_shape, tool_unknown, arguments_json, arguments_schema | ToolContract.accept_batch发生失败的分支；重复/未知字段及index问题属call_shape；无效/重复键参数JSON属arguments_json |
| request | route_invalid, body_invalid, history_invalid, budget_exceeded, time_limit | guard已确定的请求校验位置或固定安全码；header/history反馈不符属history_invalid |
| response | invalid_json, shape_invalid, output_truncated, too_large, http_error, secret_detected | 已确定的响应检查分支，不能将原body/HTTP文本拼入cause |
| usage | unknown, over_limit | 现有可信usage判断及输出用量上限 |
| transport | cancelled, timeout, request_error, unknown | 固定异常**类型**，不读取str(exc)/repr/args或traceback |
| persistence | evidence_write, state_write, log_write | 已确定的写入失败位置；不暴露文件路径/OS错误消息 |
| summary | rejected | 原摘要候选/来源/策略拒绝，保持既有顶层错误码 |
| recovery | rejected | 原恢复许可/历史/重放拒绝，保持既有顶层错误码 |
| other | unspecified | 未细分的原安全错误，不发明更精确诊断 |

原因由程序当前检查分支产生，不能由模型返回cause字段或工具正文覆盖。ToolContract可在原`ContractFailure`上增加受控属性，保留已有`str(exc)`/对外分类和调用签名兼容；不能把任意ValueError文本直接当reason。多项同时无效时按固定原校验顺序记录第一个已证实原因，不推断其他原因。`other/unspecified`允许未知内部异常被安全归类，不能把它当成已定位根因。

## 4. 实际接线和所有读取接点

建议一个仅依赖标准库的纯模块`go_chi_diagnostics.py`负责白名单、构造及v1/v2校验，禁止import runtime/SDK/账操作；确需不同文件组织可在不改变本契约时采用。新模块进入Go allowlist及entry preflight/import身份覆盖，不能漏掉隔离包依赖。旧evaluation包是否变化以实际构建比较，不凭目录推断。

- `go_chi_contract.ToolContract.accept_batch`区分上述9个原因，在commit seen/records/batches之前完整验证。只扩诊断，不改可接受集合和拒绝时的部分状态。
- `go_chi_guard`保留ContractFailure细因，转换为原顶层安全码，向`ChiJournal.record_diagnostic(code,elapsed_ms,*,cause=None)`传递受控cause。每次请求重置本次原因，成功/后续错误不得沿用上一次cause。缺省错误cause构造other/unspecified；成功缺省cause=null。
- `go_chi_auxiliary`使用相同v2写入及有限传输/响应/usage原因；不改变辅助parent、10次或共享50的关系。
- `go_chi_runtime`在已有run_log中可附加`safe_cause`（同三字段结构或null），记录guard已捕获的主失败；顶层safe_error_code不变，不让finally日志错误冒充原工具细因。无guard或无法安全确定时null。只改新日志，不写旧日志/原账。
- **reserve前拒绝**不能伪造已发送请求或新的request diagnostic。可由guard本次内存属性交runtime新日志显示安全原因；未发/无持久请求诊断必须如实区分。直接guard测试可检查安全属性和lower零调用。
- `go_chi_journal._validate`及`inspect_history`验证v1/v2。`_recovery_source`目前硬编码v1，必须同步支持合法v2的ok/null，否则新length恢复会被诊断版本阻断。其他ack/reconcile、summary安装/回放、B收据等所有读取diagnostic的路径逐处检查，不能只改通用load。
- `inspect_history`只在所读历史含v2时增加`diagnostic_causes`数组；每项精确`run,round,code,cause`，按原attempt/round顺序，且仅投影已hash验证的v2证据。旧纯v1输出不强加新字段；缺失旧cause不等于诊断成功。execution_allowed仍false，读取前后字节保持。
- M6现有summary输出schema和聚合语义不扩展；它至少应能经原inspect读取v2账。查看新细因使用inspect输出，不为本包重新设计M6 API。

不得用新诊断放宽旧校验、取消完整历史或批校验，也不以捕获诊断异常的方式继续执行原已失败请求。cause校验/写入本身失败沿原持久化/安全错误停止；保留已结算费用和原未知，不能为了补cause覆盖已有diagnostic。

## 5. 实施与验收工作包

- D0：核对本文全部读取接点、当前source/SDK与导出包边界，列有界文件清单。
- D1：实现纯有限schema、ToolContract细分及guard/auxiliary捕获，原拒绝集合/批原子性不变。
- D2：journal v2写入、v1/v2读取、recovery/summary/B/inspect接点、runtime安全日志及包接线。
- D3：Docker/Python3.12禁网测试、固定候选、Gemini复审及规格内返工、文档和PR。完成后GPT做项目累计审核，不逐包等GPT重复验收。

必要证明：

1. 9类工具批反例、整批含一好一坏、重复ID/未知工具/坏JSON/schema/未知字段；原错误码不变，seen/records/batches及工具派发均零新增。带患者/Key/session/异常文本的合成恶意值不出现在cause/安全日志中。
2. 真实固定SDK+MockTransport响应：可信usage的坏工具批先settle再拒绝、lower一次/工具零次；未知usage/token、取消/网络仍原pending/阻断，无自动重试/续写。请求前拒绝lower零次，无伪造请求记录。
3. cause额外字段、未知版本/枚举、错组合、bool、超长、成功带错误cause等写/读反例；在有效关联/hash的夹具上验证schema拒绝，不能只证明checksum不符。
4. 新诊断写入失败/日志失败保留原停止、结算和unknown语义，已有证据不可覆盖；不得把缺字段补零或通过清理修历史。
5. 基线旧代码产生v1合成证据，新代码inspect及适用旧B/恢复路径读取前后逐文件hash不变；新v2的ok可用于恢复/summary/B接点。真实SDK长历史摘要及length的适用回归通过；不将两种能力同时启用。
6. M6适用兼容检查，不重复M5/M6整包审核；受影响回归按调用面选择，不默认全部历史任务或真实轨迹重跑。原因分组不能代替9类批次实际分支覆盖。
7. 无源码挂载的Go导出包真实身份及实际SDK坏批/正常路径通过；比较Go和旧evaluation包manifest，记录新身份，不能复用旧B声称新版本已实跑。

使用固定Docker/Python3.12、禁网、无Key、无world；保留全部失败日志和合成费用/未知。作者自测与Gemini实际执行/受限审阅分别记录，Gemini无工具时不能写独立Docker通过。详细实施结果追加既有可靠性阶段报告，REVIEW_STATE只存短状态；原报告和失败不覆盖。用户最终合并，不auto-merge。
