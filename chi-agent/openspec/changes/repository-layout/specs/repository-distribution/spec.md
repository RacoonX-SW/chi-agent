# 仓库与导出包交付

## Purpose

让维护者和读者直接从 Git 仓库根目录定位阶段成果、正式代码和可运行入口，并让既有导出包与历史结果能够按原始身份持续复核。

## ADDED Requirements

### Requirement: 仓库根目录提供当前交付入口

Git 默认分支 SHALL 在根目录提供项目说明、Docker 快速开始、源码、分类脚本、测试和开发规格。

#### Scenario: 浏览当前阶段成果

- **WHEN** 读者打开仓库首页
- **THEN** README SHALL 展示已核对的累计开发覆盖，按公开任务 ID 去重并按 Provider、Payer、CM 汇总
- **AND** README SHALL 概述最新 `16384` 六题基线、注明 `official_reward=null` 并链接成果证据索引

#### Scenario: 从仓库根目录构建并导出

- **WHEN** 读者在干净检出中按根 README 的步骤使用 Python 3.12 Docker 环境
- **THEN** 构建和导出命令 SHALL 从 Git 根目录解析源码与配置
- **AND** 运行手册 SHALL 提供一个常规离线验证命令，覆盖开发回归、controller 专项及两种导出包的隔离预检

### Requirement: 维护记录可追溯

主线文档 SHALL 提供包运行、协作和当前审核所需的入口。学习材料、逐轮验证记录和历史阶段报告 SHALL 从整理前的固定 Git 提交查阅。

#### Scenario: 查找结果或未决事项

- **WHEN** 维护者沿 README 或 AGENTS 中的入口核对结果、授权或历史失败
- **THEN** 链接 SHALL 解析到对应的当前材料或固定历史证据
- **AND** 记录 SHALL 保留未决事项、旧账本的原身份及其失败或未结算状态

#### Scenario: 浏览默认分支文档

- **WHEN** 读者浏览当前 `docs/`
- **THEN** 该目录 SHALL 只包含两份包运行手册
- **AND** 重排验收详情 SHALL 集中记录于对应 PR

### Requirement: 交付入口兼容

新 Go 包和兼容评测包 SHALL 各自提供既有启动入口与参数，并可独立加载允许的源码和依赖。

#### Scenario: 启动新导出包的预检

- **WHEN** 调用方从隔离目录以原命令运行 `scripts/go_chi_entry.py` 或 `scripts/evaluation_entry.py` 的离线预检
- **THEN** 入口 SHALL 从导出包加载自有模块并核对实际包身份，使用既有的模式、退出码和安全错误口径

#### Scenario: Harbor 通过既有导入路径加载

- **WHEN** 合成 Harbor 检查用 `go_chi_harness:GoChiHarness` 加载 Go 包适配器
- **THEN** 适配器 SHALL 走相同的无凭据预检和合成启动边界

### Requirement: 按已知版本验证包身份

每种 bundle 的校验器 SHALL 分别使用该版本的固定成员清单与既有字节校验机制，发布包 SHALL 验证内层包、清单和校验和的一致性。

#### Scenario: 复核迁移前后的包

- **WHEN** 校验器读取基线提交生成的上一版包或当前源码生成的新包
- **THEN** 校验器 SHALL 按对应版本验证完整目录和字节，并返回该包自身的 manifest 与配置身份

#### Scenario: 拒绝破坏成员边界的包

- **WHEN** 包的版本与成员目录不符，或含缺失、额外、链接、被篡改的文件
- **THEN** 校验器 SHALL 拒绝该包，并给出对应的安全错误

#### Scenario: 检查导出内容和既有记录

- **WHEN** 维护者离线构建新包，并只读复核旧包或旧运行记录
- **THEN** 新包 SHALL 只收录显式清单中的程序、配置、锁和手册
- **AND** 旧包、凭据、任务数据、手册源数据、vendor checkout、账本和原始轨迹 SHALL 保持其原有本地内容和身份
