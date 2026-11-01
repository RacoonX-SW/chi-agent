# Z6 发布包接口与行为冻结（待外部 Gemini 审查）

状态：离线实现候选 `ccdf8f2`，基线 `6e7643c`。

## 1. 布局

```text
<release>/
  package/                  # 现有 go_chi_bundle 产物（内含 bundle-manifest.json）
  release-manifest.json
  SHA256SUMS
  supply-plan.example.json  # 模板；实际 plan 由调用方填写后交给 delivery check
```

顶层只允许这四个条目；任何 `.env`、data、vendor、tests、runs、reviews、openspec、docs 目录或符号链接拒绝。

`package/` 内只允许 `go_chi_bundle.PACKAGE_FILES` + `bundle-manifest.json`；额外文件拒绝。

## 2. `release-manifest.json`

```json
{
  "schema": "chi-go-release-v1",
  "source_commit": "<40 hex>",
  "bundle_manifest_sha256": "<64 hex>",
  "bundle_entry_config_sha256": "<64 hex>",
  "bundle_files": {"<relative>": "<64 hex>"},
  "dependency_locks": {"model": "<64 hex>", "pdf": "<64 hex>"},
  "allowed_top_level": ["SHA256SUMS", "package", "release-manifest.json", "supply-plan.example.json"],
  "notes": ["..."]
}
```

- `source_commit` 由调用方显式给出，或在源码 checkout 中用 `git rev-parse HEAD` 取得；缺失/非 40 hex 拒绝。
- `bundle_files` 与内层 `validate_bundle()` 的文件 hash 完全一致。
- `dependency_locks` 取包内 `requirements-model.lock` / `requirements-pdf.lock` 的 SHA-256。
- 不写入时间戳、宿主路径或凭据；相同输入应产生相同 manifest 和 SHA256SUMS。

## 3. 构建

`build --target --source-root [--source-commit]`：

- target 必须不存在，避免覆盖旧发布。
- 先创建 target，再调用 `go_chi_bundle.build_bundle(target/package)`。
- 写 manifest、supply plan 模板、SHA256SUMS；任何步骤失败删除本次 target。
- 不联网、不读 Key、不复制源码 checkout/data/vendor。

## 4. 校验

`verify --root [--plan]`：

- 顶层布局/符号链接检查；拒绝额外/禁止内容。
- `release-manifest` schema/字段/commit。
- `validate_bundle(package)`；manifest 与 entry config/hash 一致。
- 包内文件集合严格等于允许集合；`bundle_files`/`dependency_locks` 一致。
- 重新计算 SHA256SUMS；不一致 → `release_checksum_invalid`。
- 可选 supply plan：`check_plan(plan)` 通过，且 plan 的 bundle root 解析到 `<release>/package`；否则 `release_plan_bundle_mismatch`。
- 输出 `status=valid`、source commit、bundle/release manifest SHA、文件数；不启动模型/世界/Trial。

## 5. 失败码

| 场景 | code |
| --- | --- |
| target 已存在 | `release_target_exists` |
| 源码 commit 缺失/非法 | `release_source_commit_missing` / `release_source_commit_invalid` |
| 根/布局/顶层内容 | `release_root_invalid` / `release_layout_invalid` |
| 禁止内容 | `release_forbidden_content` |
| manifest 缺失/字段 | `release_manifest_invalid` / `release_invalid` |
| bundle 身份/文件 hash | `release_bundle_identity_invalid` / `release_bundle_files_invalid` |
| 依赖锁不一致 | `release_dependency_locks_invalid` |
| SHA256SUMS 不一致 | `release_checksum_invalid` |
| plan 与包不匹配 | `release_plan_bundle_mismatch` |

## 6. 与 Z1/真实 Z6 的关系

- release 证明“包字节是什么”；delivery plan 证明“运行环境供应什么”；两者都通过仍不证明真实 Trial。
- 真实 Z6 还需：干净依赖安装/空状态目录、world/官方输入/MCP、真实模型、日志/trajectory/context、状态回收、owned 资源清理、分发 allowlist 检查。
- 当前测试只使用离线临时目录和合成 deps/resources；没有真实 Harbor/模型/官方任务。

## 7. 待外部 Gemini 审查

1. 顶层/包内 allowlist 是否足够防止 data/vendor/tests/轨迹/凭据混入？
2. 确定性构建是否成立（manifest/SHA256SUMS 不依赖宿主路径/时间）？`source_commit` 由调用方给出是否有伪造风险？
3. SHA256SUMS 是否覆盖 manifest/plan/package 全部文件；是否需要签名/keyless 证明？
4. 可选 plan 与 delivery check 的耦合是否合理；plan 模板是否应该校验为“未填写”而不是有效 plan？
5. 失败码/回滚（失败删除 target）是否会误删用户已有目录？
6. 真实干净环境安装/启动还需要哪些证据，当前离线 verify 不能代表什么？
