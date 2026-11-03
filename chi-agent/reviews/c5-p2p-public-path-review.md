# C5：t027 P2P公开路径、原证据回溯与独立审核

日期：2026-11-03（Asia/Shanghai）。本报告集中保存事实、失败、验证及限制，短状态只见[REVIEW_STATE](REVIEW_STATE.md)。

## 1. 范围、固定候选与结论

用户要求继续任务。主代理核实[PR44](https://github.com/xsw932187210-cell/chi-agent/pull/44)已合并，刷新到`origin/main` `3a83f1894ddd4fe061c53587ee650322d66794df`，新建`codex/c5-p2p-audit`。隔离worktree复用，原DeepSeek目录仍为`codex/reliability-boundaries` `7984b60`且无未提交改动，本轮未写其文件。

**C5只读核查及限定公开契约回归通过，原业务结果不升级。** 只新增合成测试及审核/任务/学习指针，无Agent、提示、配置、vendor或verifier修改，不新增题目专用规则。

1. payer-013/014均在finalize之前调用`p2p.record_outcome`，取得`completed/uphold_intended_adverse_decision`；随后`determination.get_summary`已返回`recommendation=deny`，最终以`overridden=false`作出denied。原“未完成P2P直接finalize”的解释不符合已核对的顺序。
2. 固定公开服务实际以P2P请求的completed/outcome解析最终来源；原MD记录保持`p2p_review/signed_off=false`与解析后推荐deny并存。不能从这个原字段单独推出finalize绕过，也不能事后改签核值来让检查变绿。
3. **交互事实仍有缺口**：两组运行的get_context调用均报无活动会话，目标导出无P2P session，未见成功send_turn/submit_summary，而模型outcome note声称讨论已举行。请求机械完成不证明实际讨论完成；本轮未识别到支撑这些交流陈述的会话记录，不认定临床/业务真实性通过。
4. 原未合并报告的21 true / 1 false（md.signed_off）保留，未重跑判分，也不把“仅期望选择差异”作为已证明的充分解释。没有读取隐藏期望值来决定应approve/deny或推定预期路径。

主代理负责历史只读审计、公开调用链、独立回放/复验、教学与Git；原唯一显式`gpt-6.1-terra/high`实现子代理（最初`fork_turns=none`）仅编写合成测试及Docker自测，未接触真实轨迹。实现停止后固定候选 **`9a8e0be3db4ec49a58e473b7cdfc4dd342062d68`**，测试文件SHA-256 `12f182002ef54fbe30e70e68cef400ee02f3241f1eef2eb69cf71bfeafcdb8b0`；主代理自有脚本和固定快照复验不以作者自测代验收。

**真实模型/摘要/续写请求0，Key读取0，无world/真实B/C/Trial/官方判分。** C1 payer-010未知与后继授权证据缺口保持，不改旧账或用新root恢复准入；输入摘要/M4/M2和全面重构不在本包。

## 2. 来源与读取边界

- 历史解释来自未合并提交`0ca0d45`的[批次报告第14、15节](https://github.com/xsw932187210-cell/chi-agent/blob/0ca0d45/chi-agent/reviews/real-external-batch-a-review.md)。旧文字、失败和21/22原样留存；本报告追加有依据的更正，不覆盖旧报告。
- 只读挂载`runs/real-external/state-abl-on2`、`state-v7`，选择payer-013/014的账、请求/响应、tool事件、seal；后续仅逐文件挂载两份`final-capture/.../exported_state.json`，筛选同一目标病例的MD/P2P/最终决定及相关状态。
- 首次捕获目录清单对四个文件做了大小/SHA登记，其中`expectations.json`只参与字节完整性哈希，未解析或输出其内容；`shared_world.json`也仅哈希。随后收紧挂载为指定exported_state文件，不再读取这两项。未导入任务expectations/solution/verifier或据其调参，未向测试夹具提供真实题目数据。
- 公开用户指令来自已发送首笔wire，要求记录review recommendation，推进MD decision、适用P2P，并自行finalize。它没有授权编造来源或交流事实。指令SHA `c0ac4a54f48a5a103f430d6b1ba1366b9d6147ddd8a66145ef7e3ff1c3e29da7`，两次一致；本报告不转载临床正文/手册/原轨迹。
- 固定vendor为clean `4444a07fa68a4f1623f841a292a54e284fc8e7f7`，仅核对公开services/review.py、determination.py、p2p.py及必要域模型/枚举。服务源码中通用workflow机制不等于读取具体任务的隐藏契约值，合成上下文没有`_expectations`。

| 公开服务文件 | SHA-256 |
| --- | --- |
| review.py | `d2868fef6a91e80d8b79f3c549b2a185230b5a815ec3544bf99bbb418401eb8a` |
| determination.py | `bcd986b22edd7d6a95710dfc2690771857248de68ecbcf7af5d296114450bdda` |
| p2p.py | `fbe0594391a9ff0b7c8e33bac5d202b9a98313f9ba9ab05b257938e9ee9323e6` |

## 3. 证据完整性及历史身份

主代理`inspect_history`在两root均返回inspected、execution_allowed=false；后者是只读reader语义，不是一次真实准入判断。读取前后**564个原账/证据文件**及两份指定导出hash不变，不构造可写原journal，不ack/reconcile/settle原账。

| 旧运行 | root / evaluation / attempt | 请求 | 原身份与完整性 |
| --- | --- | ---: | --- |
| payer-013 | state-abl-on2 / eval-abl-on2 / attempt-3 | 30，全settled | runtime `55b55cd73f73f82443b173f1d4e4be4d4e80315bda61e86ecc2e7be1ac497cb1`；该root380文件不变 |
| payer-014 | state-v7 / eval-ext-v7 / attempt-1 | 35，全settled | runtime `40a2e9757d77c2bc4e9398199e560bd8a2b1dd38c49b2d30a7e913ea4a6c6431`；该root184文件不变 |

第二项attempt以原账实际值为准，配置/报告标签不能代替原账。root内部pending=null不核销C1旧root的payer-010，也不说明账户累计已完整。

| 原物件 | SHA-256 |
| --- | --- |
| on2 accounting | `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9` |
| v7 accounting | `6e1db43361d2cf664b3ae9a1b923c31c512b028571ab3303630a56d3563f3b93` |
| payer-013 seal | `17cf4e8a445b80624a6dd1accc5b7dffb56ed3b92b3140342b7bcc30181ca131` |
| payer-014 seal | `fbb1ac6be1372ea117d63df60a8c233ecf9a6ac98557c383742220c0bfb755ea` |
| payer-013 exported_state | `62f823802cfe98386cf66f84a083801b7c5a4a453ffb0beb8e7a811f4176724b` |
| payer-014 exported_state | `419cf2f73b2c48a618e1ba9cc45698bb80551d2fe46f1435cc1c00156dd82e31` |

不少tool-evidence原包因`unparseable_escaped_body`只存hash、body_utf8=null。主代理未把缺正文当成无结果，而是从后继实际发送请求的tool历史恢复，逐一匹配原result SHA及证据文件SHA：**25个选定结果中22个由后继wire还原**。另核验130份请求/响应正文hash、25个响应参数与start事件指纹、399次对应tool历史重放hash。不是改写旧证据；投影和恢复结果仅存忽略目录。

## 4. 实际顺序与依赖关系

顺序按真实provider请求round和tool事件索引，不按模拟世界中相同的created_at时间推断。

| 事件 | payer-013 round | payer-014 round | 观察 |
| --- | ---: | ---: | --- |
| submit_md_case_decision | 11 | 14 | p2p_review，signed_off=false，创建并关联P2P请求 |
| offer_slots / schedule | 12 / 13、15 | 15 / 16 | 请求由requested/slots_offered到scheduled，尚无outcome |
| get_context失败 | 14 | 17、18 | No active peer-to-peer session；returned_error，未吞成成功 |
| record_outcome | 16 | 19 | 返回completed及uphold_intended_adverse_decision；不是pending状态直接finalize |
| get_summary | 17 | 20 | recommendation=deny，source=md_decision，来源record id与原MD相符 |
| finalize | 18 | 21 | decision=denied、overridden=false，返回case denied和determination；original_recommendation=deny |
| 后续get_summary | 22 | 26、28 | 已持久化的同一结果再次可见 |

目标导出交叉验证：原MD仍p2p_review/unsigned、关联的P2P request completed/uphold；determination原推荐deny、最终denied、overridden=false，source_record_id指向原MD。目标P2P session列表为空，没有成功send_turn/submit_summary事件。

模型note在两次record_outcome中声称讨论已举行、未提供足以改变评估的新资料。该段是**模型写入的陈述**，不是独立服务回传的交流记录。本轮未对其临床理由做正确性评审，也不能从缺少session单独断言所有线下交流绝无发生；现存已见链没有提供相应会话佐证，故维持交流真实性/业务充分性未验证。

### 与公开代码的对应

- ReviewService允许unsigned p2p_review并创建请求；原MD case decision已存在时拒绝直接amend。返回case_decision快照是在回填p2p_request_id前构造，持久记录随后才有关联ID；即时返回不等于最终回读值。
- DeterminationService先检查P2P request是否completed，再按合法outcome解析来源。uphold映射deny，overturn映射approve，同时更新解析视图的original_recommendation；原MD持久行无需变成deny或改签核。这是公开服务实际行为，不是本项目新增规则。
- pending P2P先阻断preflight，override不能越过；已finalizable来源与最终决定不一致时才需要override及reason。两次历史没有使用override。
- P2PService.record_p2p_outcome文案描述event_open→completed，方法实际只拒绝already completed；合成requested以及event_open均能记录结果，历史scheduled亦成功。它不校验“讨论已举行”note是否有会话来源；服务接受note不证明其内容真实。
- session.finalized与request.completed是不同字段；finalization解析看request状态/outcome，不能仅凭其中一个字段或工具分别可调用判断整段业务已正确完成。

## 5. 候选、作者自测及主代理独立复验

新增19项自造synthetic病例/ID/原因测试，真实调用固定公开ReviewService、P2PService、DeterminationService。MemoryStore只替代存储接口，workflow初始化/artifact外部接口为最小替身，不复制来源解析逻辑，不打桩核心resolve/preflight。覆盖：缺失/五种未完成request含override仍阻断、两个合法完成outcome、缺失/非法outcome和状态拒绝、unsigned deny拒绝、p2p unsigned接受、拒绝amend、override元数据、session/request区别、record_outcome重复拒绝及较早状态实际可完成。

**合成验证到真实finalization preflight，未执行合成最终持久化finalize。** 历史实际finalize成功由旧请求/响应和导出证明，不冒充本轮新世界完整服务执行。

作者初轮`c5-initial.log`14 failed：错误假设即时case_decision返回已填P2P ID，修为区分返回快照与持久回读。`c5-revised-1.log`14 passed、2 warnings（夹具赋字符串到枚举），最终用真实枚举消除warning，`c5-final.log` **19 passed**，无skip/warning。失败和旧日志保留，不求和。

主代理从固定main archive+唯一新测试文件建立候选快照，SHA-256 `e5c1c1302d6a178c364b54da883cc2f2c03aa14ccf8b18b1600ff46b61d5ad22`，读完差异、公开调用代码及测试夹具后独立执行：

| 独立检查 | 实际结果 | 忽略证据目录中的日志 |
| --- | --- | --- |
| C5新测试+受影响工具/运行SDK回归 | **56 passed、3 subtests passed，无skip** | evidence/independent-regression.log |
| 自有来源回放脚本 | 两份目标export均由真实_resolve_source_state解析为deny，匹配原最终决定；将内存副本改scheduled则阻断，原导出不变 | evidence/source-replay.log |
| 原证据完整性及指纹关联 | 564文件+2导出不变，130 wire/25参数/399重放hash匹配 | evidence/final-integrity.log、trace-integrity.log |
| 基线/候选两种导出包重建 | manifest分别相同，未变运行包 | evidence/build-baseline.log、build-candidate.log |

主代理失败记录也保留：早期投影仅有缺正文的tool envelope，不能用其得出结果；补还原时一次SyntaxError留在trace-projection-syntax-failure.log，固定完整脚本后成功。指纹脚本初用ensure_ascii=false与原journal规范不同，trace-integrity-encoding-failure.log保留；改用原ensure_ascii=true后25参数全部匹配。均未修改原数据或候选来让审查变绿。

本地全部审查脚本、快照、失败/最终日志及包保存在`runs/c5-p2p-20261103/independent/`，作者日志在selftest/；受限vendor、原捕获目录、临床轨迹或Key不上传GitHub。

### Docker环境和命令

所有执行在禁网Docker/Python3.12，源码/vendor/原证据只读，tmpfs临时目录、独立输出可写；容器不挂Docker socket、auth或world。镜像`chi-agent-a-control:latest` digest `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Python3.12.15/Linux arm64；复用原只读model/pdf卷及固定vendor，无安装/下载/升级。

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v /private/tmp/c5-work/candidate/chi-agent:/workspace:ro \
  -v /private/tmp/c5-work/evidence:/workspace/runs:rw \
  -v /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/vendor/chi-bench:/workspace/vendor/chi-bench:ro \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -w /workspace --entrypoint /bin/sh chi-agent-a-control:latest -c \
  '/opt/venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  tests/test_c5_p2p_public_contract.py tests/test_go_chi_mcp.py \
  tests/test_go_chi_tools.py tests/test_go_chi_runtime.py tests/test_go_chi_recovery_sdk.py'
```

来源回放使用`audit/source_replay.py`、PYTHONPATH包含固定vendor/src，仅挂两份选定export文件与只读审查输出；无原世界进程。原账审查脚本、哈希清单及选定投影保留在同一忽略目录，重现时不应扩大挂载为真实账根可写。

Go包39文件manifest `e3585b651d443c98ef7e46d17f69ef43617a318456fa9abe2825dac637df9674`；旧evaluation包14文件manifest `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`。基线与候选分别重建相同；不因为测试位于包外就省略比较，也不把旧B收据升级为C3以后已有新B。

## 6. 未决项及后续边界

C5关闭的是“实际调用链是否核对”的工作，未关闭临床/交流事实充分性问题。原21/22、md.signed_off=false、费用及C1未知保持；没有官方内容评分、真实模型改进、新B/业务C或Harbor验证。

已见模型把缺少会话支持的交流陈述写入outcome note，是后续可独立设计的来源约束议题。应先冻结“交互型完成声明须关联什么可观察来源、缺失时如何报告未完成/未知”的契约，再做通用机制；本包不一刀切禁止公开manual outcome工具、不强制所有P2P改签核、不注入隐藏期望或预设deny/approve路径。

下一已规划功能包为输入自动摘要，须单独冻结schema、保护字段、用途/额度、同账与失败/真实兼容条件后离线实施；当前输入计量不等于自动压缩已实现。M4安全cause schema及累计审核另按既有分工接续，不接管DeepSeek M2。真实验证仍须先补C1处置/授权来源，再提供明确候选、用途、次数和停止条件。PR供用户最终审核合并，主代理不merge/auto-merge。
