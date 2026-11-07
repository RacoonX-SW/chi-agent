# Spike：connect 前失败重试

日期：2026-11-07。状态：**spike/决策文档，未实现。** 只分析 connect 前重试的可行性、journal/usage/pending 语义和测试；不改 transport。

## 1. 当前代码路径

`go_chi_guard._handle_serialized()`：

1. `journal.reserve(raw, purpose, ...)`：先占位/记 request；
2. `dispatched = True`；
3. `lower.handle_async_request(request)`：连接 + 发送 + 读响应；
4. 若抛异常：
   - `chi_timeout`（`httpx.TimeoutException`/`TimeoutError`）或 `chi_transport_error`（`httpx.RequestError`）；
   - `journal.record_diagnostic(...)`；
   - pending 通常保留（没有 usage 可 settle）。

因此，当前没有“请求未发送”这一状态；connect 失败和 read 超时都走保守 pending。直接加 transport retry 只能减少瞬时失败，**不能保证 connect 失败不留 pending**。

## 2. 可选方案

### A. `httpx.AsyncHTTPTransport(retries=N)`

- 透明重试，guard 只看到一次 `handle_async_request`；
- 需要确认 httpx 的 `retries` 只覆盖 connect 失败，不覆盖 read timeout/429；
- 全部重试失败后仍会走当前 pending 路径；
- 无 attempt 级 journal 记录；
- 实现最小，但“连接前失败不留 pending”不成立。

### B. 自定义 connect-retry wrapper

- 包住 lower transport，只捕获 `httpx.ConnectError`/`ConnectTimeout`；
- 不重试 `ReadTimeout`/`ReadError`/429/5xx；
- 可记录 attempt 数/退避；
- 仍无法区分“reserve 后未发送”与“已发送但无响应”的 journal 状态；
- 需要 guard/journal 配合。

### C. wrapper + journal `record_not_sent`

- 在 B 的基础上新增 journal 方法：把已 reserve 的 request 标记为 `not_sent`/failed，零 usage，清 pending；
- 需要新 evidence/schema/审计字段，并证明不破坏旧账/旧 pending；
- 能真正满足“connect 前失败不产生 pending/usage”；
- 改动最大，需要独立设计/复审。

## 3. 需要验证的事实

- [ ] httpx `retries` 的确切语义：是否只重试 connect，是否包括 read timeout/429。
- [ ] `httpx.ConnectError`/`ConnectTimeout` 与 `ReadTimeout`/`ReadError` 的异常层级。
- [ ] 如何证明请求字节未发出（连接建立失败 vs 发送后断连）。
- [ ] journal 是否允许 `not_sent` 零 usage 记录，且旧 run/inspect/recovery 兼容。
- [ ] 重试是否受 `main_io_seconds`/`chi_admission_seconds` 总预算约束。
- [ ] 是否只用于 C，B 是否保持零重试。

## 4. 建议

**暂不直接实现 transport retry。** 先完成事实验证和 journal `not_sent` 设计；如果只想降低瞬时失败，可选 A 作为保守缓解，但必须接受“全部重试失败仍 pending”。若要满足“connect 前失败不 pending”，走 C，并单独复审。

## 5. 验收场景（实现时）

- connect 前失败两次后成功：有界重试成功；无 usage/pending；attempt 可审计。
- connect 前失败达到上限：`not_sent` 零 usage；不产生 pending；安全停止。
- read timeout/断连：不重试；pending/unknown 保留。
- 429/5xx：不自动重试。
- 工具/业务写：不重试。
- 旧 pending/旧账/旧 evidence 不变。

## 6. 非目标

- 不实现 429/5xx 重试。
- 不重试工具调用/业务写。
- 不改变现有零自动重试默认。
- 不授权真实 B/C/Trial/judge/发布。
