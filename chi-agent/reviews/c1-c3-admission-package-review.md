# C1只读准入核查与C3包依赖闭合：实施及独立审核

日期：2026-11-02（Asia/Shanghai）。本报告集中保存本阶段证据，短状态只在[REVIEW_STATE](REVIEW_STATE.md)。

## 1. 范围、候选与结论

用户确认合并C2后要求继续下一步开发。本轮从已核实合并的[PR42](https://github.com/xsw932187210-cell/chi-agent/pull/42)及最新`origin/main` `5e8418ef5e1d92f1e437b927c05392a740e3d314`新建`codex/c1-c3-admission-package`。原目录`codex/reliability-boundaries`及DeepSeek工作不动；不续写已合并分支，不merge main，不自动合并。

- **C1完成只读事实核查，未清账、未开放真实准入**：确认`payer-010`原账仍pending时，后继运行使用了不同state及evaluation。原未合并报告“无换账根”的文字与文件事实不符；现有选定证据不足以闭合未知处置与特定后继授权，不能仅凭新root内部完整认定准入获准，也不据此断言用户从未作过其他授权。
- **C3最小依赖修复在限定离线范围通过独立审核**：隔离包实际调用旧适配器预算函数可复现`ModuleNotFoundError: run_baseline`。原函数提取为标准库纯模块，两个发布包补齐依赖及身份绑定；保留旧入口重导出、函数行为、拒绝理由、签名和注解。当前Go主循环不走这条旧预算路径，没有证据证明真实Go曾因此崩溃。
- C1没有修改准入程序或引入全局账户登记器；C3不改任何额度、费用、重试、长度恢复或journal策略。不处理C4/C5、自动摘要、M2及旧pending。**Key读取0，真实模型/摘要/续写/B/C/Trial/判分请求0，无新world。**

分工：主代理规格、只读核查、独立复验、教学与Git；原唯一实现子代理`gpt-6.1-terra/high`（最初派发`fork_turns=none`）只实现及Docker自测。实现停止后主代理固定快照审核，作者自测不算独立验收。

实现提交`3434f8e`；最后EOF清理候选 **`ae47067584c7e6761f9bf844dd938da3a1b46bc5`**。后续报告/状态提交不改变包成员。固定快照与完整本地审查脚本、日志保存在忽略目录`runs/c1-c3-20261102/`，原始轨迹、配置、受限vendor和凭据均不上传。

## 2. C1来源、方法与证据边界

来源为未合并提交`0ca0d45`的[批次报告第14节](https://github.com/xsw932187210-cell/chi-agent/blob/0ca0d45/chi-agent/reviews/real-external-batch-a-review.md)、同提交审批草案及原目录`runs/real-external`下相关state/config。旧报告不改写。

主代理在禁网Python3.12容器只读挂载五个指定state及选定配置；用固定main源码的`inspect_history`读取，不构造可写journal，不调用reconcile/acknowledge，不挂载auth目录、`go.env`或world。先后比较每个文件的集合、字节数与SHA-256，**1458个文件保持不变**：

| root | 文件数 | chi-accounting.json SHA-256 |
| --- | ---: | --- |
| state-v6 | 181 | `1b9c50bc5d7529a835e84333e72f43e7a41511d425eb935dd53d64e9648b1968` |
| state-abl-off | 512 | `74f7c1aa368cc5920ed2505e7f3420161931018b25d5614c95c6e342f7809563` |
| state-abl-on | 201 | `1736968b236330627f5530b1866f6f6b3e842a95857ebb5f754d191e77f678ef` |
| state-abl-on2 | 380 | `7440d13ecd3675fd1f584d11c76d6a4058c842cc2ede173d00df8d0ba6006fc9` |
| state-v7 | 184 | `6e1db43361d2cf664b3ae9a1b923c31c512b028571ab3303630a56d3563f3b93` |

五个历史检查均返回`inspected`、`execution_allowed=false`。这是只读reader的返回语义，不能当成一次真实准入判定，更不能解释成所有root都已结算。

本地证据：`audit/c1_inventory.py`、`audit/c1_metadata.py`；`independent/c1-inventory.json/.log`、`c1-config-timeline.json`、`c1-metadata.log`及五份`state-*-file-hashes.json`。只输出核查所需元数据，文件不进入Git。

## 3. payer-010及后继的事实链

共同任务为`pa_t030_t030_o002_p01_triage_payer`，均为`attempt-2`，运行时身份`55b55cd73f73f82443b173f1d4e4be4d4e80315bda61e86ecc2e7be1ac497cb1`，release-v6 bundle `7206012ac6715c5c8dc803dffd2108db23245afd1db65a63fca9906a0671f19d`，能力`f0-f3-v1`、external模式。

| 事件 | 原root / evaluation | 观察 |
| --- | --- | --- |
| payer-010 | state-abl-on / eval-abl-on | 2026-11-02 00:52:48.277首请求派发元数据；164ms后chi_transport_error；请求reserved=1、status=pending，无response文件；run失败而root pending仍指向run/round1 |
| B009 | state-abl-on2 / eval-abl-on2 | 01:03:20.837起，3请求已结算；新root不是旧账的结算证据 |
| payer-012 | state-abl-on2 / eval-abl-on2 | 01:04:00.926起，同任务/attempt，47请求均结算 |
| payer-013 | state-abl-on2 / eval-abl-on2 | 01:16:32.340起，t027 attempt-3，30请求均结算；不在本轮分析业务正确性 |

时间由`dispatch.started_utc_ms`转换为Asia/Shanghai；不是服务端接收确认。旧请求body 70694 bytes，request SHA `2fa28297a8d01af62f89a6604ac2d1b8b8a32dc19e6dee171bad61f125030b0e`；request证据文件SHA `27e2d50635103bc7a560ec1cc0d0085865c9f0661deb830b2a12f5b82c92521d`；diagnostic SHA `aa5f6d1d7e1ef175ce2a02714a2259258d942d2b13998f7ba424c8de5034f180`；seal SHA `3e8f7a4e0dc04e6f50960d56dce994259014004fb0d3b1e433a8e1539f1f28e1`。payer-010/012 instruction SHA同为`8abfcba1eac2de06fae0959f78e09a20132708af297835cadc12214a6bf2d723`。

配置`tri-on.json` SHA `20424dc9063c8ba9e1af50fdb1efa403fd4493a2668897cf822dc44868a4ba0a`，`tri-on2.json` SHA `e34d75f6585ea756a098c5e7466ddab5b47664c8d13dc829cb205be35cc5b6ca`；后者明确改用`state-abl-on2`及`eval-abl-on2`。两个root均没有acknowledgements、reconciliations、source_transitions关联此转换；新root pending=null不改变旧root pending。

`state-abl-on`已知小计输入7614740、输出44186，list USD 1.07178269、allowance USD 0.64306962、charged USD 0；因payer-010未知，完整性均为false，以上不是完整消费或余额。`state-abl-on2`内部已知小计输入14559771、输出83142，list USD 2.13476578、allowance USD 1.28085947、charged USD 0；它自身完整，但跨前史仍unknown，不能核销旧请求或把旧未知费用填0。

旁证：state-v6为B006/payer004已知结算；state-abl-off为B007/payer005/007/008/009，payer005为已知length失败而非未知；state-v7的B010/payer014使用另一个`40a2e975…`身份。均保留其历史语义，不冒充本轮新候选已实跑。

### 解释、缺口与后续条件

原报告据短时Console窗口无匹配session推断“未到服务端”，这不足以排除请求在途或服务端计费。所选材料没有Console原始导出或明确针对payer-010 unknown及eval-abl-on2切换的用户决定。原审批草案一般性允许既定任务的新attempt，不能直接证明本次未知处置/新账根已获准；此结论仅限本轮所选来源，不能断言其他对话中绝无授权。

`role_operator`按选中`state_relative`进入本root的journal准入；它不是跨root的提供方账户注册表。新root内部通过检查，不等于同一账户前史已核清，也不等于具备独立evaluation授权。**可确认发生了root/evaluation切换，无法从当前证据确认其授权和未知处置已经闭合。** 本轮不删除pending、不伪造settled、不重发payer-010、不选择第三个root绕过阻断。

如后续要真实验证，需先补齐提供方可核对的单请求结算证据，或保留原未知的明确处置决定及后继evaluation授权关联；再冻结具体候选、包、用途、次数、停止条件并单独获准。本报告本身不授予真实B/C准入。

## 4. C3最小修复与独立审查

基线包仅挂导出物及SDK，实际调用`model_runner_adapter._budget_check()`，复现`ModuleNotFoundError(name='run_baseline')`（`independent/c3-baseline.log`）。只做顶层import会漏过函数内导入；此处是潜在依赖缺陷，Go主循环当前采用其他guard/journal路径。

修改为`budget_evaluation.evaluate_budget`：原函数体AST不变、标准库`decimal`依赖、无IO。`run_baseline`保留原符号重导出。Go及旧evaluation的PACKAGE_FILES均加入新模块，`opencode_go_provider.source_identity`、`b_live_preflight`、`evaluation_entry`、`live_development`的显式源码身份列表同步加入，防止打包成功却遗漏身份绑定。不把run_baseline及其d0_gate依赖放入发布包。

独立审查曾抓到纯模块缺少`from __future__ import annotations`，导致注解/签名元数据不同；交回Terra修复并补回归。之后仅去除模块与fixture尾部多余空行、更新fixture SHA；最终主代理再次对固定main原函数做AST、结果/理由、签名/注解比较，并重建两种包及真实身份。

正常链：`_budget_check`校验ledger/请求 → 同一纯预算函数预留并判定 → 原成功返回。失败链：usage_unknown/accounting_state_invalid、轮数/费用不足、非法输出上限、过长中文输入、错误model保持原安全错误；测试均断言transport_calls=0。没有改变真实模型、思考强度、单次/共享50次上限或length恢复默认关闭状态。

## 5. Docker环境与固定身份

所有执行禁网、只读源码/包，tmpfs临时目录，只有独立输出目录可写，无凭据挂载；无安装/升级。镜像`chi-agent-a-control:latest` digest `sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，Linux arm64/Python3.12.15。

依赖复用只读`chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`；实际Agents0.13.6、OpenAI2.36.0、httpx0.28.1、httpcore1.0.9、mcp1.30.0、jsonschema4.26.0、pydantic2.14.1/core2.50.1。身份检查挂载固定clean vendor `4444a07fa68a4f1623f841a292a54e284fc8e7f7`；严格预算路径检查**不挂源码或vendor**。

| 最终项 | SHA-256/数量 |
| --- | --- |
| 固定candidate-3.tar | `23620f0710e566018b7297287a5276feb605c5fb6d56a9348833892e61c06b71` |
| budget_evaluation.py | `93e1072e71188a11c7300688c001489bc9469c1e7e4719beb807b8b0a46118aa` |
| 自有原函数fixture | `c8339dc92c9244955ddcb16c7de5772d5d23a5fe033d69b3624a066f64d010fd` |
| Go bundle | 39文件；manifest `e3585b651d443c98ef7e46d17f69ef43617a318456fa9abe2825dac637df9674` |
| 旧evaluation bundle | 14文件；manifest `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc` |
| Go真实runtime identity | `035e3e65d351c40443d5f1b3c2c41c24eb45240efb277b0f54127b587540ee60` |

旧evaluation真实`_runtime_identity()`返回`verified_for_offline_integration`，新模块hash绑定匹配。以上都是离线包身份，**没有新B收据或真实Go验证**；旧B/旧基线不迁移为新身份已验证。

## 6. 自测、独立复验及失败保留

### 作者自测（不能替代独立验收）

`selftest/c3-final.log`：234 passed、105 subtests；`c3-go-regression.log`：60 passed、12 subtests（存在重叠，不求和）；注解返工`c3-annotations-rework.log`及EOF返工`c3-eof-rework.log`各3 passed。README dry-run exit0。作者后续补做两种strict隔离包检查，旧包hash因返工已过时，以本报告主代理最终包为准。

保留作者`c3-initial.log`（不存在的测试名，零执行）、`c3-targeted-1.log`（vendor挂载路径不符，88 failed/199 passed/51 subtests）、`c3-targeted-2.log`（缺少可写runs挂载，4 failed/229 passed/105 subtests）。早期隔离挂载包含源码快照，不能当作最终严格隔离证据；最终检查已去除。

### 主代理独立证据

| 固定对象/检查 | 结果 | 本地日志 |
| --- | --- | --- |
| 基线Go实际旧函数路径 | 复现缺少run_baseline | independent/c3-baseline.log |
| candidate-2原函数等价性 | 3 passed、160 subtests | independent/independent/independent-equivalence.log |
| candidate-2受影响链回归 | **501 passed、8 skipped、158 subtests** | independent/independent/affected-regression.log |
| 最终candidate-3 EOF返工及原函数独立复核 | **6 passed、160 subtests** | independent/final/eof-independent.log |
| 最终Go严格包实际成功/安全拒绝 | **2 passed、12 subtests** | independent/final/package-go.log |
| 最终旧evaluation严格包实际成功/安全拒绝 | **2 passed、12 subtests** | independent/final/package-evaluation.log |
| 最终两包重建/校验、Go及旧evaluation真实身份 | exit0；见第5节 | independent/final/package-build.log、identity-*.log |
| 静态闭包 | closure_gaps=[]、unknown_imports=[]、Go Python模块33 | independent/independent/import-closure.log |

501项回归是注解返工后、EOF清理前的固定candidate-2，tar SHA `0c9bd47c65396a55c76d00e9e4dffa50893c3117dc02e340777c9975688683d9`。candidate-3与其代码差异仅两处EOF空行及fixture校验值，主代理逐差异确认并跑受影响的最终6项、重建两包及真实身份，不把501项伪称为在最终字节上全量重跑。测试/subtests及重叠检查不相加。

8 skips为5项Harbor controller overlay、3项controller Docker SDK；没有把skip当通过。未锁`docker`/`huggingface_hub`风险保持，非C3范围。主代理首次回归缺少只读父目录内runs挂载点，容器初始化exit125、零测试（affected-regression-mount-failure.log）；创建空挂载点后同一代码通过。最后复核有两次Docker socket权限失败（未启动容器）及身份检查vendor挂至错误相对路径失败，均在`final/*failure*`保留；改成`/package/vendor/chi-bench:ro`后通过，不改生产检查绕过身份。

### 可复现命令

本地证据路径中的`candidate-3/chi-agent`是只读源码快照；`audit/`为主代理检查脚本。所有命令均执行在同一Python3.12镜像，不用宿主Python。主受影响回归：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/scripts:/workspace/vendor/chi-bench/src \
  -v /private/tmp/c1-c3-work/candidate-2/chi-agent:/workspace:ro \
  -v /private/tmp/c1-c3-work/independent/runs:/workspace/runs:rw \
  -v /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/vendor/chi-bench:/workspace/vendor/chi-bench:ro \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -w /workspace --entrypoint /bin/sh chi-agent-a-control:latest -c \
  '/opt/venv/bin/python -m pytest -q -rs -p no:cacheprovider \
  tests/test_go_chi_*.py tests/test_c3_budget_closure.py tests/test_import_inventory.py \
  tests/test_model_runner_adapter.py tests/test_readiness_and_baseline.py \
  tests/test_b_provider_preflight.py tests/test_evaluation_entry.py \
  tests/test_opencode_go_provider.py tests/test_live_development.py'
```

最终严格Go包路径（旧evaluation仅替换package-go为package-evaluation）：

```sh
docker run --rm --pull=never --network none --read-only --tmpfs /tmp \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/model-deps:/pdf-deps:/package/scripts \
  -v /private/tmp/c1-c3-work/final/package-go:/package:ro \
  -v /private/tmp/c1-c3-audit:/audit:ro \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  --entrypoint /opt/venv/bin/python chi-agent-a-control:latest \
  -m pytest -q -p no:cacheprovider /audit/c3_package_independent.py
```

身份检查是在上述包基础上只读增加固定vendor相对挂载，运行`audit/c3_final_identity.py`，不打桩核心`_identity`或`_runtime_identity`。C1审查脚本及日志保留实际选择的state、配置、前后hash与时间线；从未重跑旧任务。

## 7. 未验证与下一步

本阶段通过只表示最小闭包/兼容性及只读事实核查通过；未知结算/授权缺口不因此消失。没有真实端点、新B、业务C、患者调用、Harbor Trial、判分、干净联网安装或账户全量审计；原payer业务false与official_reward=null保留。C2输入计量不等于输入摘要已实现。

用户审核本PR后，后续离线可单独冻结C4用途参数一致性或C5公开P2P实际调用链核查；不得把本PR合并视作自动授权真实模型。需要真实探针时先完成离线候选，再提交明确次数/用途/停止条件。C2已集中讲解正常与失败调用链，学习记录不升级为用户已掌握，也不默认小测。
