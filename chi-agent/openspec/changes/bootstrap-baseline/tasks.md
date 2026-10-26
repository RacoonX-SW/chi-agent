当前阶段、授权与已通过身份以 [REVIEW_STATE](../../../reviews/REVIEW_STATE.md) 为准。以下已勾选项保留其历史验收范围；旧双代理人数与开发版本不覆盖现行协作约定。

## C. Offline single-attempt lifecycle control

用户于 2026-10-26 恢复 C 代码开发；本轮先实现单题执行控制的离线部分，不恢复真实模型、官方任务试跑或判分，不代勾真实 C 的 3.2。一个 Luna High 实现，主代理独立审核。

- [x] C.1 Verify the user's merged B PR, fast-forward the untouched C branch to latest origin/main, and specify offline/live boundaries.
- [x] C.2 Implement a pure plan and an explicitly synthetic rehearsal controller, reusing the existing single-task builder and budget gate without modifying the real baseline guard.
- [x] C.3 Persist an exclusive attempt claim scoped by campaign/task/upstream, isolated from real attempts; prevent duplicate/concurrent replay and evidence overwrite.
- [x] C.4 Verify shared-budget provenance, one fresh-world/runner invocation, partial-failure/timeout/cleanup handling and retained null real outcomes in Docker (implementation self-test; independent acceptance follows C.5).
- [x] C.5 Freeze and independently verify the candidate, update the existing learning ledger and one phase report, then push a base=main PR for user review/merge. PR identity and next action are recorded only in REVIEW_STATE.

## B. Offline preparation of model/tool exchanges

用户于 2026-10-26 恢复 B 规格与离线实现，一个 `gpt-6-luna` / `high` 实现子代理，主代理独立审核。真实参赛模型 API、C 与官方判分继续暂停；本节不代勾 1.5 的真实 provider/harness 验证。

- [x] B.1 Verify PR #4 merged and create a B work branch from the latest `origin/main` before writing.
- [x] B.2 Specify offline-only transport, candidate profile, at least two synthetic tool exchanges, history preservation, budget gates, failure boundaries and reference-runner gaps.
- [x] B.3 Implement the bounded adapter and synthetic probe without a live transport, credentials, official world or relaxed production gate.
- [x] B.4 Self-test the production probe and affected regressions in the existing Python 3.12 Docker image with networking disabled; retain local evidence and distinguish synthetic usage from unmeasured provider usage.
- [x] B.5 Freeze the candidate; independently review/recheck normal, invalid-call, post-tool rejection, limits and unknown-usage paths; record one review and learning entry.
- [x] B.6 Push the bounded work branch and create a base=main PR for user review/merge; do not merge or enable a later stage. PR identity and next action are recorded only in REVIEW_STATE.

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

## Model/official runner integration code (offline only)

- [x] I.1 Add an optional, pinned SDK dependency layer in the existing Python 3.12 Docker; preserve the base environment and vendor source.
- [x] I.2 Separate route/client and wire body; verify actual SDK serialization and same-model/endpoint reasoning plus tool-result history through the fixed official loop.
- [x] I.3 Enforce per-request budget/input/output/round guards, account returned usage before validation, and verify zero HTTP/Agents/tool/outer retries including failure paths.
- [x] I.4 Prepare direct-runner ungraded plan/offline entries with synthetic tools/HTTP only, preserved evidence and live rejection; leave real B/C and grading paused.
- [x] I.5 Freeze implementation, independently review in Docker, record limitations in one stage report and create a base=main PR for user review/merge. PR identity and next action are recorded only in REVIEW_STATE; user merge remains separate.

## Real B run preparation (actual API calls paused)

- [x] P.1 Verify the merged integration PR and create a new branch from latest origin/main; freeze provider/profile/provenance and authorization boundaries.
- [x] P.2 Add a strictly validated, source-dated provider profile and read-only plan/preflight with real budget/auth readiness kept separate from execution authorization.
- [x] P.3 Prepare a reusable injected transport/accounting boundary with documented CNY reserve, prior spend and persistent synthetic pending/settled/unknown states; do not create a real ledger or send requests.
- [x] P.4 Rehearse the same boundary through the pinned real SDK/official loop in network-disabled Docker; preserve existing integration behavior and verify failure/restart/race/history/budget paths.
- [x] P.5 Freeze candidate, independently verify it, update the learning ledger and one stage report, then create a base=main PR for user review/merge. Actual B/C/grading remain paused; PR identity is recorded only in REVIEW_STATE, and user merge remains separate.

