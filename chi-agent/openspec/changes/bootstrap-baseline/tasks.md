当前阶段、授权与已通过身份以 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md) 为准。以下已勾选项保留其历史验收范围；旧双代理人数与开发版本不覆盖现行协作约定。

## B. Offline preparation of model/tool exchanges

用户于 2026-10-26 恢复 B 规格与离线实现，一个 `gpt-6-luna` / `high` 实现子代理，主代理独立审核。真实参赛模型 API、C 与官方判分继续暂停；本节不代勾 1.5 的真实 provider/harness 验证。

- [x] B.1 Verify PR #4 merged and create a B work branch from the latest `origin/main` before writing.
- [x] B.2 Specify offline-only transport, candidate profile, at least two synthetic tool exchanges, history preservation, budget gates, failure boundaries and reference-runner gaps.
- [x] B.3 Implement the bounded adapter and synthetic probe without a live transport, credentials, official world or relaxed production gate.
- [x] B.4 Self-test the production probe and affected regressions in the existing Python 3.12 Docker image with networking disabled; retain local evidence and distinguish synthetic usage from unmeasured provider usage.
- [ ] B.5 Freeze the candidate; independently review/recheck normal, invalid-call, post-tool rejection, limits and unknown-usage paths; record one review and learning entry.
- [ ] B.6 Push the bounded work branch and create a base=main PR for user review/merge; do not merge or enable a later stage.

## E. Align development and controller Python with the official runtime

用户于 2026-10-25 授权本项环境收尾：默认一个 Luna High 实现、主代理独立审核。仅对齐开发/调度环境至官方 Python 3.12；不恢复 B/C、参赛模型 API 或官方判分。

- [x] E.1 Fetch the merged main, preserve existing changes, and create `codex/align-python312` before writing (base `925d34b`).
- [x] E.2 Pin the development image to Python 3.12, select the same minor version for the controller venv, and resolve/check both dependency locks inside Docker without unrelated upgrades.
- [x] E.3 Build the changed images with existing caches; verify actual interpreters, installed distributions, dependency consistency, offline project tests and production readiness/dry-run entry points. Default dev remains without a Docker socket.
- [x] E.4 Reuse an existing fixed official image and local resources for a fresh model-free A probe from the migrated controller. Do not rebuild/download official fixtures, handbooks or browser binaries; verify image identity, MCP response, cleanup and retained evidence.
- [x] E.5 Freeze the candidate, independently verify it, record one bounded review and the user's learning feedback, then push a base=main PR for user review/merge (PR #4 created; merge remains the user's decision). Do not treat the environment migration as a new Agent trial or official score.

最新取舍：本地官方评分暂缓，先做离线与无评分开发验证；缺 Anthropic 不阻塞全部开发。已核对的 cb CLI 未见直接跳过 judge 的开关，开发入口需实际验证。见 `docs/development-preparation-2026-10-21.md`。

执行顺序以 [分段交接包](handoff.md) 为准，不按编号误把付费兼容性验证提前到离线修复之前。D0 先完成包装、配置和离线证据；A 验证实际环境/工具与入口；B 验证候选模型往返；C 才做一次任务执行。每段交付稳定候选，由 Codex 验收，未授权阶段不自动启动。

2026-10-24 环境方式按用户要求改为 Docker 内开发；依赖安装、下载和测试均在容器执行，宿主机不配置项目环境。D0 可构建/启动开发容器，不启动官方任务世界。详见 [Docker 工作流](../../../docs/docker-workflow.md)。勾选仅表示所注明阶段的实现或证据，不能代替独立审核及未运行的真实阶段。

## A. Model-free official environment and read-only tools (verified 2026-10-25)

User authorization: stage A only; B/C, runtime model API calls and official grading remain paused. Base `d1c9f991eda9548974838f72578078f9f9b05757`, branch `codex/bootstrap-baseline-a`; preserve the pre-existing learning document changes. The D0 summary above records the previous stage.

