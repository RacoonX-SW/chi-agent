# Z6 离线发布包与干净环境校验：实现与证据

更新：2026-11-01。本报告只记录 release wrapper/verify；真实干净环境、Harbor Trial、真实模型和官方任务未运行。状态/权限见 [REVIEW_STATE](REVIEW_STATE.md)。

## 1. 身份

| 项目 | 值 |
| --- | --- |
| 基线 | `6e7643c`（F7/PR35 合并后的 main） |
| 实现候选 | `ccdf8f26ce79e0b3c423dc899664b60d08f577a2` |
| 分支 | `codex/z6-release-package`（未推送/未开 PR） |
| 环境 | Docker `chi-agent-dev:latest`，Python 3.12.15 |

## 2. 实现

- `go_chi_release.py`：
  - `build`：创建 release、调用现有 `go_chi_bundle.build_bundle(package/)`、写 `release-manifest.json`、`SHA256SUMS`、`supply-plan.example.json`；失败删除本次 target；已有 target 拒绝。
  - `verify`：顶层/包内 allowlist、符号链接/禁止内容、source commit、bundle manifest/entry config/file hashes、依赖锁、SHA256SUMS、可选 `go_chi_delivery.check_plan()`。
  - 确定性：不写时间戳/宿主路径/凭据；相同源码+commit 的 manifest/SHA256SUMS 相同。
  - 不联网、不读 Key、不启动模型/世界/Trial。

## 3. 实际命令与结果

定向：

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -e PYTHONPATH=/workspace/scripts -e PYTHONDONTWRITEBYTECODE=1 \
  -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest tests.test_go_chi_release -v
```

结果：`Ran 5 tests ... OK`。

全量：

```bash
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

结果：`Ran 466 tests`，`FAILED (errors=2, skipped=8)`；2 个错误仍是既有环境缺 `anthropic`，无新增回归。

过程中的真实失败已修正：

1. `build_bundle(target/package)` 要求父目录存在；首版未先创建 release target，导致 `bundle_target_invalid`；改为先 `target.mkdir()`，失败仍删除本次 target。
2. bundle 篡改时可能先触发 `BundleFailure` 而不是 release checksum code；verify 显式映射为 `release_bundle_identity_invalid`，测试覆盖。

## 4. 覆盖的失败路径

- 目标已存在、source commit 缺失/非法。
- 顶层额外/缺失条目、符号链接、禁止目录。
- 包内额外文件、manifest 缺失/字段错误。
- bundle hash/文件集合不一致、依赖锁 hash 不一致、SHA256SUMS 篡改。
- 可选 plan 与 release/package 不匹配。
- CLI build/verify 退出码。

## 5. 未验证项

- 真实干净依赖安装（空卷）、空状态目录、真实 world/公开输入/MCP。
- 真实模型、日志/trajectory/context、状态回收、owned 资源清理。
- 分发 allowlist 的最终人工检查；release 不是签名，不能证明来源可信。
- 外部 Gemini 尚未复审；PR 尚未创建。
- 真实 Z6 启动/Harbor Trial 未运行；不能把离线 verify 写成真实复现通过。

## 6. 下一步

1. 外部 Gemini 审查 release allowlist、确定性、checksum/plan 耦合和回滚边界。
2. 返工后创建 PR。
3. 合并后准备真实 Z6/Z4 干净环境与 Trial 的审批包；真实运行需用户一次性确认任务/候选/资源/次数。

## 7. 外部 Gemini 复审结论（2026-11-01）

- **结论**：通过（LGTM），建议创建 base=main 的 PR 交用户最终合并。
- **审查对象**：Z6 候选 `ccdf8f2` / 文档 HEAD `89a1344`；复审方未另附命令日志，本条按用户转述记录。
- **逐项结论**：
  - 发布包布局与白名单：通过；顶层与包内双层封闭白名单。
  - 确定性构建：通过；规范序列化与相对路径排序，构建结果逐字节可复现。
  - 防篡改核验：通过；SHA256 全覆盖结合内层 Bundle 校验。
- **边界**：仅离线发布包/合成构建；未运行真实干净依赖安装、Harbor Trial、真实模型或官方判分。SHA/checksum 不是签名，不证明来源可信或执行许可。
- **后续**：创建 base=main 的 PR 由用户合并；真实 Z6/Z4 仍需空依赖安装、world/MCP、模型、日志/清理和用户批准。
