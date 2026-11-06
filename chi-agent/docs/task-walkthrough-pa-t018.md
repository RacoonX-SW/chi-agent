# 一个官方任务的拆解：头痛病例的新转诊

日期：2026-10-21（Asia/Shanghai）。用途：理解比赛，再制定基线和改进方案。

**当前证据等级：官方输入、静态工具说明和任务配置已核对；下文执行流程是解释性示意，不是实际轨迹。本题尚未运行，真实 reward、scorecard、耗时及成本均未测。**

## 任务身份与资料

- 领域：Provider Prior Authorization（医院侧事前授权）。
- 任务 ID：`pa_t018_t018_o001_p01_new_referral_provider`。
- 数据版本：`chi-bench-v1.0.0`，提交 `5ce88104df2a91e057619eb70fb51f56fc5949eb`。
- 后续基线计划使用的运行时代码提交：`4444a07fa68a4f1623f841a292a54e284fc8e7f7`；尚未建立本地可运行 checkout。
- 本次读取该任务的 `instruction.md`、`tool_reference.md`、`task.toml`。后两份为本轮新增下载；未读取该题的隐藏 expectations、solution、judge rubrics 或原始病例 backing store。
- 此题属于开发校准案例，不能在后续报告中称为未见过的验收案例。

## 1. 输入是什么

这是官方模拟病例：48 岁女性，有高血压病史，持续数周头痛，并出现新的左侧面部无力。转诊说明提出紧急的进一步影像评估，并说明医院门诊场所及社区影像排期的背景。这里只转述任务背景，不替 Agent 指定诊断、申请编码、适用政策或最终答案。

| 输入/资源 | 作用 | 当前核对程度 |
| --- | --- | --- |
| `instruction.md` | 病例摘要、角色限制、可用资源位置 | 已读取固定版本 |
| `healthverse` MCP | 查询病例和候选医嘱、读写医院侧业务记录 | 静态工具名已确认，未连接实时服务 |
| 受限手册 | 按角色索引查阅适用规则和材料要求 | 已下载；不将受保护内容复制进公开规格 |
| `tool_reference.md` | 本任务公开列出的工具名和部分枚举 | 已读取固定版本；不是完整实时 JSON schema |
| `task.toml` | 执行环境、MCP 端点、基础超时 | 已读取，不代表环境已经启动 |

Agent 应通过允许的工具取得完整病例事实和业务状态，而不是把 task 配置或评测预期当作病例证据。初始状态、患者/订单/案件 ID、工具参数和返回结构，仍需在实际运行时确认。

## 2. 能用哪些工具

该任务的静态工具说明共列出 **8 个命名空间、30 个方法**。这里只说明职责，不声称每个方法都需要在本题调用。

| 类别 | 已确认的方法示例 | 在任务中的作用 |
| --- | --- | --- |
| `chart`（3） | `search_patients`、`get_patient_chart_by_patient`、`list_candidate_orders` | 查找目标患者、取得病例和候选医嘱 |
| `cases`（3） | `create_from_order`、`get_case`、`list_cases` | 建立和查询医院侧案件 |
| `people`（3） | `list_contacts`、`list_ordering_providers`、`list_reviewer_contacts` | 获取可用联系人和开单人员信息 |
| `forms`（3） | `list_required_forms`、`save_form_response`、`validate_form` | 获取动态表单要求、保存和校验回答 |
| `docs`（5） | `list_case_documents`、`get_document`、`upload_evidence`、`upload_evidence_file`、`create_submission_bundle` | 查阅及附加真实证据，准备提交包 |
| `auth`（8） | `finalize_provider_determination`、`submit_authorization`、`check_status` 等 | 记录办理决定、实际提交和查询状态；也有补件、复核与申诉方法 |
| `inbox`（2） | `list_messages`、`read_message` | 读取模拟系统中的往来消息 |
| `p2p_session`（3） | `get_context`、`send_turn`、`submit_summary` | 工作流需要时进行模拟同行对话 |

完整方法名为 `命名空间.方法`，例如 `chart.search_patients`。本角色不开放 `coverage.*`、`worklist.*`、`fhir.*`；不能因业务上想查询某件事，就编造一个调用或改读底层存储。

静态说明还确认：

- `cases.create_from_order.priority` 只能是 `standard` 或 `expedited`，不能自行写 `urgent`。
- `service_type`、`site_of_service` 和证据 `kind` 也有受约束的枚举，不能将自然语言直接当作合法值。
- `auth.finalize_provider_determination.final_action` 有 `submit_pa`、`gather_more_evidence`、`do_not_submit` 三个值。它记录医院侧的提交前决定；实际提交还有独立的 `auth.submit_authorization`。
- 哪些参数必填、如何取得合法 ID、调用之间的依赖和返回值，以实时 MCP schema 为准。本次未取得实时 schema，不补写猜测的调用参数。

## 3. Agent 如何执行

下表是基于公开输入和工具职责的工作流解释，不是本题的标准解答或已发生的工具轨迹。实际调用顺序需要跟随工具契约和返回状态，可能有往返补查。

