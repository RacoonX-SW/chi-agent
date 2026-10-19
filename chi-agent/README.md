# CHI Workflow Agent

目标：开发可追踪的医疗行政流程 Agent，在获得必要访问权限后使用 CHI-Bench 模拟环境验证。业务 MVP 优先考察医疗机构侧事前授权流程。

当前状态：只有协作约定与首轮 OpenSpec 文档，尚无实现、模型运行、报名确认或评测成绩。当前 PATH 未找到 OpenSpec CLI，未执行其校验。

## 现在先做什么

1. 用户登录 [Kaggle 赛事页](https://www.kaggle.com/competitions/chi-bench)，核对并接受当前赛事规则，完成报名。
2. 同时到 [Managed-Care Operations Handbook](https://huggingface.co/datasets/actava/managed-care-operations-handbook) 申请访问。页面说明人工审核，通常一个工作日回复；这不是审批时限保证。
3. 申请时如实说明独立非商业研究、参赛目的，以及拟公开的成果范围。页面对手册、数据和衍生输出披露设有条件；按实际授权确认公开范围。
4. 执行器读取下方首轮任务包，先实现不调用模型的环境检查。获得访问后再收集官方单任务基线证据。

## 协作入口

- [共同协作约定](../COLLABORATION.md)
- [执行器交接指令](openspec/changes/bootstrap-baseline/handoff.md)
- [首轮目标](openspec/changes/bootstrap-baseline/proposal.md)
- [验收场景](openspec/changes/bootstrap-baseline/specs/benchmark-readiness/spec.md)
- [实现任务](openspec/changes/bootstrap-baseline/tasks.md)

## 后续变更方向

- M0：环境就绪、官方单任务基线及证据记录（本轮）。
- M1：自己的 Agent 执行循环、角色工具接入、规则检索和证据输出。
- M2：流程阶段检查、失败处理、预算控制及固定任务集对照。
- M3：演示、复现说明和经过验证的简历表述。

后续变更尚未细化或实现。官方模拟器、MCP 工具和评测器属于上游能力，不能作为自己开发的成果。

## 资料来源

核对日期：2026-10-19。

- [官方仓库与安装说明](https://github.com/actava-ai/chi-bench)
- [官方单任务 Quickstart](https://www.actava.ai/benchmarks/docs/quickstart)
- [自定义 Agent 接入](https://github.com/actava-ai/chi-bench/blob/main/docs/extending.md)
- [OpenSpec 结构与场景格式](https://github.com/Fission-AI/OpenSpec/blob/main/docs/concepts.md)

依赖版本、任务 ID 和命令以实施时固定的上游提交及对应文档为准；不把示例模型名当作已经可用的配置。
