# 包外操作者：输入摘要/输出恢复开关接线（离线）

日期：2026-11-04。基线 `origin/main` `1f5c580`（PR53 已合并）；分支 `deepseek/validation-probe-wiring`。**只完成包外接线与离线验证；两项探针仍未授权，未创建真实 journal/world/请求。**

## 1. 范围与改动

| 文件 | 改动 |
| --- | --- |
| `scripts/role_operator.py` | 配置新增可选 `input_summary`/`output_recovery`：只接受 `chi-input-summary-v1`/`chi-output-recovery-v1`，类型/版本/空串/null/布尔/数字/列表拒绝；两者互斥；`_validation_flags()` 生成一次 CLI 参数并附加到 runner 命令 |
| `scripts/role_runner.py` | 新增 `reject_shadow_with_validation_flags()`：当 `CHI_DEV_EVIDENCE_SHADOW=shadow` 且 argv 含任一开关时，在调用包内 entry 前抛 `evidence_shadow_exclusive` |
| 测试 | `tests/test_role_operator_config.py` 新增默认/合法/非法/互斥/argv 用例；`tests/test_role_validation_wiring.py` 覆盖 runner→entry 转发身份、entry parser 两开关、shadow 接缝 |

未改：包内 `go_chi_entry`/runtime/guard/journal/摘要/恢复算法、`go_chi_harness`、profile、`PACKAGE_FILES`、模型/端点/thinking/额度/输出/context/时间。

## 2. 实际调用链与证据

1. **配置→argv**：`_config()` 拒绝非法组合；`_validation_flags()` 返回 `["--input-summary","chi-input-summary-v1"]` 或 `["--output-recovery","chi-output-recovery-v1"]`，缺省 `[]`。`main()` 将其拼接到 runner 命令尾部一次。
2. **runner→entry**：`role_runner.main` 就是包内 `go_chi_entry.main`（测试断言对象同一）；argv 原样转发。
3. **entry→journal.launch**：用返工后重建的真实包（`de326a26…`）与**临时复制的真实 state**（含绑定 `c9b1571d…` 的 B 收据）在禁网无 Key 容器内运行包内 live 入口：
   - `--input-summary`：attempt 写入后 `launch.input_summary="chi-input-summary-v1"`，`requests=0`、`pending=null`，因 `chi_credential_missing` 停止（未读 Key、未发请求）；
   - `--output-recovery`：`launch.output_recovery="chi-output-recovery-v1"`，同样零请求、无 pending。
   - 原 state 只读复制，真实 `runs/validation-live-20261104/state` 未改。
4. **guard 采用**：沿用既有真实 SDK+MockTransport 的 `tests/test_go_chi_summary_*` 与 `tests/test_go_chi_recovery_*`，证明 launch 字段进入 guard/runtime 路径；本包未改这些算法。
5. **shadow 互斥**：`role_runner.reject_shadow_with_validation_flags()` 仅在 runner 环境可观察 shadow；operator 当前不转发该变量，因此经 operator 无法开启 shadow，但直接 runner 调用会被拒绝。未新增 Y 启用入口或 schema 字段。

## 3. Docker 检查（返工后）

Python 3.12，禁网、无 Key、无 world：

```
# 适用 pytest（排除两个缺 anthropic 的收集模块）
pytest tests --ignore=tests/test_dev_patient_adapter.py --ignore=tests/test_dev_patient_network.py -q
# 892 passed, 13 skipped, 275 subtests passed

# controller 镜像：operator 配置 + 接线
unittest tests.test_role_operator_config tests.test_role_validation_wiring -v
# 12 tests OK（5 配置 + 7 接线）
```

失败/skip：11 个既有 skip（Harbor overlay、旧 Docker/controller 依赖）+ 本包 2 个 controller-only 用例在 dev 镜像 skip；2 个 `anthropic` 收集错误保持。保留失败与 skip，不称全量全绿。

## 4. 包身份（返工后实测）

