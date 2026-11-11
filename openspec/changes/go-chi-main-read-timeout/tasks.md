# 主请求读窗口执行清单

当前：策略与测试已改；真实运行未重跑，等待复审。

## 实现

- [x] `TIME_POLICY`：`main_read_seconds` 60→240、`main_io_seconds` 120→300，其余不变。
- [x] `profiles/go-chi-entry.json` 同步为 240/300（复审阻断项：配置漂移会让 `_identity()` 必报 `chi_config_invalid`）。
- [x] 新增不打桩的配置一致性测试：`CONFIG` 必须等于 `profiles/go-chi-entry.json`。
- [x] `AsyncClient` 的默认 timeout 改用 `TIME_POLICY`，不再写死 60.0。
- [x] 超时测试改为从 `TIME_POLICY` 读取，避免与实现脱节。
- [x] 新增策略不变量测试（读窗口、墙钟、准入、operator 关系）。

## 验证

- [x] Docker 定向：guard/contract/entry 31 tests OK。
- [x] Docker 全量：472 tests，2 个既有环境错误（缺 `anthropic`），8 skipped。
- [x] 复审阻断修复后复跑：`config_matches 240 300`，定向 43 tests OK。
- [x] 外部 Gemini 首轮复审：两项逻辑通过，发现配置未同步阻断。
- [ ] 外部 Gemini 复核修复后的固定候选。
- [ ] 新 release + 新 coding-B（`TIME_POLICY` 进入 runtime profile，旧 B 不适用）。

## 明确不做

- [x] 不重试 provider/CM，不改 `state-v2`/`state-v3`。
- [x] 不引入自动压缩、动态超时或自动重发。
- [x] 不改变确认请求、判分或额度。