## F. Separate development budgets from official evaluation

正式提交前的必需前置；[行为契约](specs/benchmark-readiness/spec.md#requirement-separate-local-development-budgets-from-official-private-evaluation) 和 [设计依据](design.md#本地开发预算与正式私有评测) 区分本地首轮限额与正式冻结策略。F.2–F.4 的勾选只涵盖代码/离线策略演练，不替代 F.5 完整冻结或真实 API/C/判分；验收身份与报告只见 REVIEW_STATE。

- [x] F.1 Record the user's scope concern, official rule basis and the explicit boundary between local-development acceptance and final-evaluation readiness.
- [x] F.2 Separate usage/cost recording and monetary stop policy from the provider profile; preserve the local shared 5 CNY guard, and provide identified record_only/capped evaluation-policy rehearsals that do not inherit development balances/prior files or synthetic ledgers. Final submission freezing remains F.5.
- [x] F.3 Scope evaluation accounting/evidence by legitimate task/attempt identity; preserve uncertain/duplicate-attempt protection without allowing one trial's pending state to poison unrelated trials. Retain null unknown totals and existing request/history/tool/retry controls.
- [x] F.4 Independently verify production entry/configuration selection for offline rehearsals, sequential tasks, independent attempts, unknown-usage isolation and duplicate-attempt rejection in Docker with synthetic transports; rerun affected local-cap and protocol regressions.
- [ ] F.5 Before final submission, review the current organizer limits, freeze one evaluation policy for all private tasks and document the runnable entry/configuration; exclude local ledgers, credentials and protected materials from the package. Actual-run authorization remains separate.

## G. Dedicated evaluation entry and clean bundle (offline)

本轮针对“底层支持 record_only，但交付默认入口仍可能落回本地 5 元”的缺口。只完成专用入口与干净目录包的离线准备，不能代勾 F.5 完整正式冻结，也不恢复真实 API/C/判分。

- [x] G.1 Verify PR #10 merged, branch from latest origin/main, and specify the dedicated-entry/default-policy and clean-package boundaries.
- [x] G.2 Implement a dedicated plan/preflight/rehearse/live entry with default fixed evaluation record_only and null monetary cap, no development budget/scope/prior fallback, explicit trial identities/output root and earliest live refusal.
- [x] G.3 Export a fixed-allowlist directory bundle with strictly validated config/content manifest and runbook; exclude development policy/ledgers, credentials, vendor/data/handbook, tests and raw evidence. Bind verified entry/package identity to the evaluation registry; reject existing/unsafe destinations and retain incomplete builds without false completion.
- [x] G.4 In offline Docker, run the actual dedicated CLI from a read-only exported package at an unrelated cwd without the original repository mounted; verify multiple above-5-CNY synthetic trials, unknown/replay isolation, identity/config/file tampering, prohibited overrides, build failures, read-only modes and live refusal, with existing local regressions preserved.
- [x] G.5 Freeze the candidate, independently review/recheck it, record one phase report and learning entry, then create a base=main PR for user review/merge. This delivery is an identified offline package, not final submission or real execution acceptance.

## 3. Verify and hand over

- [x] 3.1 Run and record actual offline checks; provide diff, exact commands, exit codes and limitations.
- [ ] 3.2 Once implementation is resumed and prerequisites/budget are set, verify live tools and one real ungraded Agent execution; retain local evidence and do not claim official success.
- [ ] 3.3 Report measured duration and available usage/cost, failed stages and implications for the next change; identify unmeasured fields.
- [ ] 3.4 Codex independently reviews the code and applicable offline checks; user inspects the demonstrated result. D0 code review passed at b7f8941; the combined checkbox remains open because separate full user acceptance has not been recorded.
- [ ] 3.5 Deferred by user: run the original official verifier only if local grading is later requested with its prerequisites available; retain the verdict, scorecard and resource sources.
- [x] 3.6 Demonstrate the D0 development target's clean container startup without host project dependencies; record Python 3.13.17/aarch64, uv/lock and image identity. Official Python 3.12, other architectures and real task runtime remain unverified; no paid task was repeated.

Do not check 3.2 based on a dry run or fixture, or 3.5 based on ungraded execution. Do not mark Codex/user acceptance complete on their behalf. If access or the development entry point is unavailable, hand over completed work with the real-run prerequisite still open. Deferred grading stays explicit without blocking all other development.
