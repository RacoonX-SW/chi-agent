# 主请求读窗口契约

本契约覆盖 Go CHI 主请求的时间参数与超时语义；不改变确认请求、编码-B 准入或 operator 墙钟。

## 需求：读窗口覆盖已观测长生成

### 场景：长上下文生成

给定单个主请求，服务端在 90s 后返回 200 和完整 usage，客户端读窗口必须仍未放弃，请求正常结算。

### 场景：服务端挂起

给定服务端在读窗口内不返回任何字节，请求以 `chi_timeout` 终止，usage 记 unknown，`state.pending` 保留，运行停止且不自动重试。

## 需求：策略自洽

### 场景：窗口关系

`main_io_seconds > main_read_seconds`、`main_read_seconds >= 180`、`confirmation_read_seconds > main_read_seconds`、`main_io_seconds < chi_admission_seconds`、`chi_operator_seconds < operator_max_seconds` 必须同时成立。
