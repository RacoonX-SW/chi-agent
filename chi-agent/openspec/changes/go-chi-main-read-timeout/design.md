# 设计：主请求读窗口

## 现状

`ChiGuard._handle_serialized` 对每个请求设置两层时间：

- `request.extensions['timeout']['read']`：httpx 单次读取超时（`main_read_seconds`）；
- `asyncio.timeout(...)`：整个请求墙钟（`main_io_seconds`）。

非流式响应在生成完成前不产生字节，所以读超时直接决定“服务端还在算，客户端是否先放弃”。

## 目标

让读窗口覆盖已观测的长上下文生成时间，同时保持失败语义和运行预算：

1. `main_read_seconds=240`、`main_io_seconds=300`。
2. `main_io_seconds < chi_admission_seconds(900)`，单请求不会耗尽整轮准入。
3. `main_io_seconds < chi_operator_seconds(1380)`，operator 仍能在自身窗口内收尾。
4. 超时仍映射 `chi_timeout`：记录 response/diagnostic 证据、usage unknown、`state.pending` 保留、运行终止。

## 不采用的替代方案

- **自动重试或延长后重发**：账户会为同一请求二次计费，且未知状态不能靠重发消解。
- **只做测量不调窗口**：两次失败已证明 60s 不足，继续测量只会重复浪费请求。
- **按上下文大小动态调超时**：缺少真实 tokenizer 与耗时分布，先固定窗口；动态策略需要独立证据。
- **自动压缩上下文**：F4 已给出“不采用自动压缩”的结论，本次不改。

## 测试

- 策略不变量：`main_read_seconds >= 180`、`main_io_seconds > main_read_seconds`、confirmation > main、main_io < chi_admission、operator < operator_max。
- 配置一致性：`profiles/go-chi-entry.json` 必须与 `go_chi_entry.CONFIG` 全等；测试不得打桩 `_identity`，否则配置漂移不可见。
- 现有超时测试改为读取 `TIME_POLICY`，不再写死 60/360，避免策略调整后测试与实现脱节。
- 既有 `chi_timeout` 路径测试（墙钟、取消、pending 保留）不变。
