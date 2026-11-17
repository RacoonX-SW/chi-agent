# Spec Delta

## ADDED Requirements

### Requirement: 正式源码按职责组织

正式源码 SHALL 在 `src/chi_agent/` 中提供 Agent 运行、上下文、工具、模型接入、账本、角色规则和评测适配七个职责子包，包根 SHALL 集中保留初始化、命令入口与交付文件。当前模块归属 SHALL 能够通过对应变更的完整迁移表核对。

#### Scenario: 从目录定位实现

- **WHEN** 读者浏览当前 `src/chi_agent/`
- **THEN** 七个职责子包 SHALL 分别以 `agent/`、`context/`、`tools/`、`models/`、`accounting/`、`roles/`、`evaluation/` 呈现
- **AND** 每个迁移前模块 SHALL 有唯一的实现位置，仓库调用方 SHALL 引用该位置

#### Scenario: 导入分类后的子包

- **WHEN** 调用方在仓库环境或独立导出包环境导入一个已收录模块
- **THEN** 该模块 SHALL 从自身源码树加载完整的包内依赖
- **AND** 子包初始化 SHALL 只建立包边界，导入 SHALL 沿用现有资源、凭据和网络访问边界

## MODIFIED Requirements

### Requirement: 交付入口兼容

新 Go 包和兼容评测包 SHALL 各自提供既有启动入口与参数，并可独立加载允许的源码和依赖。

#### Scenario: 启动新导出包的预检

- **WHEN** 调用方从隔离目录以原命令运行 `scripts/go_chi_entry.py` 或 `scripts/evaluation_entry.py` 的离线预检
- **THEN** 入口 SHALL 从导出包加载自有模块并核对实际包身份，使用既有的模式、退出码和安全错误口径

#### Scenario: Harbor 通过既有导入路径加载

- **WHEN** 合成 Harbor 检查用 `go_chi_harness:GoChiHarness` 加载 Go 包适配器
- **THEN** 适配器 SHALL 走相同的无凭据预检和合成启动边界

#### Scenario: 从仓库执行既有模块命令

- **WHEN** 调用方使用 `python -m chi_agent.cli`、`python -m chi_agent.bundle`、`python -m chi_agent.evaluation_bundle` 或 `python -m chi_agent.evaluation_cli` 运行帮助、构建、校验或离线预检
- **THEN** 命令 SHALL 接受原有参数并走对应的入口校验
- **AND** 源码子包分类 SHALL 通过包内导入加载相应实现

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

#### Scenario: 区分三代包布局

- **WHEN** 维护者验证 v1 平铺脚本包、v2 平铺 Python 包或 v3 职责子包
- **THEN** Go 与兼容评测校验器 SHALL 分别匹配各自的 schema、bundle ID 和固定成员集合
- **AND** v3 构建器 SHALL 按显式清单包含实际使用的子包初始化文件
- **AND** 将 v3 身份标记套用于 v2 成员目录的包 SHALL 被拒绝
