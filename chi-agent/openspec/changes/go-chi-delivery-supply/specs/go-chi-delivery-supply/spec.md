# Z1 配送供应行为契约

本契约覆盖 caller-owned 供应检查与离线准入；不授予真实 Harbor Trial、真实模型或官方判分。

## 需求：供应责任必须明确

### 场景：完整供应

给定 bundle、model/PDF 依赖、vendor、公开 instruction/handbook/tool refs、单角色 MCP、可写 state/logs 和仅模型 Key 的凭据配置，delivery check 通过并返回 bundle manifest SHA、plan SHA 和检查项；不得联网安装或读取 Key 值。

### 场景：缺包/缺依赖/缺 vendor

bundle 目录缺失、manifest/hash 不匹配、model/pdf 依赖目录缺失或 vendor `src/chi_bench` 缺失时，分别在启动前返回稳定错误码；不能把 no-op install 当作供应成功。

### 场景：资源与路径

instruction/tool refs 必须是普通文件、非符号链接、非隐藏/fixture/verifier/judge；handbook 必须是目录；非法绝对路径/`..`/隐藏段拒绝。

### 场景：MCP 与角色

role 与 MCP role 一致，provider/payer/cm 端口分别为 8020/8100/8200，路径必须是 `/mcp`；不允许 userinfo/query/fragment。

### 场景：state、logs 与 history

logs_dir 必须尚不存在；output_root 父目录必须存在且 output_root 不是链接；local history 要求 q_root 存在且 output_root=q_root/chi-evaluation；external history 不允许 q_root。

### 场景：凭据分离

plan 只允许 `OPENCODE_API_KEY` 作为模型凭据名；已知其他 provider/judge 凭据必须列入 forbidden_env；plan 不包含任何凭据值。官方模拟器/judge 凭据不进入 runner。

## 需求：install 与 run 的闸门

### 场景：install no-op

`GoChiHarness.install()` 不访问 environment、不下载/安装、不读 Key；包/依赖/vendor 由调用方预供应。`run()` 在读取 Key 前执行无 Key 预检；预检失败不得注入模型 Key。

### 场景：失败与清理

预检非零/无返回码、runner 非零/无返回码、日志/结果缺失或损坏时保留安全错误码，不自动重试；超时/取消交给 Harbor 清理。真实 Trial 的清理/持久化证据仍属 Z4/Z6。

## 需求：检查工具只读

### 场景：CLI

`go_chi_delivery.py check --plan --plan-sha256` 有效返回 0，无效返回 1 和稳定 code；不写文件、不联网、不读 Key。检查成功只表示供应形状满足契约，不表示真实 Harbor/模型/官方任务通过。