| 步骤 | Agent 的工作 | 应留下的可观察结果 |
| --- | --- | --- |
| 读题与发现工具 | 确认医院侧角色，读取手册索引和工具清单 | 使用的输入、版本和可用工具证据 |
| 读取病例 | 通过 `chart` 工具定位目标并查证事实 | 来自工具的患者事实及来源，不凭空补充记录 |
| 查适用规则 | 根据实际病例、服务和保障信息定位规则 | 对应规则依据和需要核对的材料项 |
| 准备申请记录 | 按合法调用创建案件，获取实际表单要求 | 真实案件/请求标识、表单 schema、已有文档清单 |
| 核对与组包 | 填写有依据的字段，附加真实材料，执行表单验证 | 已保存的回答、证据关联、校验结果及提交包（如适用） |
| 作出办理决定 | 证据支持时推进提交；有缺口则如实记录补证；规则不支持时保留不提交决定 | 与证据一致的办理决定，以及工具保存的实际业务状态 |
| 回读并结束 | 查询关键记录和状态，确认操作效果后结束 trial | 服务端记录、文档、状态和工具轨迹，供独立评分 |

角色工具的“调用成功”、案件达到某个状态、官方任务 reward=1 是不同的事实。Agent 的结束语不能代替系统里的案件、表单、证据和状态变化。

## 4. 运行环境和限制

本任务 `task.toml` 的基础配置如下；若运行器覆盖超时倍率等设置，实际生效值必须另行记录。

| 项目 | 固定任务配置 |
| --- | --- |
| Agent 超时 | 900 秒基础（15 分钟）；官方 submission 默认 2× → 有效 1800 秒 |
| Verifier 超时 | 1,200 秒（20 分钟） |
| 环境构建超时 | 1,200 秒 |
| 容器资源 | Linux，2 CPU，4096 MB 内存，10240 MB 存储，无 GPU |
| MCP | `healthverse`，`streamable-http`，容器内 `http://localhost:8020/mcp` |

这些是配置上限和资源声明，不是已测耗时、已占用资源或金额封顶。容器内的 localhost 也不是本机已在运行的服务。

## 5. 最后怎样判分

Agent 停止后，由独立的官方 verifier 检查世界状态、结构化记录、提交材料和操作轨迹；结合确定性检查和对规则依据/推理的 rubric 评审。Agent 不读取评分答案，也不自己宣布通过。

公开评分文档列出的医院侧检查维度包括申请前置条件、请求材料、提交和新转诊等阶段。它们是通用检查类别；本题实际适用哪些检查、具体通过/失败项，要由真实 `scorecard.json` 确认，本次没有借读取隐藏 rubric 得出答案。

- 所有必需且适用的检查通过：官方严格 reward 为 1。
- 任一必需检查未通过：官方 reward 为 0；部分完成率只用于诊断。
- 进程没有产生有效官方 verdict：本地收集记录保持 reward 未知，不能自行造一个 0 或 1；同时报告执行失败。若官方已产生包含评测器故障原因的 0 分，保留官方 0 分及故障原因。

| 文件 | 应检查什么 |
| --- | --- |
| `verifier/reward.json` | 官方单任务二值 reward |
| `verifier/scorecard.json` | `binary_reward`、适用/失败检查和阶段诊断；字段以实际文件为准 |
| `result.json` | 运行器结果、Agent 元数据、可用的 token/成本/耗时来源 |
| `verifier/exported_state.json` 与轨迹 | 评测后的世界记录和操作效果；只用于本地事后分析，不作为运行时输入 |

**本题当前真实结果：未运行；reward 未知；失败检查、耗时、调用量和成本均未知。** 官方文档中的其他案例成绩不能填进本题报告。

## 6. 下一步的真实基线

先补全官方运行环境及任务依赖，核对实时工具契约，选择一个实际可用的内置 harness 和精确模型，并确认一次 trial 的执行与费用边界。再运行本任务的一次官方 trial；不同时更换模型、改写 Agent 和修改判分器。

固定代码版本的 CLI 源码已支持以下命令形状。它是未执行的模板，`HARNESS`、`MODEL`、`RUN_ID` 仍须确定；当前数据也不是完整可运行任务。

```sh
# 在固定版本的 vendor/chi-bench checkout 中执行，待运行前提和预算明确后使用。
uv run cb experiment run \
  --dataset /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/data/prior_auth_provider/tasks/pa_t018_t018_o001_p01_new_referral_provider \
  --agent HARNESS --model MODEL -e docker -n 1 \
  --trials-dir /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/runs/RUN_ID/upstream
```

单任务路径选择这一题；单次尝试、并发 1 和生效超时等还需核对实际运行配置。运行完成后，先回答“是否真实执行并获得有效评分、在哪一步失败、耗时与成本多少”，再决定改进 Agent 的哪一部分。

## 官方来源

- [本题 Agent 输入（固定版本）](https://huggingface.co/datasets/actava/chi-bench/blob/5ce88104df2a91e057619eb70fb51f56fc5949eb/prior_auth_provider/tasks/pa_t018_t018_o001_p01_new_referral_provider/instruction.md)
- [本题公开工具说明（固定版本）](https://huggingface.co/datasets/actava/chi-bench/blob/5ce88104df2a91e057619eb70fb51f56fc5949eb/prior_auth_provider/tasks/pa_t018_t018_o001_p01_new_referral_provider/tool_reference.md)
- [本题启动配置（固定版本）](https://huggingface.co/datasets/actava/chi-bench/blob/5ce88104df2a91e057619eb70fb51f56fc5949eb/prior_auth_provider/tasks/pa_t018_t018_o001_p01_new_referral_provider/task.toml)
- [官方单任务运行说明](https://www.actava.ai/benchmarks/docs/quickstart)
- [官方评分输出说明](https://www.actava.ai/benchmarks/docs/scorecard)
- [固定运行时代码的 CLI](https://github.com/actava-ai/chi-bench/blob/4444a07fa68a4f1623f841a292a54e284fc8e7f7/src/chi_bench/cli.py)