6ffc6ca 初审发现 R1：分发 runbook `docs/go-chi-entry-runbook.md` 映射为包成员 `RUN_CHI_GO.md`，该提交新增的操作者说明改变了内包：

- 6ffc6ca 重建：bundle `0d2a1c844aee0683e710db64b19c4c9ef82f12ff2043c6e2ec7cff9dd9518edb`，runtime `f5700b54692e093e12ec08af0d4088ed063dcaf9f534eac740a0ede3f164ed76`（对旧 manifest preflight 失败）。
- 返工 `afb9dff` 恢复该 runbook 原字节（本任务说明只留在包外报告），从该提交重建：

| 对象 | 实际身份 |
| --- | --- |
| Go 内层成员 | 41 个；与冻结包逐成员 sha256 全部相同 |
| Go bundle | `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb` |
| runtime（隔离包无 Key 禁网 preflight） | `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559` |
| 旧 evaluation 包 | `a6a69d7d23ae5197eff00fadb198e2cf743f74aae600b65ae2f5e36e3085abfc`（未变） |
| 重建 release | `5d2d2d6f6785ba5f0a2a1caec9580e6411f65414df9a3b6400490658d8bf53bd`，source_commit `afb9dff85de9599196f89c7c81a1f6b1d9691eee` |

release wrapper 因 source_commit 变化产生新 hash；内包 manifest/runtime 与冻结候选一致。旧封存 release、候选清单与 B 证据未覆盖。

## 5. 探针草稿（未授权执行）

| 草稿 | SHA-256 | 开关 | run/attempt |
| --- | --- | --- | --- |
| `runs/validation-live-20261104/probe-summary-draft.json` | `8fe12ade59359c45a2cafb7d0ebc3f35b6b0318c74546af885002d9f646f0c29` | `input_summary=chi-input-summary-v1` | `vprep-s-001` / `summary-probe-1` |
| `runs/validation-live-20261104/probe-recovery-draft.json` | `27491401365c73ebcc6c1a98c55a3f805650f26befecf758827a581ce86c4c21` | `output_recovery=chi-output-recovery-v1` | `vprep-r-001` / `recovery-probe-1` |

共用：evaluation `eval-vprep-20261104`、state `runs/validation-live-20261104/state`、payer `pa_t030_t030_o002_p01_triage_payer`、bundle `de326a26…`、runtime `c9b1571d…`、t030 manifest `6518225…`、runner/world 镜像 `b22f7c66…`/`000ca509…`（arm64 已确认存在）。

离线核对：两配置均通过 `role_operator._config`、原 `role_resource_preflight`、dev hash 与 bundle/state 路径检查，输出目录尚不存在；未创建 journal、未占 attempt、未读凭据、未启动 world。**文件是草案，不构成执行授权。**

## 5.1 初审 R1/R2 返工（2026-11-04）

- **R1**：恢复 `docs/go-chi-entry-runbook.md` 到 base 字节（不改 `PACKAGE_FILES`/身份算法/profile/B 收据）；重建后 41 成员逐项相同、manifest/runtime 恢复。先前“内包不变”的写法已更正为“6ffc6ca 改变、返工恢复”，旧候选不写成通过。
- **R2**：`role_runner` 不再只比较完整 token，而是用包内 parser 的 option 表按 argparse 语义解析（精确、`=`、无歧义缩写），shadow 与任一能力组合在进入 entry 前拒绝；不修改包内 parser/runtime/guard。
- 新增回归：两能力 × 4 种合法写法均拒绝；实际 `role_runner.py` 子进程证明在 entry 前停止；无 shadow/无开关路径保持；`--input-s` 等等价形式经真实 parser 验证合法。
- Docker：适用 pytest **892 passed、13 skipped、275 subtests**；controller 配置/接线 **12 tests OK**。原 6ffc6ca 的 889/13/261 保留为历史结果，不预填为返工通过。

## 6. 限制与未验证

