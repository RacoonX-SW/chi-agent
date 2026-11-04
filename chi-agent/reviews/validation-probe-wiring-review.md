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
3. **entry→journal.launch**：用**临时复制的真实 state**（含绑定 `c9b1571d…` 的 B 收据）在禁网无 Key 容器内运行包内 live 入口：
   - `--input-summary`：attempt 写入后 `launch.input_summary="chi-input-summary-v1"`，`requests=0`、`pending=null`，因 `chi_credential_missing` 停止（未读 Key、未发请求）；
   - `--output-recovery`：`launch.output_recovery="chi-output-recovery-v1"`，同样零请求、无 pending。
   - 原 state 只读复制，真实 `runs/validation-live-20261104/state` 未改。
4. **guard 采用**：沿用既有真实 SDK+MockTransport 的 `tests/test_go_chi_summary_*` 与 `tests/test_go_chi_recovery_*`，证明 launch 字段进入 guard/runtime 路径；本包未改这些算法。
5. **shadow 互斥**：`role_runner.reject_shadow_with_validation_flags()` 仅在 runner 环境可观察 shadow；operator 当前不转发该变量，因此经 operator 无法开启 shadow，但直接 runner 调用会被拒绝。未新增 Y 启用入口或 schema 字段。

## 3. Docker 检查

Python 3.12，禁网、无 Key、无 world：

```
# 适用 pytest（排除两个缺 anthropic 的收集模块）
pytest tests --ignore=tests/test_dev_patient_adapter.py --ignore=tests/test_dev_patient_network.py -q
# 889 passed, 13 skipped, 261 subtests passed

# controller 镜像：operator 配置/schema
unittest tests.test_role_operator_config -v
# 5 tests OK

# 新增接线测试
unittest tests.test_role_validation_wiring -v
# 4 tests OK
```

失败/skip：11 个既有 skip（Harbor overlay、旧 Docker/controller 依赖）+ 本包 2 个 controller-only 用例在 dev 镜像 skip，均在预期；2 个 `anthropic` 收集错误保持。

## 4. 包身份

- 只改包外 operator/runner/测试/文档：Go 内层 bundle 仍为 `de326a26e20c6b6b29ea11c50805d2679143f7bc3eb62ad4035f4a56cf8a30bb`；隔离导出包无 Key 禁网 preflight 仍返回 runtime identity `c9b1571d217e8ad4a58b80123db6643ba228850ed0399e47a70fff22509ab559`。
- 旧 evaluation 包 `a6a69d7d…` 未变。
- 未重建 release 包；若重建，release manifest 仅因 `source_commit` 变化而不同，内包 identity 不变，不能混称包身份变化。既有 B 收据仍绑定 `c9b1571d…`。

## 5. 探针草稿（未授权执行）

| 草稿 | SHA-256 | 开关 | run/attempt |
| --- | --- | --- | --- |
| `runs/validation-live-20261104/probe-summary-draft.json` | `ddccaba793174a07994c6434b0774321090c1c30708833f5f4811b450ce9bfed` | `input_summary=chi-input-summary-v1` | `vprep-s-001` / `summary-probe-1` |
| `runs/validation-live-20261104/probe-recovery-draft.json` | `abfb32b4a20595ba442bd67d6982c4d15bae15d4623b99b90bb66e383162768f` | `output_recovery=chi-output-recovery-v1` | `vprep-r-001` / `recovery-probe-1` |

共用：evaluation `eval-vprep-20261104`、state `runs/validation-live-20261104/state`、payer `pa_t030_t030_o002_p01_triage_payer`、bundle `de326a26…`、runtime `c9b1571d…`、t030 manifest `6518225…`、runner/world 镜像 `b22f7c66…`/`000ca509…`（arm64 已确认存在）。

离线核对：两配置均通过 `role_operator._config`、原 `role_resource_preflight`、dev hash 与 bundle/state 路径检查，输出目录尚不存在；未创建 journal、未占 attempt、未读凭据、未启动 world。**文件是草案，不构成执行授权。**

## 6. 限制与未验证

- 未跑完整 operator→容器→world→entry 链路；入口侧用真实 state 副本验证 launch 字段，B 门禁未被绕过，无新 B。
- 两项探针的真实端点兼容、触发/未触发、取消/未知、费用/额度仍未验证；本轮零模型请求。
- shadow 只在 runner 接缝拒绝；operator 不转发该 env，组合无法经 operator 开启，但未做容器级验证。
- operator/controller 的未锁依赖（docker SDK 等）保持既有风险，未重构。
