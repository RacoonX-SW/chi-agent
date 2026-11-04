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
