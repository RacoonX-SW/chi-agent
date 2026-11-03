# 可靠性边界工具交付（M1/M3/M2）

日期：2026-11-02。基线：`origin/main` `fc7d678`（PR38 后）。PR39 `codex/reliability-refactor-plan` `04cf1a8` 在本次工作时**仍为 open**（`git ls-remote refs/pull/39/*` 有 head，但 `origin/main` 未前移），因此本分支从 `origin/main` 建立，不包含 PR39 的文档改动，也不续写任何已合并分支。

本包只做包外工具、只读分析与测试；未改 guard/journal/contract/runtime/context，未实现续写、未动账、未跑真实模型。

## M1 模块/调用/发布边界地图

交付：`docs/module-map.md` + 只读工具 `scripts/import_inventory.py`。

- 60 个自有模块逐个登记：分类（runtime/guard/capability/tools/build/devop/devsim/legacy）、是否进包、行数、用途、直接导入者。
- 三个边界分开写明：内层 `PACKAGE_FILES`（31 个 .py）、外层 release（`package/` + 3 个文件）、供应检查。
- 边界穿越事实：包内→包外只有 `model_runner_adapter` 函数内导入 `run_baseline`；包外→包内为正常复用；`live_development`/`b_provider_transport`/`model_runner_adapter` 仍被调用，**未整体判废**。
- 未移动目录、未改 allowlist。

## M3 包依赖与配置/契约检查

交付：`scripts/import_inventory.py` + `tests/test_import_inventory.py` + `tests/test_config_limits_consistency.py`。

- 导入清单区分 self/stdlib/third_party（按 4 个 `requirements*.lock`）/vendor（`chi_bench`）/unlocked_external/unknown，并单列函数内导入与动态导入（`__import__`、`import_module`）。
- 隔离包检查：只复制 `PACKAGE_FILES` 到临时目录后运行清单，能发现缺失模块。
- 当前真实结果：

```
modules=60 packaged=31
GAP model_runner_adapter -> run_baseline
UNLOCKED a_environment: docker, huggingface_hub
UNLOCKED go_chi_operator: docker.types
UNLOCKED role_operator: docker.types
```

`docker` 与 `huggingface_hub` 不在任何 lock 中，仅存在于 controller 镜像/下载环境；登记为环境漂移风险，未修。

- 配置/上限一致性：不打桩 `_identity`，直接比较 profile ↔ `CONFIG`；guard 必须接受配置值、拒绝 ±1/bool/字符串/None 且**不派发**；journal 记录的 `max_tokens` 必须与配置一致；改动任一数值/字段/多出字段必须被 `_same` 判否。
- 未新增依赖。

## M2 资源 manifest 生成

交付：`scripts/make_role_manifest.py` + `tests/test_make_role_manifest.py`。

- 显式 schema：family→role 映射；public 仅 instruction/tool_reference/request PDF；`task.toml`、`fixtures/manifest.json`、`fixtures/expectations.json`、world 一律 `world_only`；CM 使用共享 world + 共享 tool_reference。
- 拒绝：符号链接、路径越界、缺文件、多余文件、PDF 数量不符、未知 family/task、无 revision、输出已存在。
- 确定性：同一输入产生相同字节；写入用临时文件 + `O_EXCL`/`os.replace`，先跑**原** `role_resource_preflight.validate` 再落盘；预检失败不留文件。
- 真实数据核对：t027 生成的 11 项与现有手工 manifest 语义一致（仅列表顺序不同）；CM `cm_afib` 生成 6 项并通过 preflight。

## 检查命令与结果（Docker，Python 3.12）

