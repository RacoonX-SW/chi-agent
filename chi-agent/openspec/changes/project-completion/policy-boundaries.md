# C4：用途参数与独立安全边界

本包登记当前用途、配置声明和执行/回放约束，补等价性与漂移反例。范围依据[设计第15节](design.md#15-可靠性治理与分阶段重构)；实际候选、环境、结果与未验证项只见REVIEW_STATE指向的阶段报告。不修改数值、运行模型/思考强度、默认启用状态或账目语义，不做常量集中化或重构。

## 1. 来源和职责

- `profiles/go-chi-entry.json`是Go入口的版本化配置声明；`go_chi_entry.CONFIG`是程序认可的完整期望结构。真实`_identity()`先验证包manifest，再以精确类型和字段全等检查声明；声明不能单独扩大安全边界。
- `go_chi_policy.TIME_POLICY`和`RECOVERY_POLICY`提供相应用途的固定策略，入口JSON保存严格同步副本；配置变化必须显式评审，不能仅为让检查通过删掉副本校验。
- runtime负责构造SDK参数，guard负责最终wire的独立前置/响应校验，journal负责reserve和历史重载验证；三者的重复有防御职责，不在本包合并成一次检查。`inspect_history`复用journal历史校验，不是另一份放行策略。
- `profiles/opencode-go-deepseek.json`/`opencode_go_provider.PROFILE`声明较早coding探针的提供方设置；其中6/1024不是CHI主循环上限。`request_budget.MAX_REQUESTS`用于共享计数提示，不凭提示文本实施准入。
- 患者模拟是显式开启的包外开发用途；辅助transport在包内，broker/probe不进入参赛包。相同数字分别记录，不能把患者额度或旧开发预算合并到主请求额度。

## 2. 输出与请求额度

| 用途 | 单次输出上限 | 次数/归属 | 构造或声明来源 | 独立执行/历史约束 |
| --- | ---: | --- | --- | --- |
| coding-B | 1024 | 6次；独立于CHI运行 | entry配置、`run_coding_b`、Go provider profile | ChiGuard coding分支；journal coding分支 |
| CHI主循环 | 8192 | main/confirmation/continuation共享50次 | entry配置、`go_chi_runtime.run_chi`、request_budget | guard最终wire和usage；journal reserve及load |
| 患者确认 | 32768 | 最多2次，计入共享50 | entry配置、`patient_identity_binding.CONFIRM_MAX_OUTPUT_TOKENS`及`go_chi_tools`调用 | guard可信确认context；journal确认子限额及load |
| length continuation | 8192 | 默认关闭；每链最多1次、每run最多2次，计共享50 | RECOVERY_POLICY及`go_chi_recovery`派生视图 | guard一次性许可；journal许可、reserve、load |
| 嵌套患者模拟 | 8192 | 独立辅助最多10次；不挤占/扩大共享50，最多合计60 | dev_patient_broker请求构造 | AuxiliaryTransport；journal parent/用途/辅助计数及load |
| 独立患者probe | 8192 | 同一probe最多2次，不是主共享50 | dev_patient_probe请求构造 | AuxiliaryTransport；journal patient_probe分支 |
| 旧SDK合成预算路径 | 128 | 3轮；离线CNY预算 | model_runner_adapter常量及budget_evaluation | 原合成适配器校验；不与Go参数同步 |

所有Go用途维持`deepseek-v4.1-flash`、thinking enabled、reasoning high、automatic retries=0。length追加是已结算截断的特许请求，不是传输自动重试；再次length、未知结果/token、取消、网络或持久化错误仍停止。8192包含模型生成的reasoning与content/工具参数，并非8192可见文字保证。

## 3. 输入与预留

| 项目 | 当前值 | 职责/来源 |
| --- | ---: | --- |
| 完整请求字符门限 | 3,500,000 | go_chi_context.DEFAULT_BUDGET.max_chars |
| UTF-8 byte输入估计+输出预留门限 | 1,000,000 | DEFAULT_BUDGET.max_estimated_tokens；启发式上界，未测真实tokenizer |
| 最低输出预留 | 8192 | DEFAULT_BUDGET.output_reserve_tokens |
| 实际有效预留 | max(最终wire.max_tokens, 最低预留) | check_budget；确认必须预留32768，B仍至少预留8192 |
| 文档context容量 | 1,048,576 | Go provider profile.documentation_only_not_measured，不是已测可用输入 |
| 响应用量输入安全界 | 1,048,576 | guard/auxiliary/journal独立usage检查，不与1,000,000估计门限混为同一用途 |
| wire请求/响应字节界 | 8 MiB / 4 MiB | guard/auxiliary/evidence约束，与token估计分别检查 |

完整实际wire中的结构、schema、工具参数、reasoning、中文均计入；以`max(canonical UTF-8 bytes, raw bytes)`作输入估计，不能仅数可见文字。旧v1证据按原版本规则读取，不能用v2核对结果回写旧历史。计量/预留不表示自动摘要已实现；本包不新增摘要用途或请求。

## 4. 时间用途

| 参数/用途 | 秒 | 当前来源与意义 |
| --- | ---: | --- |
| connect / write / pool | 10 / 60 / 60 | TIME_POLICY；guard最终request.extensions覆盖 |
| main/B/continuation read / 单次总IO | 240 / 300 | TIME_POLICY；read为socket等待，IO是整次异步wall timeout |
| confirmation read / 单次总IO | 360 / 420 | TIME_POLICY；最终用途决定，不能沿用SDK客户端main默认值 |
| patient simulator read / 单次总IO | 360 / 420 | AuxiliaryTransport当前独立硬边界；恰与确认相等，不共享额度/确认语义 |
| B / CHI请求准入窗口 | 180 / 900 | TIME_POLICY；新请求派发前检查，不是保证全程在此时刻完成 |
| 旧Go operator最低等待（B / CHI） | 360 / 1380 | TIME_POLICY，由go_chi_operator校验调用方配置 |
| 旧Go operator可配置最大等待 | 3600 | TIME_POLICY.operator_max_seconds |
| 统一role_runner运行 / 清理 | 1500 / 450 | role_runner的运行和收尾边界，不是main IO |
| 统一role_operator等待 | 2040 | role_operator配置期望和runner.wait，不和旧operator强行统一 |
| 患者bootstrap等待broker | 430 | dev_patient_bootstrap，broker HTTP等待，不是提供方read预算 |

超时表示客户端放弃等待，不能证明服务端未执行；用量/结果未知保留pending并停止。时间值相互有层级或用途关系，而非全部应当相等。本包不因表中窗口差异推断错误或提高任何值。

## 5. 验收与后续修改

用独立冻结的期望值及真实请求检验声明、SDK构造、guard、journal和context；有效包先过真实_identity，再对配置数值、类型、字段和嵌套策略改坏并重新生成合法manifest，须仍拒绝。不得只测checksum不匹配，或打桩核心身份函数再宣称配置已核对。

邻值/错误类型、不合法用途和耗尽额度必须在下层发送前停止；可信usage已返回则先结算再拒绝过大输出，不能把已发送的一次请求抹去。恢复及辅助额度采用真实合成journal操作，不能用破坏历史结构、绕过load来证明合法准入。

检查覆盖和现存保护应按实际测试报告说明，不把静态源码观察或已有测试名称当作动态证据。若发现漂移先确认是哪一个用途和哪一层，不为绿色测试修改门限或放宽历史。后续改参数需独立行为提案、身份/包比较和适用回归；真实运行是否要新B仍依实际身份与准入条件，不能复用旧收据冒充新验证。
