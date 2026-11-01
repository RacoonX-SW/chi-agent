# 设计：写入路径与父目录

## 现状

`writable()` 只接受 `<case_id>/<role|shared>/<file>`，但工具描述只说“permitted role workspace”；`write_file()` 在父目录不存在时直接返回 `ERROR: workspace parent unavailable`。CM 角色因此把文件写到 `care-manager/` 并被拒。

## 变更

1. 工具描述与 guidance 明确 `<case_id>/<role>/`，`<role>` 为精确 id。
2. `write_file()` 在父目录缺失时用 `mkdir(parents=True, mode=0o700)` 创建。
3. 创建后 `Path.resolve(strict=True)` 必须仍在 `workspace_root.resolve()` 之内，否则返回 `ERROR: workspace parent unavailable` 且不写入。
4. 最终文件仍以 `O_NOFOLLOW` 打开，符号链接文件本身不可写。

## 为什么不接受别名

角色目录是运行时判定依据（`workspace_path()` 用 `parts[1] in {role, "shared"}`）。接受 `care-manager` 会让目录名与角色脱钩，并使跨角色写入更难审计；正确做法是把约定说清楚。

## 验证

- 新增：缺失多级父目录时写入成功；`<case>/cm` 为指向外部的符号链接时拒绝且外部无文件。
- guidance：三角色 invariants 均包含 `<case_id>/<role>/` 与“exact role id”。
- 既有越权/失败测试保持通过。