```
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

- 全量：**509 tests**，2 个既有环境错误（缺 `anthropic`），11 skipped；无新增失败。
- 定向：`tests.test_import_inventory` 7 OK；`tests.test_make_role_manifest` 11 OK；`tests.test_config_limits_consistency` 4 OK。
- 身份：用 `go_chi_bundle.build_bundle` 重建，manifest `7206012ac6715c5c8dc803dffd2108db23245afd1db65a63fca9906a0671f19d`，与 release-v7 内层包一致 → 本包**未改变 runtime 身份**（仍需在合并后按实际 manifest 复核）。

## 复审修复（Gemini 阻断项）

- `import_inventory._module_imports` 原先只遍历模块顶层 `FunctionDef`，**漏掉类方法内的 import**；修复为递归遍历，类体透明、方法仍算函数上下文，嵌套函数单独归名。
- 影响：`go_chi_mcp` 方法内导入的 `referral_field_guidance`、`patient_identity_binding` 之前未被登记为调用者；`docs/module-map.md` 已按新结果重生成（60 个模块，新增 `import_inventory`/`make_role_manifest` 两个包外工具）。
- 新增测试：类方法 import、嵌套函数 import、相对导入不计 unknown。
- 非阻断建议一并处理：模块表注明 58+2 口径；相对导入归为 `relative`，不再落入 unknown。
- 复跑：定向 `tests.test_import_inventory` 9 OK；全量 **509 tests**，2 个既有环境错误、11 skipped。

## Codex 复审 R1/R2 修复（2026-11-02）

### R1：provider 主 world 选错

`build_manifest` 原先对 provider/payer 都用 `PA_WORLDS[0]`（payer world），合法 provider 任务会被原 preflight 判 `world_invalid`。

修复：新增 `PRIMARY_WORLD`，按 role 选主 world（provider→provider、payer→payer、cm→cm），两个 PA world 仍完整进入 `files`；主 world 必须出现在文件清单中，否则拒绝。原 preflight 未改、未放宽。

验证：

- 合成 provider 正常路径：主 world = `healthverse-pa-v2-provider.json`，7 项，原 preflight 通过；
- payer 正常路径：主 world = payer，11 项，通过；
- CM 正常路径：主 world = curated25，6 项，通过；
- 反例：provider 任务的 fixture world_id 写成 payer → 原 preflight `world_invalid`，且不落盘；
- 真实数据：`pa_t032` provider 任务生成 7 项、主 world 为 provider，通过原 preflight。

### R2：最终落盘非原子不可覆盖

`write_manifest` 原先是 `exists()` 检查后 `os.replace`，竞争创建的最终文件会被覆盖。

修复：临时文件写入并通过 preflight 后，用 `os.link(temp, output)` 原子提交；目标已存在（常规文件或符号链接）时内核返回 `EEXIST`，映射为 `manifest_output_exists`，原字节不变；成功后删除临时文件并 fsync 目录；其他 `OSError` 映射为 `manifest_write_failed`。

验证：

- 竞争创建：preflight 回调期间由另一写入者创建目标 → 拒绝，目标字节保持 `created-by-another-writer`，无 `.manifest-*` 残留；
- 已存在文件：拒绝且字节不变；
- 已存在符号链接：拒绝，链接与目标均不变；
- 预检失败：不产生最终文件，临时文件清理；
- `os.link` 抛 `OSError`：`manifest_write_failed`，无输出、无临时文件。

### 复跑

- 24 项原定向集扩为 **30 tests**（9 + 17 + 4），全部 OK；
- 全量：**515 tests**，2 个既有环境错误（缺 `anthropic`）、11 skipped，无新增失败；
- 未改 runtime/guard/journal/contract，未跑真实模型或 B/C。

## 失败与限制

- `model_runner_adapter -> run_baseline` 闭包缺口**保留未修**，交 C3；`test_real_tree_reports_known_run_baseline_gap` 显式断言该现状，修复后需同步更新。
- `docker`/`huggingface_hub` 未锁：只标记，不新增 lock 或安装。
- M4（诊断 cause）未做，等 Codex 冻结 schema。
- 未做 Input 压缩、Output 续写、pending 处置、账根/模型/目录变更、journal 拆分。
- PR39 未合并，本分支未包含其 §15 文档；合并后如文档冲突，只需取并集，不涉及代码。

## M5 文档/状态一致性（2026-11-03）

- `REVIEW_STATE.md` 同步：M1–M3 随 PR41 合并、输入摘要随 PR46 合并且默认关闭、M4 仍待 schema、M5–M6 候选待复审；`origin/main` 更新为 `4ac9c0c`，当前分支改为 `deepseek/m5-m6-closeout`。
- `tasks.md`：M1/M2/M3（PR41）与 M5/M6（本 PR）勾选；M4 保持未实施。
- `input-context.md`：把“概念流程（尚未实现）”改为“S0–S3 已实现并默认关闭”，链到输入摘要报告；F4 旧结论与历史失败未改写。
- 分支约定：`AGENTS.md`、`COLLABORATION.md`、`docs/github-workflow.md` 由固定 `codex/<任务名>` 改为 `<实现方>/<任务名>`（DeepSeek 用 `deepseek/`，历史 `codex/` 分支保留、不追溯重命名）。
- README 增加包外只读汇总的用法、输出字段与退出码。
- 未把已合并写成独立验收通过；C1 unknown、C5 交流佐证、M4 等仍保留。

## M6 包外只读 run 摘要（2026-11-03）

新增 `scripts/go_chi_run_summary.py`，**不进入** `PACKAGE_FILES`/release allowlist。

调用链：显式 `--root/--identity/--accounting-sha256` → 既有 `inspect_history`（严格身份/hash/证据校验，`execution_allowed=false`）→ 同一 `_state_object` 解析已校验账本 → 只投影白名单字段（run/task/role/status/error、请求 round/purpose/status/max_tokens、已知 token、三项 USD 与来源、pending/halted/missing、reconciled/acknowledged/input_summaries）。

- 不遍历 runs/账户目录；`--run` 不存在时返回 `summary_run_missing`，不静默选择“最新成功”。
- 按 purpose 分组（main/confirmation/patient_simulator/summary/continuation），主共享与患者辅助分列。
- 缺费用保持 `null` 且 `complete=false`；未结算请求 token 为 `null`，`unknown_tokens` 单独计数，不补零。
- 错误码与退出码：0 成功；1 `chi_inspect_invalid`/`chi_history_invalid`/`chi_inspect_hash_mismatch`/`summary_root_invalid`/`summary_run_missing`/`summary_billing_invalid`/`summary_lock_unavailable`，JSON 写 stderr；2 参数错误。
- 只读：不 reserve/settle/ack/rebind/reconcile；`inspect_history` 只读打开 `.lock`；测试比较读取前后文件集合与 SHA256 完全一致。

测试 `tests/test_go_chi_run_summary.py`（8 项）：完整运行稳定性与只读、pending/unknown 不记零、已知 token 但费用缺失且 halted、main+patient 分组、错误身份/hash/坏 JSON、无效 run 选择、CLI 退出码与 stdout/stderr、旧账缺少新字段仍可汇总。

## M5/M6 检查记录

Docker `chi-agent-dev:latest`，Python 3.12：

```
python -m unittest tests.test_go_chi_run_summary        # 8 tests OK
python -m unittest discover -s tests                    # 539 tests, 2 个既有 anthropic 错误, 11 skipped
```

- 包身份：分别从 `origin/main` 快照与当前候选构建内层 bundle，manifest 相同（工具不在 allowlist）；详见下节实际值。
- 未跑真实模型/摘要/续写/B/C/world；未改 runtime/guard/journal/contract；未处理 pending 或账根。

### 限制

- `summary`/`continuation` 用途只做分组与字段透传，未合成新历史；其真实端点与收益仍未验证。
- 患者辅助请求在测试中用 `cm_outreach.send_message` 的 started 事件合成，未启动 broker。
- 旧账/新账的语义差异由既有 `inspect_history` 判定，本工具不重算身份或修复旧文件。

## M4 安全诊断 cause（2026-11-03）

按 PR48 `safe-diagnostics.md` D0–D3 实现。对外安全码、整批零派发、可信 usage 先结算、未知阻断和持久化失败停止均未改变。

### 实现

- 新增纯模块 `scripts/go_chi_diagnostics.py`（仅标准库）：`chi-safe-cause-v1` 白名单（9 stage）、`chi-go-diagnostic-v2` 精确五字段校验、v1 原规则校验、固定 code→cause 映射；cause JSON ≤256 字节，未知字段/枚举/类型拒绝。
- `go_chi_contract.ToolContract.accept_batch`：在原拒绝点区分 9 种批错误（`assistant_shape`、`unfinished_batch`、`call_shape`、`call_id_invalid`、`call_id_reused`、`function_shape`、`tool_unknown`、`arguments_json`、`arguments_schema`），`ContractFailure` 增加受控 `cause`；接受集合与“整批提交前验证、失败不落盘”不变。
- `go_chi_guard`：保留 `chi_tool_batch_invalid` 顶层码；请求路径区分 `route/body/history/budget/time`，响应/usage/transport/persistence 走固定映射；每次请求重置 `safe_cause`；成功写 `ok`+`cause=null`。
- `go_chi_auxiliary` 使用同一 v2 写入与传输/响应/usage cause。
- `go_chi_journal`：`record_diagnostic(code, elapsed, *, cause=None)` 写 v2；`ok` 带 cause、非法对象、缺字段均 `chi_diagnostic_invalid`，不静默替换；恢复点接受 v1/v2 的 `ok`。
- 读取接点：`_validate` 接受 v1/v2；`_recovery_source`、`go_chi_summary` 安装/回放接受 v2；`inspect_history` 仅在历史含 v2 时增加 `diagnostic_causes`（run/round/code/cause）。
- `go_chi_runtime` 的 run_log 新增 `safe_cause`（guard 捕获的主失败，否则 null）；顶层 `safe_error_code` 不变。
- 包接线：`go_chi_diagnostics.py` 进入 `PACKAGE_FILES` 与 entry preflight 模块清单；evaluation 包未变。

### 验证

Docker `chi-agent-dev:latest`，Python 3.12，禁网、无 Key、无 world：

```
python -m unittest tests.test_go_chi_diagnostics tests.test_go_chi_diagnostic_causes   # 14 tests OK
python -m unittest discover -s tests                                                  # 553 tests, 2 个既有 anthropic 错误, 11 skipped
```

覆盖：9 类批错误与一好一坏整批零提交、恶意参数/患者值/Key 文本不进 cause、可信 usage 先 settle 后拒绝且 lower 仅一次、工具零派发、reserve 前拒绝不造请求行、cause 额外字段/未知枚举/错类型/bool/超长/`ok` 带 cause 拒绝、v1 旧格式接受、inspect 输出 v2 causes。

- **旧账兼容（实物）**：对 `runs/real-external/state-v7` 执行只读汇总，v1 历史正常读取且不新增 `diagnostic_causes`；整个目录读取前后 SHA256 集合不变。
- **包身份**：Go 内层 bundle 由 `d99a49f0…` 变为 **`8cb711fe77eb7a346fe71f64a005a52e979f97643de3e13aff12e461f01c9f0b`**，runtime identity **`b4741cce241291d68c6c2761c12f892da95f9057487b06e8bb68dd7faafd202a`**；旧 evaluation 包仍为 `a6a69d7d…`。
- **隔离包**：仅挂载 `package/` 与固定依赖，无 Key preflight `identity_verified`；在包内用 MockTransport 跑坏工具批，得到 `chi_tool_batch_invalid` + `tool_unknown`，请求先 settled。

### 限制

- 未用 v1 合成夹具单独跑 `_validate` 的单元路径；v1 兼容由真实旧账只读读取证明。
- 未同时启用 summary 与 output recovery 的真实 SDK length 组合；两者共用同一 v2 校验，分别由既有回归覆盖。
- 未跑真实模型/B/C/Trial/判分；新身份需新 B 才能用于真实运行。
