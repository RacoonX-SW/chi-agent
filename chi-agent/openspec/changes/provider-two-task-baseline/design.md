# 设计与实验条件

## 任务选择

根据固定公开索引和 instruction 提出任务。最初 t008/t031 的公开输入已读过但未用于改代码；固定官方 `_is_pa_um_judge_eligible()` 返回 false，故排除，不放宽评审契约。其必要资源与筛选记录保留在忽略目录。

继续按公开输入核对的 t015、t024、t026 同样被现有 eligibility 门禁排除。随后使用已有固定索引的兼容元数据减少下载，并按公开输入的临床情境冻结以下两题（运行结果不再改变清单）：

| task_id | 公开输入情境 | instruction SHA-256 |
| --- | --- | --- |
| `pa_t013_t013_o002_p01_new_referral_provider` | 腰椎神经根病、功能下降及结构化康复评估 | `30a214794621e177678c3481aafa15ca87c4ffab6c8c8cf4dec12f87b87f2c05` |
| `pa_t019_t019_o001_p01_new_referral_provider` | PAP 不耐受的睡眠呼吸暂停、进一步手术评估 | `409303f50fed1907dac8909a4b2251d98eb248e91e8bef862786cf1a06181d46` |

两题均为 provider / contract_v5、固定官方语义 eligibility=true；虚拟空 export 的 adapter 预检确认原始目标 chart 和完整 workspace 可构建（不算任务执行或判分）。统一 prompt 版本 `2026-04-28-pa-provider-v3`，原 prompt SHA-256 `42db1f985695b877c77c36607efe6459bb7a26590233d9058f37015b8f49dbe2`。详细必要文件指纹绑定实现的任务资源定义。所选必要资源从固定版本获取，原始资源不提交 Git。

## 参数与来源

旧 J/A 和旧 t018 的身份及证据保持原意义。K 的新 C 使用显式 `--task-id`，限定冻结白名单，贯通 claim、controller、worker、官方环境、公开投影、终态捕获和评审。B 是当前 participant 源码/SDK/profile 的工具接入证据，可复用于两个任务；历史 B 的旧 task 字段不改写为新题。

任务资源定义绑定固定版本、任务目录、必要文件哈希/大小及共用世界身份。调用前验证普通文件、祖先无链接、任务/manifest/版本一致性；拒绝任意路径、未知任务、缺件、篡改和不支持契约。资源配置及新增 participant 模块进入源码身份；改变它们需 rebind 和新 B。各 C 记录独立任务资源身份，不把某题专用内容混入共享提示或策略。

复用旧固定 world 镜像、Python 3.12 和既有锁定 SDK/PDF 卷；仅向 world 只读挂载必要的选定 task 目录，沿用官方 entrypoint 和已存在的固定共享世界。participant 只投影公开 instruction/reference、授权 handbook 以及既有受限业务 workspace。隐藏 fixtures、expectations、原始 world 和评审目录不对模型文件工具开放。

## 固定首轮

participant 维持既有 `deepseek-flash`、thinking enabled/high、Chat Completions、最多 30 轮、每轮最多 8192 输出 tokens；B 维持小轮数工具闭环。reviewer 维持同一 DeepSeek profile、既有官方 PA prompt 与内联补充协议、32768 输出 tokens、360 秒总截止及既有单次读取界限。两题各用相同角色配置，不按题修改提示、工具许可、轮数或模型；只有公开任务输入和独立世界/attempt 不同。

运行前留存共享源码/profile/提示/镜像/依赖和每题资源指纹。每题默认一次自主 C 和一次开发评审；工程阻塞可据证据修复，但保留全部尝试，必要源码变更重新审核/B；不得静默重跑、不为取得全通过而调参循环。模型请求零自动重试，未知用量阻挡后续调用。

## 终态和诊断

每次新世界、全局唯一 run-id 和独立 claim，共用既有 K 累计账目及单 controller 锁；不得按题新建零账。保留旧 adoption、source transitions、receipt、失败和费用。review 继续使用独立累计账目。

runner 已退出时，在 world 清理前捕获完整 export、固定 expectations 和原始 world。非零退出仍保留失败身份和可核对终态；wait 异常时先按持有的精确 runner 句柄停止并确认静止，无法确认则标记捕获不可用，不把运行中快照称为终态。捕获失败不阻止资源精确清理。

评审交叉核对 task、资源指纹、源码、capture、claim、run journal、orchestration 和清理。失败尝试若有可信完整终态、runner 静止和已知结算，可作失败诊断，报告保留失败标签；缺来源、未清理、pending 或未知用量不得付费评审。不得把 incomplete、缺字段或解析失败改成通过。

结果分层为工程执行、业务可观察终态、确定性部分检查、DeepSeek 开发判断。official_reward 始终 null；本地 verdict 不作为官方评分或主代理独立临床裁决。下一项通用改进从真实证据提出，验证方案固定条件、只变一个通用机制，区分已见开发题与后续新任务。

## 验证和文档

一个 Terra/high 实现并在 Docker 自测，停止写入后固定候选；主代理按差异和必要调用代码独立复验，再实际运行。合成边界覆盖任务传播、资源篡改/路径、跨题身份冲突、失败捕获/停止、旧账与 B 接续、未知用量、隔离/清理及相关回归；不重做已通过 G/H 的安装和打包流程。

README 只补运行方法；学习账本记录实验控制、失败归因和改进验证的讲解与理解证据；REVIEW_STATE 只存短状态；一份 `reviews/provider-two-task-baseline-review.md` 记录候选、筛选、全部实际尝试、工具/用量/耗时/估算和限制。原始资源、轨迹、评审与秘密仍只在忽略目录。
