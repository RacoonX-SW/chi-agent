# Y 实现任务（DeepSeek接手后执行）

2026-10-31由DeepSeek实现者执行第1–5步，本地固定候选后停写；独立审核状态只在REVIEW_STATE及一份Y报告记录。执行细则见[五步计划](design.md)，停止条件优先于勾选清单。

- [x] 1. 核对规划PR合并/最新main与已有改动，建立新codex实现分支；明确可检测收益、限制、源/观察语义、大小边界和最小修改清单。
- [x] 2. 在Docker实现无网络/凭据/world依赖的纯原型及自造输入，区分来源有效与语义未判。
- [x] 3. 完成契约反例、保留失败，作出有依据的go/no-go；不依赖t011隐藏答案。
- [x] 4. go后做payer默认关闭的开发shadow接线与合成SDK/MCP/包检查。
- [x] 5. 停写、本地固定候选，完成单份待审报告/必要文档，回传用户；不push/PR/真实调用/自行验收。

勾选只表示实现者完成自测与交付，不代替Codex独立审核；真实B/C/患者/评审请求为0。证据、失败与未验证项见[Y报告](https://github.com/xsw932187210-cell/chi-agent/blob/fdff6cff629a6c7ccd0de0d37bdc18d92ff8a57d/chi-agent/reviews/payer-evidence-prototype-review.md)。
