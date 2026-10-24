状态：2026-10-24 用户已仅恢复 D0 开发协作，由用户指挥 Gemini 实现与容器内自测，Codex 本次先保存规划基线。A/B/C、参赛模型 API 和官方判分仍暂停。第 0 节只表示资料拆解完成，不代表候选实现或真实基线已验收；本次准备不代勾实现方或审核方任务。

最新取舍：本地官方评分暂缓，先做离线与无评分开发验证；缺 Anthropic 不阻塞全部开发。已核对的 cb CLI 未见直接跳过 judge 的开关，开发入口需实际验证。见 `docs/development-preparation-2026-10-21.md`。

执行顺序以 [分段交接包](handoff.md) 为准，不按编号误把付费兼容性验证提前到离线修复之前。D0 先完成包装、配置和离线证据；A 验证实际环境/工具与入口；B 验证候选模型往返；C 才做一次任务执行。每段交付稳定候选，由 Codex 验收，未授权阶段不自动启动。

2026-10-24 环境方式按用户要求改为 Docker 内开发；依赖安装、下载和测试均在容器执行，宿主机不配置项目环境。D0 可构建/启动开发容器，不启动官方任务世界。详见 [Docker 工作流](../../../docs/docker-workflow.md)。下列实施项均未完成。

## 0. Understand the first official task

- [x] 0.1 Select the public provider task pa_t018_t018_o001_p01_new_referral_provider and read its fixed-version instruction.
- [x] 0.2 Inspect its public tool reference and task setup; record 30 static tools, namespaces and base timeouts without reading hidden task answers.
- [x] 0.3 Deliver the input/tool/workflow/scoring walkthrough with live schema and real reward explicitly unverified.
- [x] 0.4 Align OpenSpec context and baseline planning with the competition route, preserving the coding pause and unresolved runtime/budget decisions.
- [x] 0.5 Record the user's 5 CNY first-round runtime budget selection, separate coding costs and retain the implementation/paid-run pause; runtime profile remains a candidate.
- [x] 0.6 Prepare the staged D0/A/B/C handoff with scope, evidence identity, review gates and stop conditions; no executor dispatch or implementation activation.

## 1. Inspect and freeze the baseline

- [x] 1.1 Read project instructions and these artifacts; record repository state and actual executor identity.
- [x] 1.2 Check host Docker availability and container Python/uv/dependencies per mode without invoking a model; do not require host project package installation.
- [ ] 1.3 Fetch the official source into an ignored directory and pin its actual commit; inspect that version's installation, task and CLI contracts.
- [ ] 1.4 Record user-controlled prerequisites separately: registration, handbook approval and local credentials; do not claim they are complete without evidence.
- [ ] 1.5 Verify the candidate provider/model/API/mode through the selected harness, including consecutive tool exchanges and required history fields; record the actual effective profile before the task attempt.

## 2. Implement the bounded wrapper

- [x] 2.1 Add the minimal project manifest and configuration example required by the wrapper; use environment-variable references for secrets.
- [x] 2.2 Implement a no-model readiness command with clear missing-dependency/configuration output.
- [x] 2.3 Add a single-task baseline entry point with actual argv invocation, finite limits, isolated result directory and failure reporting.
- [x] 2.4 Produce a local manifest linked to real upstream results; preserve reward 0 and null verdicts, and retain unknown usage as null.
- [x] 2.5 Add focused offline checks for missing dependencies/configuration, command failure, timeout, missing verdict and fixture success; default checks require no network or API key.
- [x] 2.6 Verify a bounded ungraded entry point against the fixed upstream; report unsupported paths without inventing CLI flags or patching the official judge (D0: unverified ungraded real execution blocked before subprocess with unsupported reason; dry-run preview preserved).
- [x] 2.7 Report readiness per mode, retain ungraded traces and null reward, and identify simulator/API dependencies separately. Existing project.yaml and wrapper behavior require review for these distinctions.
- [x] 2.8 Enforce bounded calls/generation and pre-request budget checks; record unknown use and budget stops, prevent automatic whole-task reruns and start the measured attempt from a clean initial world (D0: evaluate_budget implemented, reservation & unknown usage logic verified offline, limits forwarded via agent_kwargs).
- [x] 2.9 Provide the minimal development image, Compose entry points, dependency lock and controlled build context; run offline checks inside containers, persist source/results and keep secrets/restricted data out of the distributable image (D0: requirements.lock committed, Dockerfile uses pinned image & locked dependencies, socket mount removed).
- [ ] 2.10 At stage A, verify task-container creation from the containerized scheduler using the existing engine, actual mount source paths, network endpoints, artifact persistence and cleanup; retain the official runtime contract.

## 3. Verify and hand over

- [x] 3.1 Run and record actual offline checks; provide diff, exact commands, exit codes and limitations.
- [ ] 3.2 Once implementation is resumed and prerequisites/budget are set, verify live tools and one real ungraded Agent execution; retain local evidence and do not claim official success.
- [ ] 3.3 Report measured duration and available usage/cost, failed stages and implications for the next change; identify unmeasured fields.
- [ ] 3.4 Codex independently reviews the code and applicable offline checks; user inspects the demonstrated result.
- [ ] 3.5 Deferred by user: run the original official verifier only if local grading is later requested with its prerequisites available; retain the verdict, scorecard and resource sources.
- [ ] 3.6 Demonstrate the applicable stage's clean container startup without host Python/uv/Node dependencies; record image/interpreter/dependency identity and disclose unverified architecture/runtime paths without repeating a paid task attempt.

Do not check 3.2 based on a dry run or fixture, or 3.5 based on ungraded execution. Do not mark Codex/user acceptance complete on their behalf. If access or the development entry point is unavailable, hand over completed work with the real-run prerequisite still open. Deferred grading stays explicit without blocking all other development.
