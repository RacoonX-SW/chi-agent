# OpenCode Go 的 DeepSeek V4.1 Flash 接入

用户已在本地 `.env` 新增 `OPENCODE_API_KEY`，要求将后续模型调用适配为 OpenCode Go，模型继续使用 V4.1 Flash。本轮建立可复用的 provider 客户端、独立核算与受控 SDK 工具往返入口，供下一项正式入口接线使用。

原 native 路由、固定 profile、K/J/开发评审账目及历史验收保持其身份；不把美元金额写进人民币累计，不以订阅替代未知用量阻断。本轮不恢复 t013/t019、Claude 判分或 F.5 配送，也不直接打开现有正式 `live`。

Go 文档明确面向 coding agents；CHI 非编码任务及独立临床评审的套餐支持仍未确认。本轮真实输入限定为本仓库新建的固定合成代码样例，不发送任务资源、手册、患者或评分资料。技术接通与 CHI 用途/正式接线分别验收。

详细协议及场景见 [design](design.md)，执行清单见 [tasks](tasks.md)。