- [x] A.1 Read current summaries, fetch origin, preserve the existing learning diff and create the work branch before writing.
- [x] A.2 Provision pinned official source, fixed task resources and a declared Python 3.12 task environment entirely inside Docker; record their actual identities.
- [x] A.3 Verify model-free startup and containerized scheduling, mount sources, service endpoints and isolated task state using the existing Docker engine.
- [x] A.4 Discover live role MCP schemas and call only individually audited, allowlisted read tools; retain local raw evidence and permitted report metadata.
- [x] A.5 Check rejection, failure/timeout reporting, resource ownership/cleanup and evidence persistence; retain B/C guards and run affected offline regressions. Normal cleanup was observed twice; abnormal branches use synthetic checks.
- [x] A.6 Stop implementation, fix a candidate, independently review/recheck it, update learning/status records and create a base=main PR for the user to review and merge (PR #2 created; user review/merge remains the user's decision).

Do not mark combined Agent execution tasks complete based on these stage A checks. OpenSpec CLI and other architectures require their own evidence.

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
- [x] 1.3 Fetch the official source into an ignored directory and pin its actual commit; inspect that version's installation, task and CLI contracts (A: 4444a07; official runtime/entrypoint and selected role MCP verified).
- [ ] 1.4 Record user-controlled prerequisites separately: registration, handbook approval and local credentials; do not claim they are complete without evidence.
- [ ] 1.5 Verify the candidate provider/model/API/mode through the selected harness, including consecutive tool exchanges and required history fields; record the actual effective profile before the task attempt.

## 2. Implement the bounded wrapper

- [x] 2.1 Add the minimal project manifest and configuration example required by the wrapper; use environment-variable references for secrets.
- [x] 2.2 Implement a no-model readiness command with clear missing-dependency/configuration output.
- [x] 2.3 Add a single-task baseline entry point with actual argv invocation, finite limits, isolated result directory and failure reporting.
- [x] 2.4 Produce a local manifest linked to real upstream results; preserve reward 0 and null verdicts, and retain unknown usage as null.
- [x] 2.5 Add focused offline checks for missing dependencies/configuration, command failure, timeout, missing verdict and fixture success; default checks require no network or API key.
- [x] 2.6 Verify a bounded ungraded entry point against the fixed upstream; report unsupported paths without inventing CLI flags or patching the official judge (D0: unverified ungraded real execution blocked before subprocess with unsupported reason; dry-run preview preserved).
- [x] 2.7 Implement D0 mode-specific readiness with one selection/evidence policy; distinguish configured local prerequisites from overall execution readiness. Ungraded real execution remains unsupported, with null reward and a blocked manifest; no real ungraded trace is claimed. Independent review follows the candidate.
- [x] 2.8 Implement the D0 offline cumulative-budget/next-request-reservation and round-limit decision; the production preflight stops on missing accounting evidence, and limits are forwarded via agent_kwargs. Actual per-request harness enforcement, measured usage and a clean real task attempt remain deferred to B/C, not completed by these offline checks.
- [x] 2.9 Provide the minimal development image, Compose entry points, dependency lock and controlled build context; run offline checks inside containers, persist source/results and keep secrets/restricted data out of the distributable image (D0: requirements.lock committed, Dockerfile uses pinned image & locked dependencies, socket mount removed).
- [x] 2.10 At stage A, verify task-container creation from the containerized scheduler using the existing engine, actual mount source paths, network endpoints, artifact persistence and cleanup; retain the official runtime contract (A: fresh-world independent verification; see stage A review).

## 3. Verify and hand over

- [x] 3.1 Run and record actual offline checks; provide diff, exact commands, exit codes and limitations.
- [ ] 3.2 Once implementation is resumed and prerequisites/budget are set, verify live tools and one real ungraded Agent execution; retain local evidence and do not claim official success.
- [ ] 3.3 Report measured duration and available usage/cost, failed stages and implications for the next change; identify unmeasured fields.
- [ ] 3.4 Codex independently reviews the code and applicable offline checks; user inspects the demonstrated result. D0 code review passed at b7f8941; the combined checkbox remains open because separate full user acceptance has not been recorded.
- [ ] 3.5 Deferred by user: run the original official verifier only if local grading is later requested with its prerequisites available; retain the verdict, scorecard and resource sources.
- [x] 3.6 Demonstrate the D0 development target's clean container startup without host project dependencies; record Python 3.13.17/aarch64, uv/lock and image identity. Official Python 3.12, other architectures and real task runtime remain unverified; no paid task was repeated.

Do not check 3.2 based on a dry run or fixture, or 3.5 based on ungraded execution. Do not mark Codex/user acceptance complete on their behalf. If access or the development entry point is unavailable, hand over completed work with the real-run prerequisite still open. Deferred grading stays explicit without blocking all other development.
