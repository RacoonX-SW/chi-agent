# V：代表角色接线与本地Go患者模拟

日期：2026-10-30至31（Asia/Shanghai）。范围见[V规格](../openspec/changes/representative-role-baseline/design.md)。固定候选的独立审核与本轮最小探针已完成；实现者自测、开发接点及真实业务/官方判分分别取证。

## 基线、授权与证据位置

GitHub实际核对[PR #25](https://github.com/xsw932187210-cell/chi-agent/pull/25)已合并，merge/fetch后的最新origin/main均为 `c429ebec4d650fa56e65f2b2ded0a52851eb8c21`，工作区干净后建立 `codex/representative-role-baseline`。U已通过范围仍保留于[U报告](harbor-launch-coverage-review.md)，不把其合成模型验证改写为真实Go任务。

用户选择医院新转诊的不提交/关单分支；本轮冻结医院、payer、CM各一题并做无模型接线。随后用户明确要求本地CM患者模拟改用OpenCode Go/DeepSeek，同时保留官方Anthropic默认路径。新增开发模拟用途不授权Claude、Go临床评审、三题业务C、F.5或官方判分。最小真实清单及候选/历史前置条件以V规格为准，不能将未用次数转给新题或重跑。

一个显式Terra/high实现者负责scripts/tests与Docker自测，主代理规格、固定资源、独立审核、教学和Git。所有运行/下载/检查都在Docker，宿主只编辑、Git和调度Docker。原始证据在忽略的 `runs/representative-role-baseline-root/`：`operator-audit/`为主代理程序，`evidence/`为选题/资源/历史，`resources/`为最小受限投影，`implementation/`为实现者成功和失败。原数据、persona/expectations、手册、vendor、凭据及模型轨迹不上传。

## 公开元数据选题与资源冻结

固定官方源码 `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，数据revision `5ce88104df2a91e057619eb70fb51f56fc5949eb`。101项公开索引SHA256 `8751f9ae3132a861f389d85d66ba0cca5a52fddb17fe3e2ab4dc92f2804ccc91`。先按公开family/actor/kind/contract/终态/输入文件数量排除不兼容依赖和已读/已跑题，再按字典序固定每类第一项；不根据题文、评分材料或结果筛选。

| runtime角色 | 固定task | 选择范围 | 资源manifest SHA256 |
| --- | --- | --- | --- |
| provider | pa_t032_t032_o002_p01_new_referral_provider | 3个未见关单元数据候选，仍是新转诊 | `7e3be9e6df8568d85ff31b847a46548a1754a39e941f126834e6adfb72ef42d8` |
| payer | pa_t011_t011_o003_p01_intake_payer | 11个非P2P且排除历史/同批PA同case候选，4份公开PDF | `9d1c51b8e517cb30970334ac2dd9e597f9c1c7db9d148f3a64bb0ce359b09f95` |
| cm | cm_afib_moderate_anxious_001 | 25个CM候选，task actor care_manager映射runtime cm | `3c947fb0ba70aff0839d7c404fc4bd1265534245c84f284e1baf828a5a9b85dc` |

初始payer t008与此前已读provider t008同clinical case。在下载/读详情前发现并将跨family同case加入排除；保存v1选择及原程序后生成v2，不是见到失败后换题。v2选择SHA256 `bc2c6c51e8f167bc40dc2d4b14f88cdf837e446840594f88d1bde33b9778516b`，原记录中的Anthropic暂停描述是新增Go模拟授权之前的选择条件，历史原字节保留。

先用Hugging Face API在固定revision列元数据，再冻结22个文件的明确计划，SHA256 `1ac61800aee3c75f8dd216e20834cf569ab1a39ce2ab83973c6c5c561156e1bb`。只下载20项，其余2个PA world从原固定镜像复用；逐一比对官方Git blob/字节数并计算SHA256后才解析最小初始化结构。CM world和共享tool reference补齐；没有下载judge、solution或tests目录，也没有全量下载101题。

PA原镜像 `sha256:000ca5096533e5dcb4451dd524e2e6492a1250c23e183241f13cba4e338dad50`；共享world与manifest声明world_id一致。每角色显式manifest为 `evidence/role-resources-{provider,payer,cm}.json`，分别绑定7/11/6文件，PA每份含原双world，CM含共享world/ref。资源验证见 `download-plan.json`、`resources-download.json`、`resources-reuse_fixed_image.json`、`resource-verification.json` 和 `resource-structure-summary.json`。

payer原 `ServiceContext._materialize_incoming_request_pdfs()` 会把所选fixtures/request普通文件复制到payer/incoming_request工作目录，故优先复用现有workspace allowlist和锁定PDF读取器。预检必须限定该目录恰为冻结的4份公开PDF；原fixtures只挂给世界，不给runner。没有以公开PDF需求为由扩大隐藏材料权限。

元数据准备的首次失败保留于 `resource-list.log`：操作脚本名select.py遮蔽Python标准库select，导入HfApi时失败，未下载内容；重命名为freeze_selection.py后在同环境完成列举，日志 `resource-list-2.log`。首次误查不存在的宿主HF token路径失败，随后复用项目既有只读授权目录，没有输出token或新增登录。

## 旧历史与隔离副本

主代理先使用U已审核导出包、原SDK/PDF卷、Docker禁网与原项目只读挂载，直接按原契约审计Q/CHI。原CHI identity仍为 `0cd78f67750c313aa96ed45e6f6f986561d47e2b7ca2817ce56a46e080cd5f46`，主账SHA256仍为 `3814a9452869ef36e5be93c3fdc051348be6909741be4125c02e4181630bb362`。有效pending/halt=null，唯一旧S第9请求留档链完整，仍未结算。没有再次acknowledge、settle、重发或删占位。

U先前604个文件仍原字节。本轮另为完整Qroot（含CHI、source archive、wire、seal、ack）生成490文件的逐字节清单与隔离副本 `evidence/history-copy-original/`，见 `history-before.json`；后续新契约测试只在再复制的测试目录执行，原始副本和真账保持只读。490与604是不同范围，不能相互替代或合并成全部旧目录。

## 实现、独立审核与真实验证

**固定实现 `410a5b4f31444afd85f2850986a17d547a90f015` 在以下有界范围独立审核通过。** 首候选为 `e3ba44ccbc8578e7c4a4e29e380a19af3d2607bd`，Docker网络返工为 `9ce18195e1b1c645848065d45c1629d2125e7519`，最终提交补齐CM来源捕获。文档/PR存储提交不替代该实现验收身份。两个返工只改包外操作者，32个参赛包文件逐字未变。

实现代理在10月30日额度中断，10月31日恢复同一Terra/high继续，未切换模型或增加并行写入者。代理自测的64项/9子检查、真实loopback延迟、失败回滚、完整历史副本、操作者/CM捕获专项只是候选证据；主代理随后从Git archive和同SHA本地vendor克隆建立三个独立快照，源码只读，测试产物用独立目录。

### 实现职责与默认隔离

- `role_resource_preflight.py`将family/actor/role、必要文件闭包、world与公开输入的hash一并验证；`role_world_preflight.py`选择唯一角色端点，保留原始MCP响应、初末权威导出、两侧完整resources、容器日志、时间和精确owned清理。CM额外走`role_cm_capture.py`，PA仍走原helper。
- `dev_patient_adapter.py`复用原官方prompt、patient_profile、消息role翻转、STOP和SimulatorResponse；原CM service继续管理会话、回滚和终止。`dev_patient_bootstrap.py`/`dev_patient_cb`只在显式开发启动条件下于serve同一进程安装适配类。vendor和评分器未改，正式包不含这些开发文件，Go Key存在不会自动切换官方Anthropic。
- `PatientBroker`只接受当前run/session/parent工具的能力token请求；Go Key留在计费所有者。`AuxiliaryTransport`固定Go模型/端点/参数和零重试。主/确认仍共享50、确认最多2；患者辅助独立10，独立probe最多2。统一round和wire pending，辅助不能消耗或伪造Agent剩余次数。
- MCP派发锁与billing锁分开：主HTTP只取billing；工具调用持MCP锁进入官方service，患者回调只取billing。正常结算后返回；辅助未知/取消/异常来源使broker fatal，下一次主HTTP在发送前停止。合法parent工具与aux wire同时在途可审计，但仍阻断，不自动留档。

包manifest为 `5600fd738481264781cd011b625731bee2b66e9eb64178121ca64d7607bd0af4`，runtime identity为 `b29d6ecfdb7503fd0caecfd413aa06b8dd09cc6b0d4d71581b5951b33c5b3e60`。包从31增为32个allowlisted文件，仅增加默认关闭的通用辅助transport；所有开发模拟器/探针/资源操作者排除。SDK、SDK源码hash、PDF锁/包/wheel和上游身份与T逐字段一致。原`evaluation_entry` live拒绝保留。

Python3.12.15/Linux aarch64；复用原dev/controller/world镜像、SDK/PDF卷及U的Harbor0.20.0最小overlay，没有安装/下载新依赖或重做G/H。开发broker复用现有model锁中的Starlette1.10.0、Uvicorn0.54.0；原world的Anthropic0.101.0仅用于固定源码类型/默认路径，不发Anthropic请求。为完整测试在原world Python环境中只读复用dev镜像已有的pytest/pluggy/packaging/pygments/iniconfig五项测试包，没有升级原SDK。

### 主代理独立证据

| 检查层 | 实际结果与证据 |
| --- | --- |
| 最终禁网全量 | **487 passed、3 skipped、203 subtests，30.70秒**；`independent/full-tests-final.log`。3个缺Docker SDK的原操作者项另在controller中通过（0.39秒） |
| 默认/辅助SDK | 原三角色循环、确认/预算/旧费策略和真实Harbor类型/日志单元回归；新增真实loopback MCP→官方CM service→broker→真实Go SDK配合合成HTTP，含6秒响应、STOP和失败回滚。这里的HTTP全部合成，不冒称Harbor/真实模型任务 |
| 完整真实历史的隔离副本 | 实际旧490文件再次复制，显式迁移到当前包，真实CLI/SDK自然生成合成B3响应与当前receipt，再执行合成患者probe2响应；另副本模拟parent工具+aux取消在途，审计能定位且下一attempt拒绝。来源archive篡改被`chi_history_invalid`拒绝；原副本490文件不变。`independent/history-independent.json` |
| 运行时嵌套/失败传播 | `independent/runtime-aux/summary.json`：正常主2+aux1，Agent结果只计6/4 tokens、2 turns，患者另计7/5；患者超时由环境返回普通工具错误后，主请求仍只发1次、aux1次，下一主请求在wire之前拒绝，pending可完整审计 |
| 三角色真实世界 | 见下表：原固定官方entrypoint、真实MCP与真实存储，Key/外网/模型均无；初末导出与两侧资源完整、资源不变、owned容器精确ID均404 |
| 真实payer公开PDF | `independent/payer-projection.json`：物化的4份PDF与冻结源文件逐字hash一致，现有workspace许可和锁定reader能提取，provider路径拒绝；未输出真实PDF文本，也未扩Agent读目录 |
| 开发启动接点 | `independent/dev-cb-boot/result.json`：在独立容器仅bind覆盖`/workspace/.venv/bin/cb`，沿原tini/entrypoint激活venv后运行该受审文件，再同进程serve，health200；CB文件hash/实际serve进程/无模型Key/none网络及清理核验通过，5.906秒。复用镜像内旧t018仅作新启动接点烟测，业务工具0、模型0，不是重跑任务或重做G/H |
| 最终只读收口 | `evidence/offline-independent-acceptance.json`、`final-audit.json`绑定候选/包/配置、原历史、实际5次Go请求、首轮canonical载荷、费用、清理与秘密缺席；唯一旧ack仍原样 |

| 最终独立世界预检 | 公开工具数 | provider/payer资源数 | 总耗时 / MCP耗时 | 初末导出、资源和清理 |
| --- | --- | --- | --- | --- |
| provider-002 | 30 | 2202 / 0 | 7.716秒 / 0.922秒 | 完整、不变、已移除 |
| payer-001 | 41 | 474 / 130 | 12.201秒 / 0.936秒 | 完整、不变、已移除 |
| cm-002 | 16 | 2748 / 0 | 9.084秒 / 0.996秒 | 完整、不变、已移除 |

这些是初始化状态的只读预检。三题均只调用各自的一个队列/患者查询，随后调用`collect_all_verifier_checks(include_semantic_judge=False)`，证明固定检查入口可执行；其中false/NA反映尚未做业务动作，不能当失败trial、通过率或分数。没有执行WorkspaceJudge、verify_task聚合或官方reward。

### 独立审核发现及保留的失败

1. 锁定SDK的MCP ClientSession默认仅5秒。只延长HTTP仍会早断；显式aux路径的HTTP/SSE/session统一450秒，world到broker430秒，Go自身read360/总420秒；普通路径与原TIME_POLICY不改。真实网络6秒合成响应通过，不用付费请求试错。
2. 首个provider-001在官方health等待失败，原日志与失败结果保留、容器已清理。独立无任务诊断发现：Docker API `network_disabled=True`在本机表现为bridge配置/无附加网络，127.0.0.1可用而localhost解析gaierror；显式`network_mode='none'`保留localhost且无外网，官方entrypoint才可启动。未改vendor的健康检查或hosts。诊断证据`independent/network-modes.json`；首次诊断误认为inspect一定含NetworkDisabled可选字段，KeyError后仍精确清理，后续改成可选读取。
3. CM-001世界已ready，但PA捕获helper强制`export.world_id`。固定`WorldService._export_cm_state()`没有该字段，故初末raw导出未保存，结果保留unavailable、完整resources保留；没有补造成原终态。新CM分支严格核对care_manager及9个对象列表，原始export不增字段；从容器实际fixture manifest/expectations/world核对任务、actor、world和hash，标注`mounted_fixture_manifest_and_world_file`来源。CM-002完整通过，PA原契约未削弱。
4. 首轮独立全量有4项旧测试因只读快照缺可写runs失败，470项已过；加独立runs挂载后474项通过，最终加CM捕获返工后为上列487项。三个日志均保留，未修改旧测试来绕过权限。
5. 新CB启动烟测首次控制器缺scripts模块路径，在创建世界前停止；补PYTHONPATH后沿真实entrypoint完成。原entrypoint激活venv会把venv/bin置于PATH前端，因此运行说明使用隔离容器内的cb文件bind覆盖，不将单纯前置PATH误写成已接通。

文档收尾另保留首次检查环境缺父级COLLABORATION挂载导致的6个相对链接缺失；补只读父文件后，7份职责文档193个本地链接和代码围栏通过，`evidence/docs-checks-2.json`。`git diff --check`通过，首轮上传检查恰为30项源码/测试/规格和职责文档，真实Key值缺席，数据/vendor/轨迹/凭据未选入；原始私有证据仍留忽略目录。

## 最小真实Go验证与费用

先完成离线独立验收，冻结候选/包/两份配置/自造载荷与第二轮规则，再无Key禁网执行原`rebind-history`。旧主账原字节保存到`source-archives/0004-3814…json`，没有重新ack、结算或重发旧S请求。随后自然取得当前包的新B receipt，再执行唯一patient_probe。北京时间实际为10月31日，十一月隐私仍待届时人工复核，没有程序日历门禁或后台唤醒。

| 真实运行 | OpenCode请求 | 输入 / 输出tokens | 操作者耗时 | 余额实扣USD | 价目价值USD | Go套餐消耗USD |
| --- | --- | --- | --- | --- | --- | --- |
| v-go-b-20261031-001 | 3 | 1356 / 93 | 13.094秒 | 0 | 0.0001463 | 0.00010973 |
| v-go-patient-20261031-001 | 2 | 878 / 144 | 7.098秒 | 0 | 0.00016165 | 0.00012124 |
| 本轮合计 | **5** | **2234 / 237** | 两次耗时分列，不当整个阶段墙钟 | **0** | **0.00030795** | **0.00023097** |

三项USD是独立口径，不相加，不混旧native CNY，也不包含订阅固定费。新5请求的提供方billing_source均go、tokens/三项费用已知且已结算；零自动重试、零回退，无新增未知。`final-audit.json`中的B两个工具计数指`inspect_code`与`verify_patch`编码工具，不是临床业务动作；临床业务C仍0。余额0是这些请求返回的计费证据，不冒称已核清账户全部余额/消费。

患者probe只使用自造预约persona与两句固定问题，未含基准患者/手册/隐藏评分材料。第一轮请求canonical hash与事先冻结值一致，第二轮沿原role翻转携带真实首答，conversation session header稳定。两次回答均返回、STOP未出现，所以受2响应边界结束观察，存档的内存会话仍active；这不是CM外联业务会话完成。完成标记仅表探针及记账成功，进程/容器已停止并移除，不存在遗留临床资源。

实际有效pending/halt=null；仍只有原S第9请求未结算、唯一原ack。490旧Q/CHI文件中489逐字不变；U范围604文件中603逐字不变；唯一变化的CHI主账已在本轮合法来源迁移前以原SHA完整归档，旧9个attempt、旧来源前缀、wire/seal/ack均原样，新账追加B和patient两项。新主账SHA256 `8b89b9cdd89294d15cce3b09141424f20bbed0c5a33d1f04f824ea08b3999bee`。累计费用仍因旧未结算项不完整，不能把新5项完整写成历史全部结清。

## 当前限制

三代表题业务C、临床内容评审与官方reward尚未执行。三个角色的真实世界/资源入口已验证，开发患者的真实模型往返也已验证；完整CM业务中Agent→world→broker的跨容器编排尚未用一次实际CM题证明。当前提供显式bootstrap和`run_chi(..., auxiliary=broker)`开发接口，尚无受验收的一键三角色付费任务操作者。不得将loopback合成、真实启动烟测或自造患者probe合写成CM整题通过。

本地DeepSeek患者行为与官方Anthropic条件不同，不构成临床批准、官方成绩或模型等价结论。官方Anthropic默认、原判分器和原evaluation_entry的live拒绝保留；Claude/Go付费临床评审、t013/t019复测、正式配送/Harbor官方CLI与F.5继续暂停。V只补默认接入的类型/单元回归，未再次执行U的真实Harbor Trial，更未执行经Harbor的真实Go任务。

下一阶段先根据本轮冻结资源准备受审的统一角色操作者和CM broker/world生命周期，再另冻结医院关单、payer、CM各一次的真实清单与停止条件；不能只替换旧provider操作者的常量。CM还需实际验证外联开始/停止、评估与照护计划等业务闭环，以及原版程序/内容评分分别需要的材料。当前患者接口结果不解决U三题的10项未评审内容rubric，临床评审仍按其独立授权管理。Go非编码用途未获得官方明确许可，用户已知悉并授权开发使用；十一月隐私条件仍按实际日期人工复核。
