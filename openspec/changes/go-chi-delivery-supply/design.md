# Z1 配送供应契约（待外部 Gemini 审查）

状态：离线实现候选 `a9965e5`，基线 `4ade699`。本页冻结 caller-owned 供应与检查接口。

## 1. 供应责任

| 内容 | 供应方 | 检查点 |
| --- | --- | --- |
| 导出包（`go_chi_bundle.py` 产物） | 调用方/操作者 | `bundle-manifest.json` + SHA-256 |
| 固定 model 依赖 | 调用方（卷/镜像） | `<model_root>/agents` |
| 固定 PDF 依赖 | 调用方（卷/镜像） | `<pdf_root>/pypdf` |
| 官方 vendor checkout | 调用方 | `<vendor_root>/src/chi_bench` + 固定 commit 字符串 |
| 公开 instruction/tool_reference/handbook | 调用方/官方任务 | 普通文件/目录、无链接、无隐藏材料 |
| 角色 MCP URL | 官方 world/调用方 | 单角色、端口 8020/8100/8200、路径 `/mcp` |
| 可写 state/logs | 调用方 | state 父目录存在；logs 尚不存在 |
| 模型 Key | 运行时注入 | 只允许 `OPENCODE_API_KEY`；其他已知 provider 凭据禁止 |
| 官方模拟器/judge 凭据 | 官方环境 | 不进入 runner；delivery plan 不含值 |

`GoChiHarness.install()` **不联网、不安装**：包/依赖/vendor 已由调用方放入 world；`run()` 先执行 `go_chi_entry.py preflight`，失败后才不读取/注入模型 Key。caller-owned 是明确决策，不是“no-op 已具备自动安装”。

## 2. `chi-go-delivery-plan-v1`

```json
{
  "schema": "chi-go-delivery-plan-v1",
  "role": "provider",
  "bundle": {"root": "/package", "sha256": "<64 hex>"},
  "dependencies": {"model_root": "/model-deps", "pdf_root": "/pdf-deps"},
  "vendor": {"root": "/vendor/chi-bench", "commit": "<40 hex>"},
  "resources": {
    "instruction": "/input/instruction.md",
    "handbook_root": "/workspace/skills/managed-care-operations-handbook",
    "tool_references": ["/input/tool_reference.md"]
  },
  "mcp": {"url": "http://official-world:8020/mcp", "role": "provider"},
  "state": {"output_root": "/state", "logs_dir": "/runner-logs/task"},
  "history": {"mode": "external", "q_root": null},
  "credentials": {
    "model_env": "OPENCODE_API_KEY",
    "forbidden_env": ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "DEEPSEEK_API_KEY",
                      "GEMINI_API_KEY", "GROK_API_KEY", "OPENAI_API_KEY",
                      "OPENROUTER_API_KEY", "XAI_API_KEY"]
  }
}
```

规则：

- 未知字段、缺失字段、非绝对路径、`..`、隐藏路径段拒绝。
- bundle root 必须是目录；`validate_bundle()` 通过且 manifest SHA 与计划一致。
- model/pdf 依赖目录必须存在；vendor 必须有 `src/chi_bench`，commit 为 40 位 hex。
- instruction/tool refs 必须是普通文件、非链接、非 fixture/verifier/judge/hidden/expectations/solution；handbook 必须是目录。
- role 与 MCP role 一致，URL 端口按角色固定，路径必须是 `/mcp`，不允许 userinfo/query/fragment。
- `logs_dir` 必须尚不存在；`output_root` 父目录必须存在；`output_root` 不能是链接。
- history=local：`q_root` 必须存在，`output_root` 必须等于 `q_root/chi-evaluation`；history=external：`q_root` 必须为 null。
- 凭据只允许 `model_env=OPENCODE_API_KEY`，`forbidden_env` 必须恰好是已知其他 provider 凭据集合；plan 只存名字，不存值。
- `plan_digest()` 对规范化 JSON 计算 SHA-256；CLI 可要求 `--plan-sha256` 匹配。

## 3. 检查与失败

`check_plan()` 只读、无网络、不读 Key，返回：

```json
{
  "schema": "chi-go-delivery-check-v1",
  "status": "valid",
  "plan_sha256": "...",
  "role": "provider",
  "bundle_manifest_sha256": "...",
  "checks": ["bundle", "dependencies", "vendor", "instruction", "handbook",
             "tool_references", "mcp", "state", "history", "credentials"],
  "network_install": false,
  "credential_names": ["OPENCODE_API_KEY"],
  "note": "caller supplies package/deps/vendor/resources/MCP/state; runner receives only the model key"
}
```

| 失败 | 代码 |
| --- | --- |
| plan 结构/角色/schema | `delivery_plan_invalid` |
| bundle 目录缺失 | `delivery_bundle_missing` |
| bundle manifest/哈希不匹配 | `delivery_bundle_identity_invalid` |
| model/pdf 依赖缺失 | `delivery_dependencies_missing` |
| vendor 源码缺失 | `delivery_vendor_missing` |
| instruction/tool ref 链接/隐藏/缺失 | `delivery_instruction_invalid` / `delivery_tool_reference_invalid` |
| handbook 缺失/隐藏 | `delivery_handbook_invalid` |
| MCP 角色/端口/路径 | `delivery_mcp_invalid` |
| logs 已存在 | `delivery_logs_exist` |
| state 父目录/链接 | `delivery_state_invalid` |
| history 模式/q_root 不匹配 | `delivery_history_invalid` |
| 凭据名不合规 | `delivery_credentials_invalid` |
| plan SHA 不匹配 | `delivery_plan_sha256_mismatch` |

## 4. 与 Harness 的关系

- `install()` 保持 no-op；测试断言它不访问 environment、不联网。
- `run()` 继续在读取 Key 前执行 no-key preflight；delivery check 是调用方/操作者的额外闸门，不能替代 run 内预检。
- 真实 Harbor 工厂/Trial 仍在 Z4/Z6；本变更只证明 caller-owned 供应检查、缺件失败和凭据分离。

## 5. 待外部 Gemini 审查

1. `install()` no-op + caller-owned 供应是否满足“不能把 no-op 当安装能力”？是否还需要在 install 里写 supply 摘要？
2. plan 的 bundle/deps/vendor 检查是否足够？是否需要校验依赖版本/锁 hash，而不只是目录存在？
3. `logs_dir` 必须不存在、`output_root` 可存在，是否适合所有 evaluation 模式？
4. local history 强制 `output_root=qroot/chi-evaluation` 是否过严/是否覆盖外部独立 evaluation？
5. 凭据白名单是否遗漏其他 provider 凭据？plan 只存名字是否足够防泄漏？
6. instruction/tool refs 的 hidden 段过滤是否会误伤合法路径？
7. 真实 Trial 的 install/run 顺序、world 镜像供应和 state/log 持久化还需要哪些证据？