- 未跑完整 operator→容器→world→entry 链路；入口侧用真实 state 副本验证 launch 字段，B 门禁未被绕过，无新 B。
- 两项探针的真实端点兼容、触发/未触发、取消/未知、费用/额度仍未验证；本轮零模型请求。
- shadow 只在 runner 接缝拒绝；operator 不转发该 env，组合无法经 operator 开启，但未做容器级验证。
- operator/controller 的未锁依赖（docker SDK 等）保持既有风险，未重构。

## 7. GPT独立复审与交付记录（2026-11-04）

固定复审候选 **`9d36c54426131e97fdc6bf370c27a63e348288b4`**，生产实现 **`afb9dff85de9599196f89c7c81a1f6b1d9691eee`**，base=`1f5c580218aff88175f095e13a6bec8fa7a59ad8`。**R1/R2在本次限定离线范围关闭，未发现新增阻断，可push/开PR；用户最终验收/合并。** 原`6ffc6ca`初审失败及原`0a8449e`累计初审失败保留，不以新通过回写旧候选，也不扩大为真实端点或正式交付通过。

复审阶段严格只读；随后用户明确授权更新审核记录、push并创建base=main PR，保持零真实调用、不merge、不auto-merge。本次新增记录只改审核文档，生产/测试/profile字节与上述已审候选相同。没有派实现代理或要求Gemini重复审核。

### 独立环境、命令与证据

从上述三个固定Git提交分别`git archive`导出到仓库外，原工作区不作为可写测试目录。所有Python均在Docker/Python3.12、Linux arm64；`--pull=never --network none --read-only --tmpfs /tmp`，`PYTHONDONTWRITEBYTECODE=1`，无Key、`.env`或Docker socket挂载。固定vendor/SDK/PDF卷只读复用，实际环境与冻结身份一致，没有安装或升级依赖。

- dev镜像：`sha256:b22f7c664bf5da8994d7199f1482536b0b4ab36d0d522ae121c4a0562ed044b3`，`/opt/venv/bin/python`。
- controller镜像：`sha256:24bef2e2c7e30bb972667b29afd0ed80d6fb79ae735210b8e3167ee5013b0bf3`，`/opt/a-venv/bin/python`。
- 依赖卷：`chi-h-root-model-deps-20261027-v1`、`chi-k-pdf-deps-20261027-v1`。

独立原始证据集中 `/private/tmp/chi-review-9d36c54/`，`audit/`为复现脚本、`evidence/`为日志、`exports/`为新导出包；不上传这些原始产物。第一轮失败审查仍保留在 `/private/tmp/chi-review-6ffc6ca/`。

| 固定对象/检查 | GPT实际执行结果 | evidence文件 |
| --- | --- | --- |
| 最终9d36c54适用pytest | **892 passed、13 skipped、275 subtests**，18.00s、exit0 | `pytest.log` |
| controller配置/接线 | **12 tests OK**（5+7），exit0 | `controller-tests.log` |
| base/实现/文档候选各自新导出Go/evaluation/release | 三组Go 41成员与冻结包逐项相同；release验证通过 | `build.log` |
| 最终新Go导出包真实CLI preflight | `identity_verified`，manifest/runtime恢复冻结值 | `preflight.json` |
| 最终新evaluation包真实运行身份 | `_runtime_identity()`通过 | `identity-evaluation.json` |
| 自有argparse差分/实际runner子进程 | 36种合法前缀形式、重复/分隔边界；指定8种子进程均在entry前拒绝，3种非组合保留entry解析 | `argparse-repro.json` |
| 新包+返工runner的入口/B门禁反例 | 两项有B均止于缺凭据、零请求；无B均拒绝且无attempt；原15文件不变 | `entry-repro.log` |
| 两草稿SHA/dev hash/资源/原state核查 | 均匹配；原state仅一次B，无probe attempt，输出目录不存在 | `drafts.log` |

实际测试命令均在上述Docker限制中，源码只读、`/workspace/runs`仅绑定仓库外测试输出：

