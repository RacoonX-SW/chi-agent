# chi-requirements-v1 阶段报告：公开要求清单、来源校验与 claim 门禁

日期：2026-11-06（Asia/Shanghai）。分支：`deepseek/requirement-completion-gate`，基线 `origin/main=8154148`（PR64 已合并），实现提交 `85b89664e8db245adc5ddaa9840962a3c929a1e5`。**本报告是离线实现/自测记录，不是独立复审，也不授权真实模型、B/C、摘要、续写、患者、world、Trial、judge 或发布。**

## 1. 范围与结论

- 新增 opt-in `chi-requirements-v1`；默认关闭，关闭时 state/completion 仍走 v3，工具 schema/description、guidance 内容/digest 保持旧路径，不增加 claim 检查。
- 开启时 task state `chi-task-state-v4`、completion `chi-completion-v4`；模型可显式记录最多 8 项公开 instruction 要求，为 done/waived 附本 run 观察来源；未声明、空清单、open 项阻止 claim。
- 程序只验证引文、来源、状态转换和声明项闭合；**不证明抽取覆盖全部要求，不证明观察语义上完成业务，不证明临床正确或官方得分**。
- 未执行任何真实模型/B/C/摘要/续写/患者/world/Trial/judge；未读取凭据或完整 `.env`；未修改旧 state/账本/运行证据；未 push/PR/merge。

## 2. 实际改动

| 文件 | 改动 |
| --- | --- |
| `scripts/go_chi_state.py` | v4 按实例 schema；instruction 绑定/SHA；requirements 快照、quote 逐字子串/归一化长度、append/open/终态/回退规则；done/waived 来源与 scope；共享 `_completion` 门禁；v4 completion/summary；四个 `chi_state_requirement_*` 码 |
| `scripts/go_chi_tools.py` | 仅开启时 `local-state-update` 增加 requirements schema/description；claim/completion 描述补门禁；guidance 透传 requirements |
| `scripts/go_chi_guidance.py` | off 保持 v3/原 digest；on 使用 `chi-role-guidance-v4` 并增加角色中立公开要求自检 invariant |
| `scripts/go_chi_runtime.py` | `requirements` 参数→TaskState/local_tools；未知版本/缺 instruction/与 summary/recovery/Y shadow 组合早拒；run_log `requirements_policy`、v4 guidance/completion |
| `scripts/go_chi_entry.py` | `--requirements`；launch 记录；早期互斥拒绝；run-log reader 支持 completion-v4、新 reason、requirements_policy、guidance-v4；拒绝非法嵌套 |
| `scripts/go_chi_journal.py` | `_requirements_enabled`；launch 策略版本/互斥校验；历史 v3 兼容 |
| `scripts/go_chi_readiness_inventory.py` | completion-v4、requirements 对象、计数/hash/open_ids 严格校验 |
| `scripts/role_operator.py` | config `requirements` 精确版本/互斥；`_validation_flags` 透传 |
| `scripts/role_runner.py` | `--requirements` 纳入 Y shadow 互斥 argv 检测 |
| `tests/test_go_chi_requirements.py` | 新增 27 个测试：结构/引文/边界、快照/事务/回退、来源/scope、claim/report 门禁、entry/inventory/run-log、off 回归、三角色合成接线、no-claim final |
| `tests/test_role_operator_config.py` | requirements 精确版本/互斥/flag 测试 |
| `openspec/changes/requirement-completion-gate/` | design、tasks、specs 验收场景 |

## 3. Docker 测试结果

镜像：`chi-agent-dev:latest`（Python 3.12）；controller 另用 `chi-agent-py312-review:controller`。命令均在 `/workspace` 下、禁网、只读脚本/依赖卷。

| 检查 | 结果 |
| --- | --- |
| 新功能测试 `tests.test_go_chi_requirements` | **27 passed**，exit 0 |
| 相关回归（state/tools/guidance/entry/runtime/journal/inventory/role_operator/c4/requirements） | **112 passed, 6 skipped**，exit 0 |
| controller `tests.test_role_operator_config` | **6 passed**，exit 0（含 requirements 配置） |
| 全量 `unittest discover -s tests` | **653 tests, 18 skipped, 3 errors**，exit 1 |

全量 3 个错误均为既有环境/收集问题，单列而不排除：

- `test_dev_patient_adapter`：`ModuleNotFoundError: anthropic`
- `test_dev_patient_network`：`ModuleNotFoundError: anthropic`
- `test_role_payer_projection`：`ModuleNotFoundError: docker.types`

新测试不依赖真实 world/模型；`test_three_role_requirements_claim` 与 `test_no_claim_final_keeps_open_requirements` 使用禁网 `httpx.MockTransport` + 合成 MCP/本地工具，覆盖 provider/payer/CM 正例和 no-claim final。未把上述 3 个错误写成“全绿”。

## 4. 新 bundle/release 身份

从实现提交重建 release，源树含 requirements 代码；不改旧冻结包。

