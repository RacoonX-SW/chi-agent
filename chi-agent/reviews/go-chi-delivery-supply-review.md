# Z1 正式配送供应与离线准入：实现与证据

更新：2026-11-01。本报告只记录 Z1 离线供应检查；真实 Harbor Trial、真实模型和官方任务仍未运行。状态/权限见 [REVIEW_STATE](REVIEW_STATE.md)。

## 1. 身份与现场

| 项目 | 值 |
| --- | --- |
| 基线 | `4ade699`（本轮核对到的 `origin/main`） |
| 实现候选 | `a9965e57fb78a5de7ce1f3cd9230014d8b2cc2c9` |
| 分支 | `codex/z1-delivery-supply`（未推送/未开 PR） |
| 环境 | Docker `chi-agent-dev:latest`，Python 3.12.15 |

**现场说明**：用户表示已合并 F7，但本轮多次 fetch 后 `origin/main` 仍为 `4ade699`；PR35 有 head `ec577a9`、merge ref `d29c608`，但 main 未前进。Z1 不依赖 F7，因此从实际 main 建分支。F7 合并后需把本分支 rebase/merge 并重跑全量。

## 2. 实现

- `go_chi_delivery.py`：
  - `chi-go-delivery-plan-v1`：role、bundle root/SHA、model/PDF 依赖、vendor root/commit、公开 instruction/handbook/tool refs、MCP URL/role、state/logs、history、凭据名。
  - 严格字段/绝对路径/`..`/隐藏段；bundle `validate_bundle()` + SHA；依赖/vendor 目录；资源普通文件/非链接；MCP 角色端口；logs 必须新、state 父目录存在；local history `q_root/chi-evaluation`；external 禁止 q_root。
  - 凭据只允许 `OPENCODE_API_KEY`，其他已知 provider/judge 凭据列入 forbidden；plan 不含值。
  - `check_plan()` 只读、无网络、不读 Key；CLI `check --plan --plan-sha256`。
- `GoChiHarness.install()`：
  - 明确为**无网络 no-op**；包/依赖/vendor 由调用方预供应；`run()` 的无 Key preflight 是实际闸门。
  - 新增测试断言 install 不访问 environment。
- 未改 vendor、评分器、账目 schema、官方世界或既有 B/历史。

## 3. 实际命令与结果

定向：

```bash
cd chi-agent
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -e PYTHONPATH=/workspace/scripts -e PYTHONDONTWRITEBYTECODE=1 \
  -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest tests.test_go_chi_delivery tests.test_go_chi_harness -v
```

结果：`Ran 16 tests ... OK`。

全量：

```bash
docker run --rm --network none -v "$PWD:/workspace:rw" \
  -v chi-h-root-model-deps-20261027-v1:/model-deps:ro \
  -v chi-k-pdf-deps-20261027-v1:/pdf-deps:ro \
  -e PYTHONPATH=/model-deps:/pdf-deps:/workspace/vendor/chi-bench/src:/workspace/scripts \
  -e PYTHONDONTWRITEBYTECODE=1 -w /workspace chi-agent-dev:latest \
  /opt/venv/bin/python -m unittest discover -s tests
```

结果：`Ran 446 tests`，`FAILED (errors=2, skipped=8)`；2 个错误仍是既有环境缺 `anthropic`。当前 main 未含 F7，所以数量比 F7 分支的 451 少 5；F7 合并后需重跑。

## 4. 覆盖的失败路径

- 缺 bundle / 错 bundle SHA / 缺 model 或 PDF 依赖 / 缺 vendor 源码。
- 错角色或 MCP 端口/路径。
- instruction 符号链接、fixture 路径；handbook/tool ref 缺失。
- logs 已存在；state 父目录缺失/链接。
- local history 的 `q_root` 不存在或 `output_root` 不匹配；external 带 `q_root`。
- 凭据名不是 `OPENCODE_API_KEY`，或 forbidden 集合不完整。
- CLI plan SHA 不匹配。
- `install()` 不访问 environment、不联网。

## 5. 未验证项

- 真实 Harbor 工厂/Trial、world 镜像供应、`install()` 在真实 Harbor 生命周期中的调用顺序。
- 真实依赖版本/锁 hash（当前只检查目录存在，未逐包校验）。
- 真实 state/log 持久化、清理、超时/取消后的 owned 资源。
- 真实模型 Key 注入路径与官方模拟器/judge 凭据隔离。
- 真实任务、业务终态、临床正确性、官方分数。
- 外部 Gemini 尚未复审；PR 尚未创建。
- F7 合并后的 rebase/重跑。

## 6. 下一步

1. 外部 Gemini 审查供应契约、install no-op 决策、依赖/vendor 检查粒度和凭据隔离。
2. 按意见返工后创建 PR。
3. F7 合并后 rebase/重跑；随后进入 Z4/Z6 真实 Trial 准备，仍需用户批准任务/次数/资源。

## 7. 外部 Gemini 复审结论（2026-11-01）

- **结论**：通过（LGTM），具备创建 PR 条件。
- **审查对象**：Z1 候选 `a9965e5` / 文档 HEAD `0ce593f`；复审方未另附命令日志，本条按用户转述记录。
- **逐项结论**：
  - 供应契约：责任划分清晰，覆盖 bundle、依赖、vendor、资源、MCP、状态与凭据。
  - 静态检查器：离线纯只读，路径防逃逸严格，bundle 逐文件哈希核验充分。
  - Harness 闸门：`install()` 无网络 no-op 契约成立，执行前无 Key 预检完好。
- **边界**：仅离线静态/契约与 Docker 合成；未运行真实 Harbor Trial、真实模型或官方判分。
- **合并建议**：当前分支基于 `4ade699`，未包含 F7；应先合并 PR35，再把本分支 rebase 到最新 main，重跑全量（预计 461 tests）后才合并。
