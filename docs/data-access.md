# 资料访问与下载准备

记录日期：2026-10-20。当前阶段仍为规划，应用实现和付费评测暂停。

2026-10-21 补充：新增下载头痛新转诊任务公开的 `tool_reference.md` 和 `task.toml`，供只读任务拆解。未下载该题的隐藏判分答案或启动任务环境。

## 已知状态

- 用户提供批准邮件（抬头称呼为 `gugugaga`）；随后完成浏览器授权，CLI 核对实际用户名为 `xsw932187210`。已实际下载手册，访问验证通过。
- 已准备项目独立下载环境：`.venv-hf/`，`huggingface_hub==2.2.0`。
- 本次本机认证使用 `HF_HOME` 指向 `.coordination/huggingface/`，不改变用户原有 Hugging Face 凭据，不写 Git credential helper。
- 手册已全量下载并逐文件核对远端大小；公开任务只下载规划用子集，完整任务环境尚未就绪。
- `.venv-hf/`、`.coordination/` 和 `data/` 已验证受 Git 忽略规则覆盖。

## 已完成的下载

| 来源 | 固定版本 | 本地核对结果 |
| --- | --- | --- |
| `actava/managed-care-operations-handbook` | `f1210b294904792541116852f6074df8b84d89dd` | 全量 1,292 个文件，32,881,348 字节，保存于 `data/skills/` |
| `actava/chi-bench` | `chi-bench-v1.0.0` → `5ce88104df2a91e057619eb70fb51f56fc5949eb` | 截至 2026-10-21 共 9 个文件：4 个索引/说明、3 个 Agent 输入说明、头痛新转诊任务的公开工具说明与启动配置 |

详细文件名、字节数和本地 SHA-256 记录于 `data/source-downloads.json`（受 Git 忽略）。手册路径已确认是 `data/skills/managed-care-operations-handbook/{SKILL.md,references/}`。

未下载完整任务 fixtures 和共享世界，未创建表示完整任务数据就绪的 `data/.chi-bench-version` 标记，未构建 Docker 或运行模型。公开 `tasks.jsonl` 包含评测预期字段，不能作为被测 Agent 的输入或检索资料。

## 本机登录

在终端运行以下命令，并按输出在浏览器中完成授权。验证码会过期，不能重用旧聊天中的验证码。无需把访问令牌发到聊天中。

```sh
HF_HOME='/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.coordination/huggingface' /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.venv-hf/bin/hf auth login --format agent --no-add-to-git-credential
```

## 下载与后续补全方式

1. 已完成账号核对、实际文件访问验证及手册固定版本下载。
2. 已完成公开任务索引和 3 个 Agent 输入说明的固定版本下载与阅读，并补充核对头痛新转诊任务的公开工具说明与启动配置。
3. 后续确定 MVP、技术方案和预算后，再补全固定版本的任务资料；任务版本和运行时代码版本分别记录。
4. 完整数据下载、核对及必要的官方数据修正结束后，再建立运行环境并执行真实基线；不能把本轮的规划用子集当作完整任务数据。

手册下载可用以下等价命令复现；这会复用已下载的文件，并沿用本项目的凭据目录：

```sh
HF_HOME='/Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.coordination/huggingface' /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/.venv-hf/bin/hf download actava/managed-care-operations-handbook --repo-type dataset --revision f1210b294904792541116852f6074df8b84d89dd --local-dir /Users/asaki/Documents/ChatGPT/Kaggle/chi-agent/data/skills/
```

## 资料用于什么规划

已阅读总索引、医院侧角色索引和基础流程章节，以及 3 个代表性公开任务输入。用户已确认首版范围为医院侧申请准备；接下来确认输入输出、交付形态、技术栈、验收与预算。具体工具签名、字段和枚举仍待实际 MCP 契约核对。

手册访问批准不等于向第三方披露许可。手册原文及其衍生输出的使用、外部模型处理和公开范围按实际授权核对；不将受限内容提交 GitHub。

## 官方依据

- [CHI-Bench 下载布局与数据版本说明](https://github.com/actava-ai/chi-bench#setup-one-time)
- [手册结构和访问条件](https://huggingface.co/datasets/actava/managed-care-operations-handbook)
- [Hugging Face CLI 浏览器登录与下载](https://huggingface.co/docs/huggingface_hub/en/guides/cli)