```text
python -m pytest tests --ignore=tests/test_dev_patient_adapter.py --ignore=tests/test_dev_patient_network.py -q -rs -p no:cacheprovider
python -m unittest tests.test_role_operator_config tests.test_role_validation_wiring -v
python /audit/build.py
python /package/scripts/go_chi_entry.py preflight --bundle-sha256 de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb
python /audit/identity.py（KIND=evaluation）
python /audit/argparse_repro.py
python /audit/entry_repro.py
python /audit/drafts.py
```

pytest明确忽略两个缺`anthropic`的收集模块，不称完整全绿。13个skip为5项Harbor overlay、3项旧Docker operator、5项role operator配置；后5项在controller独立执行。各组结果有重叠，不相加。

### R1独立关闭

base与最终候选的分发runbook Git blob均为`141095ade204a6eaa01c2ab2ca1721d03c70d2a6`。从base、`afb9dff`、`9d36c54`分别重建，三组41成员的hash/大小均与原冻结包相同；不是仅复查旧导出目录。Go manifest为`de326a26…`，最终新导出包真实CLI得到runtime `c9b1571d…`；旧evaluation manifest与实际运行身份不变。

独立重建的生产实现release manifest为`5d2d2d6f…`，source_commit=`afb9dff…`；与作者指定release的manifest及SHA256SUMS原始字节一致。三组wrapper JSON去掉source_commit后相同；若以文档候选`9d36c54`作source_commit，wrapper manifest为`427840b4c05b7c86f3e4d8347572a49c60b11fdf3cd0afa6d2b8000543affd10`。后者属于文档HEAD重建，不替代生产实现release记录。

原冻结候选清单、原封存release manifest及原B收据hash均未变；原B state的15文件与B阶段原始hash清单逐项相同。旧失败提交/审查报告保留，没有修改旧收据、身份算法或allowlist来消除差异，也没有重复真实B。

### R2独立关闭

自有脚本以包内真实`_parser()`的解析结果为基准，枚举两能力全部被接受的无歧义前缀及分离/等号形式，共36种合法形式；均正确识别并在shadow下拒绝。每种形式另检查重复参数、能力参数在`--`之前而mode在其后的合法边界；混合两能力也拒绝。普通参数通过等号绑定的“形似能力开关”的值没有被误判。

当前parser没有能力短选项别名；单横线伪选项、歧义`--output-r`、能力位于`--`后的非法额外参数均由真实parser拒绝，未发现当前合法语法绕过。指定8种形式均另以实际`role_runner.py`子进程验证：stdout为空、`evidence_shadow_exclusive`发生在包内entry parser之前，未打桩entry制造结果。无shadow、shadow=off、shadow无能力参数三种实际子进程保留entry原有参数解析行为。

本结论限当前固定parser和CLI接缝；实现仍自行扫描token，未来parser增加alias/nargs时需重新核查。建议保留这些差分边界测试，不要求为本次交付扩大重构。

### 入口证据、草稿及剩余边界

使用本次新Go包、实际返工runner及原B state的仓库外临时副本，无Key/禁网执行入口。两项合法开关均进入`journal.launch`后止于`chi_credential_missing`，requests=0、pending=null；无B负例均为`chi_b_receipt_missing`、attempts=[]。原state只读挂载，15文件与原始清单及审查前后均相同。**这只证明入口元数据及B门禁，不证明能力已经执行、端点兼容或账户前史已结清。**

两份草稿的实际SHA与第5节一致，dev_sha256对应当前包外脚本，资源manifest/角色/任务/选定冻结包匹配，输出目录尚未创建；所选真实state仍只有原一次B。它们没有产生真实journal/attempt/world/请求，仍须分别取得G0后继处置范围及具体config/hash/用途/次数的明确许可。

完整operator→容器→world链、真实摘要/恢复触发、取消/未知处理、摘要忠实度/净费用、官方Harbor/judge和controller未锁依赖仍未验证。本次独立复审及本轮文档/Git交付均为零真实模型/摘要/续写/B/C请求，无world/Trial/judge或发布；PR和合并均不自动恢复这些权限。
