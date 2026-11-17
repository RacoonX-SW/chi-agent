# Tasks

## 1. 审批与基线

- [x] 1.1 将用户对本版提案的明确批准记录到 `proposal.md`，核对基线 `e2404fb`、实施分支与工作树状态，确认现有未跟踪提案完整保留。
- [x] 1.2 在 Docker Python 3.12 中固定基线的两种 v2 包、既有 v1 校验样本和 Trace/Replay 输出，记录包摘要、实际镜像及依赖挂载，核对样本可读且处于隔离临时输出位置。
  - 离线 Docker `chi-agent-dev:latest`（镜像 b22f7c664bf5），只读挂载 model、pdf 依赖卷及 vendor；四个历史包构建和自校验成功，基线 replay 已生成。命令及摘要见 `/private/tmp/chi-source-layout.ETKRBZ/baseline-commands.log`。

## 2. 源码分类与调用迁移

- [x] 2.1 按设计表迁移 35 个模块并建立七个轻量初始化文件，核对 42 个原文件逐项有唯一去向，包根保留的 7 个文件可定位，更新 README 的源码结构说明。
  - 对照设计表迁移 35 个模块，七个根文件保留，新增七个轻量初始化文件；README 已列出职责目录。
- [x] 2.2 同步模块内导入、函数内和动态导入，以及 `scripts/` 和现有测试的引用与 patch 目标，在 Docker 中运行导入检查和受影响的现有单元测试，核对引用实际指向新实现。
  - 导入检查通过（`--allow-unknown`），最终全量自测 1178 passed、44 skipped、403 subtests（含新增两项回归）；首轮 1138 passed、38 failed，原日志被重定向覆盖，未保留。
- [x] 2.3 修正移动模块的资源根定位、运行身份源文件清单与入口接线，用既有根模块命令的帮助和预检核对参数、退出码、配置及资源定位。
  - 调整子包资源深度、Go 动态导入和两处运行身份清单；四个根命令帮助与两种隔离包预检通过，日志见临时目录 `candidate-final-packages.log` 和 `candidate-*-final-preflight.log`。

## 3. 两类导出包与历史兼容

- [x] 3.1 为两类包冻结 v1、v2 成员清单，声明 v3 的显式嵌套路径和必要初始化文件，同步构建、验证、release 及身份处理，在现有包测试中核对三个版本的正确匹配。
  - v1、v2 字典与基线逐项一致；新校验器成功验证四个历史样本及两个 v3 包，命令和摘要见 `baseline-commands.log`、`candidate-build.log` 和 `candidate-final-packages.log`。
- [x] 3.2 针对嵌套包补齐现有测试未覆盖的缺失初始化文件及跨版本目录错配回归，并运行既有额外成员、链接和篡改拒绝检查，确认错误仍走安全错误口径。
  - 两类包新增初始化文件缺失、v2 目录与 v3 身份错配检查，相关包测试 16 passed、15 subtests passed；既有完整测试覆盖额外成员、链接和篡改。
- [x] 3.3 分别构建并校验 Go 与兼容评测新包，在关闭网络且仓库外的目录执行原入口的无凭据预检，核对包内依赖闭合，并同步两份运行手册中的结构与版本说明。
  - 两类 v3 包构建和隔离无网络预检通过；Go 55 成员，兼容评测 22 成员，两份手册已更新；release 外层构建及校验通过。候选包及日志保存在 `/private/tmp/chi-source-layout.ETKRBZ`。

## 4. 集成与独立审核

- [x] 4.1 主代理在固定候选上运行 Docker Python 3.12 全量离线回归与 controller 专项，按实际记录通过、失败、跳过和环境限制，核对常规验证入口可执行。
  - 独立候选 `6ef5e9a`，常规入口 `CHI_VENDOR_DIR=<原 vendor 路径> bash scripts/tools/verify_offline.sh --allow-dirty` 通过。此参数保留无关未跟踪提案，已提交源码固定且 Diff 为空。1178 passed、44 skipped、403 subtests，与基线相比新增两项通过，既有跳过数量相同。controller 原专项 14 项通过，复用现有 Harbor overlay 后扩展专项 40 项全部通过。日志在临时审核目录 `independent/verify-offline.log` 和 `independent/controller-harbor-overlay.log`。
- [x] 4.2 运行现有合成 Harbor 入口演练，对照基线和候选的同一 Trace/Replay suite，确认工具事件、派发、状态与完成声明的行为差异为空，并保留各自源码和环境身份。
  - 原始两份 replay 报告保留，原比较器按预期拒绝不同 evaluator。独立对照使用一份固定评估器字节，只通过显式 flat/grouped 导入选择器加载两棵只读源码，比较器契约沿用原实现。4/4 合成用例通过，`differences=[]`。共同 evaluator 身份 `442a68fd…`，两侧源码身份分别 `ceaa5161…`、`a2fb0f3b…`，报告与临时控制器在 `independent/baseline-common`、`candidate-common`、`replay-comparison.json` 和 `common_replay_evaluator.py`。
  - 复用固定 vendor、原依赖卷和现有 Harbor overlay，运行导出包的 `claim-blocked` 与 `runner-nonzero` 合成 Trial，两者均通过既有演练断言，确认无完成声明时阻断、返回码 23 传递、合成凭据无泄漏和容器清理。初次输出挂载与缺少探针挂载的设置失败日志分别保留，补齐挂载后以新目录复验，源码候选保持 `6ef5e9a`。日志为 `independent/harbor-*-r3.log`。
- [x] 4.3 审阅 Diff、迁移表、两类上传清单和历史包身份，确认工具契约、Prompt、业务状态、预算和费用规则符合迁移验收要求，执行 `git diff --check` 与 OpenSpec 严格校验，将独立审核和验收证据写入最终 PR 描述。
  - 主代理在 Docker 中独立核对全部模块去向、七个初始化文件、两类 v3 显式清单及导入闭包，V1/V2 字典与基线逐项一致。37 个原模块经导入与已批准路径变更归一化后 AST 相同，其余五个构建、入口和身份模块已逐项审阅。Go 清单 55 成员与评测清单 22 成员匹配迁移表，闭包缺项均为 0。四个历史包保持原 manifest 身份并通过校验，独立审核和验证结果已写入 PR #107。`git diff --check` 与本 Change 严格校验通过。

## Workflow follow-up

- 按项目审批流程在最终 PR 分支同步规格并归档本 Change，复核归档结果。
- 显式提交和推送迁移内容，创建以 `main` 为目标的 PR，由用户最终验收和合并。
