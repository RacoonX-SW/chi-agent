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

## 失败与限制

- `model_runner_adapter -> run_baseline` 闭包缺口**保留未修**，交 C3；`test_real_tree_reports_known_run_baseline_gap` 显式断言该现状，修复后需同步更新。
- `docker`/`huggingface_hub` 未锁：只标记，不新增 lock 或安装。
- M4（诊断 cause）未做，等 Codex 冻结 schema。
- 未做 Input 压缩、Output 续写、pending 处置、账根/模型/目录变更、journal 拆分。
- PR39 未合并，本分支未包含其 §15 文档；合并后如文档冲突，只需取并集，不涉及代码。
