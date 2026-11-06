# chi-requirements-v1 执行清单

当前：契约冻结候选，按本清单离线实现；默认关闭，不进入当前九题候选。

## 1. 契约与状态

- [x] 新增 `chi-requirements-v1` 常量、v4 schema/completion schema，保持 v3 默认路径不变。
- [x] `TaskState` 可选 `requirements`/`instruction`；开启时校验 instruction、计算 SHA、初始化 requirements/declared/hash。
- [x] v4 requirements 完整快照校验：8 项上限、id、quote 原文子串/归一化长度、追加/终态/回退规则。
- [x] open→done/waived 来源、event/effect/scope/note 校验；`insufficient_evidence` 拒绝。
- [x] case 锁定与 claim/completion 时复验已有 done/waived 来源。
- [x] 四个 `chi_state_requirement_*` StateRefusal 码及优先级；整份更新原子回滚。
- [x] v4 completion 对象、status/count/open_ids、provenance_only 限制。
- [x] 共享 `_completion` 门禁：undeclared/empty/open 先于业务 readback；全闭合后继续原检查。

## 2. 工具、guidance、接线

- [x] `local_tools` 仅在开启时增加 requirements schema/description；off 保持原 schema/description。
- [x] `local-state-update` 完整快照透传；`local-claim_done`/`local-completion-check` 共享 v4 报告。
- [x] guidance 仅在开启时增加角色中立自检约束；off 版本/digest 不变，on 可区分。
- [x] entry `--requirements`、launch、runtime、TaskState 真实接线；缺 instruction/未知版本早拒。
- [x] journal 校验 launch requirements 与互斥；旧账/历史读取兼容。
- [x] entry 日志 reader、readiness inventory 支持 completion-v4 和新 reason；畸形 v4 明确 fallback。
- [x] dev operator/runner 配置透传、精确版本、缺省不传；Y shadow/摘要/恢复早拒；正式 Harbor 默认 off。

## 3. 测试

- [x] A 来源和结构：合法/伪造/重述/归一化-only quote；长度边界、0/8/9 项、重复 id、错误类型、未知字段、非法枚举；instruction 缺失/错误来源/hash 绑定；模型不能改 declared/hash/schema。
- [x] B 转换与事务：新项 open、合法追加；删除/重排/改 quote/终态改写/回退拒绝；缺省不改变；一项非法整份不变；体量上限不扩大。
- [x] C 来源范围：done 缺证据/跨 run/歧义/returned_error/refused/failed/neutral；未绑定 case 的 unattributed/conflict；锁定 case 复验；claim/check/report 一致；合法 waived + 只读 returned + 说明；mutation 不作豁免；insufficient_evidence 拒绝。
- [x] D 门禁及报告：undeclared/empty/open 精确 reason；全 done/含 waived 继续 readback；requirements 不掩盖未知写/失败文件/陈旧回读/claim 后写；不 claim 直接 final 保留未闭合报告；completion 计数/状态/非法嵌套反例；正常/损坏日志 fallback、首个错误不掩盖。
- [x] E 接线与回归：entry→launch→runtime→state→run_log 实际到达；禁网 MockTransport/合成工具；非法版本/互斥在任何凭据/派发前拒绝；off 的 state/completion/schema/description/guidance/digest 沿旧路径；固定时钟比较；同进程 v3/v4 隔离；provider/payer/CM 各一合成正例及负例；现有 facts/unknown/file/readback/claim 回归。

## 4. 交付

- [x] Docker 定向及适用全量：命令、镜像/解释器、退出码、passed/skipped/errors 分列；既有收集/import 错误单列。
- [x] 新 Go bundle/release 身份及隔离无 Key 禁网 verify/preflight。
- [x] 阶段报告：源码候选、实际改动、证据、失败、未验证项、独立复审重点。
- [x] REVIEW_STATE 短状态和报告链接。
- [x] 本地显式暂存/提交，固定实现 SHA `85b89664…`。
- [x] Gemini 独立复审 **Pass/LGTM，0 Blocker**；Docker 4 组数据一致。
- [x] 按用户要求 push 并创建 [PR66](https://github.com/xsw932187210-cell/chi-agent/pull/66) base=main；未 merge/auto-merge。
- [ ] 用户最终验收合并；合并后才进入主线，不自动启用 requirements 或恢复真实执行权限。

## 5. 合并后验证（2026-11-06）

- [x] P0：合并 main `dbbd356` 重建 bundle `eabec08e…`/runtime `f41021f4…`；B-005 成功；t015 requirements off 完成（34 HTTP、393.6s、completion v3 `mechanical_pass`/`observed`、claim、确定性 7/4/1）。
- [x] P1：同 bundle requirements on；B-006 成功；t015 `chi_run_time_limit`（37 HTTP、1829s），requirements `undeclared`、claim null。
- [x] 定位可发现性缺口：模型使用描述性 id、`REQ1`/`req-1`、短 quote，均被 `chi_state_requirement_invalid` 拒绝；schema/guidance 未暴露 id/quote 约束。
- [x] 修复 `47b5417`：`id` pattern `^r[0-9]{1,2}$`、quote 16..400（raw ≤800）/逐字子串、done/waived 规则进入 schema 和 v4 guidance；新增回归测试。
- [x] 测试：28 requirements OK；129 相关 OK/3 skipped；全量 654/18 skipped/3 既有 import error。
- [x] 新 release `454b048e…`/`933d4136…`、runtime `4835ee36…`；verify/preflight 通过。
- [x] B-007 成功（3 main、1400/118、receipt/seal 有效）。
- [ ] P1fix on-run：`final-c-provider-t015-p1fix` round1 settled、round2 HTTP429 `prefill_cap_refused` pending，`chi_http_error`、无业务写；按停止条件未重试，修复尚未在真实 on-run 中验证。
- [ ] 用户决定新 state+B-008 或显式 429 acknowledgement；不得静默清除 `p1fix-on` round2 pending。
