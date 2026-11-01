# Go CHI 主请求读窗口调整

建立：2026-11-01。基于 `origin/main` `dac6080`。本变更只改固定 `TIME_POLICY` 与测试，不重跑真实运行。

## 观测

| run | 输入 tokens | 服务端耗时 | 客户端结果 |
| --- | ---: | ---: | --- |
| provider `real-ext-provider-001` round 17 | 369,422 | 67.7s（Console 200） | 60s 读超时 → `chi_timeout`，usage unknown |
| CM `real-ext-cm-002` round 8 | 105,771 | 90.8s（Console 200） | 60s 读超时 → `chi_timeout`，usage unknown |

两次都是**客户端先放弃、服务端随后成功计费**，不是服务端失败。同批次其他请求耗时 2.4–45.7s；两次失败都出现在上下文显著增长之后。

现有策略 `main_read_seconds=60`、`main_io_seconds=120`：读超时先于总墙钟触发。两次失败都低于 120s 总墙钟，说明只要读窗口更大即可完成。

## 决定

- `main_read_seconds`: 60 → **240**
- `main_io_seconds`: 120 → **300**
- 其他时间不变：confirmation 读 360 / 墙钟 420、connect 10、write/pool 60、B 准入 180、CHI 准入 900、operator 1380/3600。

理由：240s 是已观测最大耗时（90.8s）的 2.6 倍，覆盖到接近 1M 上下文的理论增长；300s 墙钟留在 900s 单轮准入和 1380s operator 窗口之内，避免单请求吃满运行预算。超时语义不变：仍记 unknown、清 pending 前停止、零自动重试。

## 风险与边界

- 真·服务端挂起时，失败会晚 180s 出现；行为仍是 unknown + 停止，不会变成成功。
- 这与自动重试无关，不改变失败判定或账目。
- `TIME_POLICY` 进入 runtime profile，因此会改变包身份；下次真实运行需要新 release + 新 coding-B，不能沿用旧 B。
- 本变更不解决“上下文无限增长”：provider 已累计 3.1M input。预算/压缩仍是 F4 的独立议题。