| 项目 | 值 |
| --- | --- |
| source commit | `85b89664e8db245adc5ddaa9840962a3c929a1e5` |
| bundle manifest SHA-256 | `7bb65f3ded5459c8c4d9dda009a0430d032ef8ff14346d474da345ee4ee84de4` |
| release manifest SHA-256 | `5eecb2850eefcc00055fd41ae615dbd1e4beb191332b91cafaf523249958d059` |
| runtime identity | `6e95480af61615d0492d58cc3d05320eb82077c8d5d8e829652d1548be3b3147` |
| 隔离 verify | `status=valid`，43 files，exit 0 |
| 隔离无 Key 禁网 preflight | `status=identity_verified`，runtime 匹配，upstream clean，exit 0 |

**新身份意味着旧 B 收据不适用**；本包没有创建新 state/B，也没有进入当前九题候选。默认关闭不表示包内 hash 不变。

## 5. 失败、未验证项与边界

- **没有增加专门抽取模型请求**；不承诺 main 轮次、token 或耗时不增加。
- **没有真实模型/业务收益/误拦率/额外 token/轮次/静态 guidance 对照**；这些需九题证据固定后另行设计并获批。
- **程序不证明**：抽取覆盖全部 instruction 要求；观察在语义上完成业务；done/waived 是临床正确或官方得分。
- **默认关闭**且不进入当前九题候选；使用隔离分支/导出/测试资源，不覆盖当前运行包。
- 旧 v1/v2/v3 证据保持原义；旧 state/账本/请求/收据未修改。
- 未执行已见题回归或任何真实调用。
- 本分支的 `vendor/chi-bench` 与 `data/skills/managed-care-operations-handbook` 是本地测试资源（未提交），用于 Docker 测试/release 构建；不随提交上传。
- 全量 3 个既有 import/收集错误保留，不能据此宣称全量通过。

## 6. 独立复审重点

1. v4 requirements 快照的前缀/终态/回退校验是否覆盖删除、重排、改 quote、终态改写；整份更新是否原子。
2. quote 是否严格逐字子串；归一化只用于长度/查重，不替代来源校验。
3. done/waived 来源是否拒绝 cross-run/歧义/非 returned/neutral/错误 scope；case 锁定复验与 claim/report 复验是否一致。
4. `_completion` 顺序：claim_violation → open unknown → unresolved file → requirements → business readback；是否被 requirements 绕过。
5. off 路径是否逐字段保持 v3：state/completion、工具 schema/description、guidance 内容/digest、无 requirements claim 检查；v3/v4 同进程隔离。
6. entry→launch→runtime→state→run_log 是否真实到达；未知版本/缺 instruction/summary/recovery/Y shadow 组合是否在凭据/派发前拒绝；argv 分离/等号/缩写是否覆盖。
7. completion-v4/run-log reader/inventory 是否严格校验计数、bool、hash、open_ids、嵌套键；畸形 v4 是否明确 fallback 且不掩盖首个错误。

## 7. 交付状态

- 实现与契约已在本地提交 `85b89664…`；本报告随后本地提交。
- **未 push、未开 PR、未 merge**；固定候选后交独立审核及用户决定。
- 不恢复任何真实执行权限；旧 1800s/九题 pending 和旧候选不在本分支处理。

## 8. Gemini 独立复审（2026-11-06）

复审者：Gemini，按独立复审 Prompt 在禁网 Docker 环境实测。

| 项目 | 结果 |
| --- | --- |
| 结论 | **Pass / LGTM，0 Blocker** |
| 身份 | 分支 `deepseek/requirement-completion-gate`；基线 `8154148`；实现 `85b89664…`；报告 `5b9a3fc…`；工作区 clean |
| bundle / runtime | `7bb65f3d…` / `6e95480a…`，与实现者记录一致 |
| 定向需求测试 | `tests.test_go_chi_requirements`：27 tests，1.313s，OK，exit 0 |
| 相关回归 | 11 模块 112 tests，2.037s，OK（6 skipped），exit 0 |
| controller 配置 | `tests.test_role_operator_config`：6 tests，0.004s，OK，exit 0 |
| 全量 | 653 tests，15.976s，errors=3，skipped=18，exit 1；3 个均为既有环境缺失（`anthropic` ×2、`docker.types` ×1），无新增回归 |
| 契约 A–E | 全部通过；off 路径字段保真、quote 逐字/归一化两阶段、快照/终态/事务、done/waived 来源、scope、门禁顺序、互斥早拒、v4 reader 均核对 |
| 建议 | 准予合并；用户最终验收/合并，未启用 auto-merge |

复审边界：离线/合成证据，不证明真实模型收益、语义完成、临床正确或官方得分；不改变默认关闭和旧 B 收据不适用的事实。

## 9. 交付状态（更新）

- 实现与报告已在本地提交 `85b89664…` / `5b9a3fc…`。
- 已按用户要求准备最终 PR；**不自行 merge、不启用 auto-merge**。
- 用户最终验收合并后，本分支才进入主线；合并不自动启用 requirements，也不恢复真实执行权限。
