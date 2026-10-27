## ADDED Requirements

### Requirement: Containerized development and reproducible delivery

The workflow SHALL install project dependencies, download resources and execute project checks inside containers, without requiring project Python/uv/Node packages on the host. Containerized development SHALL preserve the official task runtime contract and separate distributable code images from restricted data.

#### Scenario: Align development and controller Python with the pinned official runtime

- **GIVEN** the pinned official task runtime uses Python 3.12 and the environment alignment is authorized
- **WHEN** the development and controller images are rebuilt
- **THEN** their actual interpreters and controller venv use Python 3.12 and their locked dependencies pass consistency and affected offline checks
- **AND** an existing official image and local resources are reused for a fresh model-free read probe, with cleanup and retained evidence verified
- **AND** official resource/browser downloads, model calls, Agent trials and grading are not performed by this migration

#### Scenario: The host has Docker but no project runtime packages

- **GIVEN** Docker is available on the host and the development image's inputs and dependencies are declared
- **WHEN** D0 is resumed and the image is built for offline checks
- **THEN** installation and checks execute inside the development container
- **AND** host Python/uv/Node project package installation is not a prerequisite
- **AND** no runtime model request or official task world is started by the offline check

#### Scenario: A containerized scheduler starts an official task

- **GIVEN** stage A or a later stage is authorized and the scheduler uses the existing Docker engine
- **WHEN** it resolves task mounts and service endpoints
- **THEN** source paths are verified from the engine's filesystem context and endpoints from the caller's network context
- **AND** invalid or inaccessible paths stop execution before a paid task attempt
- **AND** the fixed official task runtime and Agent/verifier resource boundary are preserved

#### Scenario: A development or task container is recreated

- **GIVEN** source code and retained evidence use declared persistent storage
- **WHEN** a container is removed or recreated under the workflow
- **THEN** the retained source and evidence remain accessible in their declared locations
- **AND** the project environment is not silently replaced by a host environment or an obscuring source mount

#### Scenario: A distributable image is prepared

- **GIVEN** official runtime build inputs can include protected handbook content
- **WHEN** the project's distributable code image is built or exported
- **THEN** its build context and retained layers exclude credentials and restricted content
- **AND** authorized runtime resources and their provisioning instructions are declared separately
- **AND** clean startup uses recorded dependencies and image identity rather than undeclared development-container installations

### Requirement: Distinguish documented and observed task contracts

The baseline report SHALL distinguish official static inputs and tool references from live MCP contracts, actual execution traces and official verdicts.

#### Scenario: Only the public task documents have been inspected

- **GIVEN** the task instruction, tool reference and setup configuration have been read
- **WHEN** the task analysis is delivered before a real trial
- **THEN** tool names and limits are attributed to their fixed source versions
- **AND** unobserved live schemas, execution steps and official reward are explicitly unverified
- **AND** no illustrative workflow is presented as a real trajectory

### Requirement: Bounded model-free stage A tool integration

Stage A SHALL provision the fixed official task environment and observe real MCP exchanges without starting an Agent runner, invoking a model or running an official verifier. The stage SHALL use the selected public task and record environment/data identity separately from task completion.

#### Scenario: Stage A is resumed while B and C remain paused

- **GIVEN** only official environment and model-free read-only tool integration are authorized
- **WHEN** the scheduler prepares or starts the selected task world
- **THEN** installation, downloads, debugging and checks execute inside Docker
- **AND** startup hooks and selected tool handlers are checked against the pinned official source before execution
- **AND** no model/judge credentials are forwarded and no runner, simulated model conversation or verifier is invoked
- **AND** runtime model usage and official reward remain unmeasured/null rather than inferred from tool success

#### Scenario: A script probes a live role tool

- **GIVEN** the official service is running in an isolated development world
- **WHEN** the script initializes an MCP session, discovers live tools and performs a query
- **THEN** the called tool is both present in the live schema and individually allowlisted after checking its handler for model calls and business writes
- **AND** unknown tools, missing or incompatible schemas and prohibited calls stop before tool execution
- **AND** arguments derive only from public Agent input or schema-valid general queries
- **AND** raw schemas and responses stay in ignored local evidence, while shared reports contain only permitted metadata
- **AND** the report identifies the script as caller and does not claim model selection or autonomous task execution

#### Scenario: An environment or probe fails

- **GIVEN** task resources are created with a unique stage A identity
- **WHEN** startup, a query or a bounded wait fails or times out
- **THEN** evidence records the failing stage without inventing a tool result or official verdict
- **AND** cleanup targets only resources owned by this run and retained evidence survives removal
- **AND** the next task attempt uses a fresh world rather than reusing this development state

### Requirement: Explicit readiness status

The system SHALL report dependency and configuration readiness without invoking a model by default.

#### Scenario: A required dependency is missing

- **GIVEN** a required runtime or Docker service is unavailable
- **WHEN** the readiness check runs
- **THEN** it reports the missing dependency and a non-ready result
- **AND** it makes no model API call and reports no baseline success

#### Scenario: Credential configuration is present

- **GIVEN** credential environment variables are set
- **WHEN** the readiness check inspects configuration
- **THEN** it reports presence without exposing values
- **AND** it distinguishes configuration presence from proven service or handbook access

### Requirement: Authorized single-task baseline

The system SHALL require necessary access and explicit run configuration before executing one official public task using an upstream agent.

#### Scenario: Handbook access has not been obtained

- **GIVEN** necessary handbook access is not available
- **WHEN** a real baseline run is requested
- **THEN** the run is reported as blocked by access
- **AND** no fabricated official score is produced

#### Scenario: The run has fixed configuration

- **GIVEN** access, a fixed upstream version, task, harness, model and finite execution limits
- **WHEN** a real baseline is started
- **THEN** it executes only the configured public task
- **AND** it retains the actual command, version identities, exit status and local evidence paths

#### Scenario: A configuration would run more than the selected task

- **GIVEN** the requested baseline is one configured public task
- **WHEN** the selected official entry point or effective configuration resolves to a whole domain, multiple tasks or multiple attempts
- **THEN** the bounded baseline is not started under a one-task claim
- **AND** the mismatch is reported before any paid execution

### Requirement: Separate development execution from official grading

The system SHALL distinguish offline readiness, live tool integration, ungraded Agent execution and officially scored evaluation. Deferring the official judge SHALL NOT imply that all development checks require judge credentials.

#### Scenario: The user defers local official grading

- **GIVEN** Agent development is planned without an Anthropic judge credential
- **WHEN** readiness is reported
- **THEN** offline and tool integration prerequisites are reported separately from grading prerequisites
- **AND** model-backed simulator dependencies are identified separately
- **AND** the report does not claim a real run merely because configuration is present

#### Scenario: An ungraded development execution is supported

- **GIVEN** a verified development entry point, permitted role tools, required access and bounded authorized model usage
- **WHEN** one Agent execution runs without the official verifier
- **THEN** actual commands, tool interactions, errors, stop reason and available resource use are retained
- **AND** official reward is null with grading explicitly not run
- **AND** no synthetic scorecard or official pass rate is produced

#### Scenario: The requested development entry point is unsupported

- **GIVEN** the fixed upstream version has no verified way to execute the requested ungraded path
- **WHEN** development execution is requested
- **THEN** the unsupported entry point is reported before paid execution
- **AND** the wrapper does not invent upstream CLI options or modify the official grader to claim success

#### Scenario: Official grading is requested without required credentials

- **GIVEN** the run explicitly requests the official verifier but its required access is missing
- **WHEN** the wrapper checks prerequisites
- **THEN** that scored mode is reported unavailable before starting paid execution
- **AND** it does not silently substitute a different judge or label an ungraded run as scored

### Requirement: Verify the selected provider through full tool exchanges

The system SHALL distinguish basic model connectivity from verified multi-turn tool use through the selected harness, API and explicit model mode.

#### Scenario: Chat works but the selected tool-calling mode fails

- **GIVEN** a provider returns a normal chat response
- **WHEN** a subsequent tool exchange fails in the selected runner or required history fields are not preserved
- **THEN** the selected tool integration remains unverified
- **AND** a different API or thinking mode is recorded as a separate configuration rather than silently substituted

#### Scenario: Synthetic tool integration succeeds

- **GIVEN** the selected profile completes consecutive tool exchanges using synthetic inputs
- **WHEN** the integration report is written
- **THEN** actual settings, call/result associations and available usage are retained
- **AND** the report does not label synthetic interactions as an official medical-task execution
- **AND** the task attempt starts from an independent clean world rather than a debug-modified environment

#### Scenario: A tool executes before the next model request is rejected

- **GIVEN** a tool has executed and the next model API request containing its result is rejected
- **WHEN** the failed integration is reported
- **THEN** the observed tool execution/effect and subsequent model API error are recorded separately
- **AND** the complete model-tool loop is not reported as verified
- **AND** the wrapper does not replay an executed business write solely to recover from that model request rejection

### Requirement: Offline-only preparation for stage B

The system SHALL provide a bounded synthetic Chat Completions probe while real model API calls, stage C and official grading remain paused. Offline results SHALL NOT establish provider or reference-runner compatibility.

#### Scenario: B specifications and offline implementation are resumed

- **GIVEN** only offline B preparation is authorized
- **WHEN** the production B probe runs in the existing Python 3.12 development container
- **THEN** it uses only synthetic responses and allowlisted synthetic tools, with network disabled and without credentials, a Docker socket or official task resources
- **AND** no live HTTP/SDK transport is installed or selected, a live-mode request is refused, and the original task entry-point guards remain in place
- **AND** its local evidence declares offline/synthetic provenance, unverified provider/harness integration, null real usage/cost and null official reward

#### Scenario: Two consecutive synthetic tool exchanges complete

- **GIVEN** an explicit candidate model, endpoint, API, thinking mode, effort and finite request/round limits
- **WHEN** the probe receives two successive tool-call responses followed by a final assistant response
- **THEN** every captured request contains the intended profile and finite output limit
- **AND** subsequent histories retain assistant content, opaque reasoning fields and original tool-call IDs/arguments, followed by results matched through `tool_call_id`
- **AND** the result is called an offline synthetic completion, without claiming a real model chose the tools or the official runner executed them
- **AND** absent/null/empty `tool_calls` are handled as a final-message shape; completion additionally requires at least two separate successful tool-exchange rounds, usable final content and a normal `stop` finish reason

#### Scenario: A response ends early or is truncated

- **GIVEN** fewer than two completed tool-exchange rounds, a truncated/filtered response or an inconsistent finish reason
- **WHEN** the probe considers its terminal result
- **THEN** it records an incomplete/rejected outcome and preserves prior effects rather than reporting synthetic completion

#### Scenario: A response contains an invalid tool batch

- **GIVEN** an unknown tool, unsupported call type, malformed/invalid arguments, missing reasoning history or duplicate/invalid call ID
- **WHEN** the response is validated
- **THEN** the entire batch is rejected before any of its tool calls execute
- **AND** evidence identifies the invalid response without inventing effects or continuing with a substituted mode

#### Scenario: A later request fails after a tool executes

- **GIVEN** a synthetic tool has executed and its result is recorded
- **WHEN** the next injected model transport rejects, errors or times out
- **THEN** the executed tool/result and later transport failure are recorded separately
- **AND** the probe stops without automatic retries or replay, retains evidence and does not report full-loop completion

#### Scenario: Request budget or limits cannot be established

- **GIVEN** each next request requires cumulative usage/cost, versioned prices and conversion evidence plus finite input/output/round limits
- **WHEN** usage is missing/invalid, a bound is exceeded, a limit is exhausted or the next reserve cannot fit
- **THEN** the probe stops before the next injected transport call, never treating unknown usage as zero
- **AND** synthetic accounting remains separate from real provider usage and the shared B/C runtime budget
- **AND** missing/invalid usage on the final response also prevents completion; unknown aggregate usage/cost is null, with any known prefix totals explicitly labeled incomplete
- **AND** valid usage from a returned request is accounted even when message/tool validation later rejects that response, and synthetic cap, price and conversion values/sources are retained for recomputation
- **AND** round/input/output limits require positive non-boolean integers within their hard ceilings, with malformed configuration rejected before transport

#### Scenario: Evidence is written or an output identity already exists

- **GIVEN** a run identity and local output path
- **WHEN** a probe completes or fails
- **THEN** its candidate settings, requests/results, terminal state and failure phase remain readable after the container exits
- **AND** a duplicate or unsafe run identity cannot overwrite existing evidence
- **AND** raw local evidence remains in ignored paths and diagnostics do not emit credentials or arbitrary exception payloads

### Requirement: Offline validation of the model and official runner integration layer

The integration SHALL use the pinned real SDK and official runner with synthetic network/tool boundaries. Developing this layer SHALL NOT authorize real model requests, a stage C attempt or official grading.

#### Scenario: An actual SDK request is serialized

- **GIVEN** the pinned SDK packages, fixed official runner and an explicit candidate route
- **WHEN** the real SDK sends into an injected mock HTTP transport
- **THEN** the URL/client configuration is separate from the JSON body, with finite generation limits and explicit thinking/effort settings
- **AND** no endpoint, API label or secret is sent as an application JSON field; client and Agents retries are zero and tracing is disabled
- **AND** actual serialized requests, package/source identities and synthetic provenance are retained locally

#### Scenario: The official loop performs consecutive synthetic tool exchanges

- **GIVEN** an unmodified fixed official runner with synthetic MCP/local tools and mock model responses
- **WHEN** two separate tool rounds and a normal final response occur
- **THEN** later HTTP bodies preserve the original assistant content, opaque reasoning, original call IDs/arguments and paired tool results
- **AND** reasoning replay is scoped to the same exact model and endpoint
- **AND** invalid tools/arguments, missing history, duplicate IDs or invalid finish reasons reject the entire response before its tools execute
- **AND** the thinking profile requires a string reasoning field on every assistant response, including the final response; legal empty strings remain valid, call IDs have a bounded safe shape, and not-found tool results still consume and record their original calls
- **AND** the report distinguishes official-loop execution with synthetic boundaries from a real provider decision or medical-task execution

#### Scenario: A serialized next request cannot fit its budget

- **GIVEN** a shared cap including prior spend, finite request/round limits and identified accounting inputs
- **WHEN** any actual next HTTP request exceeds a bound, exhausts rounds or lacks a valid reserve/accounting basis
- **THEN** the request is blocked before the injected transport is invoked
- **AND** returned usage is accounted before message validation, unknown aggregate usage/cost is null and known prefixes remain explicitly incomplete
- **AND** an already-incomplete ledger itself blocks the next transport boundary, and evidence retains the synthetic price/conversion/source inputs needed to recompute its costs
- **AND** missing/invalid final usage and returned over-limit usage cannot produce completion
- **AND** local byte estimates and synthetic prices are not represented as verified provider token bounds or billing caps

#### Scenario: A later transport fails after a tool effect

- **GIVEN** a synthetic tool effect has already occurred
- **WHEN** HTTP rejects, times out, fails to connect or returns an invalid response
- **THEN** the loop stops with no SDK/client/tool/outer automatic replay and preserves the prior effect separately from the later error
- **AND** retryable HTTP responses and connection/timeouts are exercised against the real SDK to verify actual send counts

#### Scenario: The direct ungraded entry is selected

- **GIVEN** the fixed runner's direct run_agent entry rather than the experiment/verifier path
- **WHEN** offline integration is executed
- **THEN** no judge, task world, shell/file tool, credentials or real MCP endpoint is used
- **AND** official reward, real usage/cost and task outcome remain null/unknown
- **AND** live mode is rejected before external effects or a real attempt claim, while existing B/C/baseline gates remain effective
- **AND** output identities are exclusive, failures retain safe evidence, and temporary runner/environment changes are restored
- **AND** invalid/existing output identities are rejected atomically before runner/tool effects, and setup/constructor failures restore temporary SDK patches as well as execution failures

### Requirement: Prepare a real stage B run without enabling API calls

The preparation SHALL provide an identified provider profile, reusable guarded transport, explicit accounting evidence and read-only preflight. All checks and rehearsals SHALL run without provider credentials, network requests, an official task world or grading; preparation SHALL NOT resume real execution.

#### Scenario: A profile is inspected before any request

- **GIVEN** a candidate provider/model/API/mode and finite request limits
- **WHEN** plan or preflight runs
- **THEN** route and wire settings, source/version/date, SDK/source identity, budget evidence and active execution pause are reported separately
- **AND** no files, production ledger, attempt claim, HTTP client/transport or credentials are created/read by these read-only entries
- **AND** absent authentication remains unverified rather than being inferred from configuration; live mode is refused before any such boundary regardless of flags or file claims

#### Scenario: Pricing and input reservation have documented provenance

- **GIVEN** a profile with current official CNY peak/cache-miss upper prices and documented model context ceiling
- **WHEN** the next request is evaluated
- **THEN** finite arithmetic includes prior B/C spend and full request reserve, with CNY units and sources retained
- **AND** absent/stale/untrusted provenance, unsafe numeric types, arbitrary reduced input ceilings or mismatched profile/accounting scope fail closed
- **AND** documentation-based ceilings and upper cost estimates are distinguished from measured provider tokens and billed costs

#### Scenario: The same guard runs through the pinned official loop

- **GIVEN** an injected mock lower transport, fixed real SDK/official runner and synthetic tools
- **WHEN** a rehearsal performs multiple tool exchanges
- **THEN** the generic boundary checks each actual serialized request before lower transport, accounts returned usage before protocol/tool validation and preserves the original history/IDs
- **AND** HTTP/Agents/tool/outer retries remain zero, all temporary SDK/environment changes are restored, and prior effects survive later failures
- **AND** invalid or final missing usage, schema/model/history errors, over-limit results and insufficient next reserve prevent completion or another send
- **AND** raw responses and evidence never disclose credentials or arbitrary exception payloads

#### Scenario: A request reservation is interrupted or uncertain

- **GIVEN** a persistent rehearsal ledger in an explicitly synthetic namespace and known prior costs
- **WHEN** a request is reserved before send and then times out, returns unknown usage or the process exits
- **THEN** restart or a different run-id cannot erase the pending state, reset prior spend or automatically replay the request
- **AND** concurrent processes cannot both spend the same reservation, persistence failure blocks the lower boundary, and known-prefix/aggregate/upper-cost meanings remain distinct
- **AND** rehearsals do not initialize or consume a real B/C budget namespace, and production missing/synthetic budget evidence is not treated as known real zero

### Requirement: Offline stage C single-attempt execution control

The system SHALL prepare stage C lifecycle and single-attempt control without enabling model API calls, an official task attempt or grading. An offline rehearsal SHALL exercise control boundaries only; it SHALL NOT satisfy the real stage C execution scenario.

#### Scenario: C code development is resumed while real execution stays paused

- **GIVEN** only C code and offline verification are authorized
- **WHEN** the C CLI is used
- **THEN** `plan` validates and previews without filesystem mutations or backend calls
- **AND** `rehearse` uses an explicitly synthetic, pure-Python backend with no network, Docker API, MCP, credentials or official task resources
- **AND** `live` is refused before an attempt claim or backend call, without weakening the existing baseline gate
- **AND** the manifest labels candidate settings as configured/unverified, real usage/cost/reward as null and official task success as unknown
- **AND** CLI exit zero is limited to a valid plan or completed rehearsal; blocked/conflicting/failed rehearsals exit one, while invalid input and live refusal exit two

#### Scenario: One campaign is invoked using different run identities

- **GIVEN** a campaign, selected task and fixed upstream identity in the synthetic namespace
- **WHEN** a rehearsal passes preflight and is about to start an external boundary
- **THEN** a persistent attempt claim is acquired by atomic exclusive creation before that boundary
- **AND** another run-id or concurrent process in the same scope cannot start a second attempt
- **AND** existing, incomplete or malformed claims fail closed; claims are not deleted or expired after success, failure, timeout or uncertain termination
- **AND** synthetic claims never occupy or modify a real stage C attempt namespace

#### Scenario: The plan or evidence identity is invalid

- **GIVEN** malformed identifiers, non-integer/bool limits, more than one task/attempt/concurrent run, retries or an existing output directory
- **WHEN** preflight or output allocation occurs
- **THEN** the controller rejects the request before backend calls and preserves existing evidence
- **AND** preflight-blocked plans do not consume an attempt
- **AND** the candidate configuration reuses the existing single-task builder without inventing an upstream skip-grading option

#### Scenario: Shared B and C budget evidence is incomplete

- **GIVEN** one shared cap, prior B spend, input/output reservation limits and identified pricing/conversion evidence
- **WHEN** the controller checks entry to the attempted run
- **THEN** it reuses the existing budget decision with B spend included rather than resetting the cap for C
- **AND** missing/invalid spend, usage, pricing or conversion stops the relevant next boundary and is not treated as zero
- **AND** spend/pricing/conversion source identifiers are non-empty, non-whitespace strings; a returned total exceeding the shared cap is recorded as exceeded rather than rehearsal completion
- **AND** synthetic amounts and sources remain separate from real B/C accounting, with any unknown totals null
- **AND** entry-level checks and requested model limits are not reported as verified per-request enforcement inside the official runner

#### Scenario: Rehearsal provisions a fresh world and runs once

- **GIVEN** valid synthetic inputs and an acquired claim
- **WHEN** the injected backend is invoked
- **THEN** the order is fresh-world creation, one runner invocation and finally cleanup of confirmed owned resources
- **AND** primary failure, timeout and cleanup failure are recorded separately without automatic retries or replay
- **AND** a partial-creation failure can provide an explicit owned cleanup handle; missing or foreign handles are not guessed or deleted
- **AND** evidence and claim remain readable after cleanup; only allowlisted metadata and fixed error classifications are persisted
- **AND** confirmed ownership includes valid handle shape and the current run/campaign/namespace identity, including on partial creation; malformed handles yield a controlled terminal result without cleanup of unknown resources
- **AND** evidence-write failure after resource creation does not prevent attempted cleanup; persistence errors are separate from primary and cleanup errors, retained claims prevent replay, and incomplete evidence is never reported as complete

#### Scenario: The runner returns or a limit is reached

- **GIVEN** a synthetic result or injected timeout
- **WHEN** the controller records its terminal state
- **THEN** exit zero represents at most rehearsal completion, never official task success
- **AND** bad/missing usage or invalid results cannot produce a successful rehearsal accounting record
- **AND** task time and model limits are passed as candidate constraints, with real blocking-call cancellation, request hooks and actual official environment integration explicitly unverified

### Requirement: Respect the selected first-round runtime budget

The system SHALL account for the selected 5 CNY first-round local-development runtime budget across integration checks and the one task attempt, separately from coding costs. This cap SHALL NOT be treated as an organizer-required private-evaluation limit. A budget plan SHALL NOT lift an active implementation or paid-run pause.

#### Scenario: The user selects a budget while paid execution is paused

- **GIVEN** the 5 CNY runtime budget has been selected for planning
- **WHEN** the plan or configuration is updated without a subsequent instruction resuming execution
- **THEN** no model request or task attempt is started

#### Scenario: A further request cannot fit the remaining planned budget

- **GIVEN** resumed execution with cumulative usage, finite generation limits and versioned pricing
- **WHEN** the next request cannot conservatively fit the remaining budget, or missing usage prevents a trustworthy check
- **THEN** the run stops with a budget or accounting reason and preserves available evidence
- **AND** it does not count unknown usage as zero or automatically rerun the whole task
- **AND** an unfinished task is not reported as completed and local estimates are not presented as an exact provider billing cap

### Requirement: Separate local development budgets from official private evaluation

The system SHALL separate usage/cost recording from monetary stop policy and identify the execution scope explicitly. Offline policy-rehearsal acceptance SHALL NOT establish final submission freezing or real private-evaluation readiness. The rule basis and design are recorded in [the budget-policy design](../../design.md#本地开发预算与正式私有评测).

#### Scenario: Local development uses the selected shared cap

- **GIVEN** the first local B/C development run is selected
- **WHEN** another model request is considered
- **THEN** prior spend, settled cost and the next conservative reserve remain subject to the shared 5 CNY cap
- **AND** restart or a different run-id cannot clear pending/unknown spend, increase the cap or authorize replay

#### Scenario: A frozen official-evaluation profile is selected

- **GIVEN** a separately identified official-evaluation profile consistent with the organizer's rules and resource limits
- **WHEN** a legitimate private trial starts
- **THEN** it does not inherit the local 5 CNY cap, development prior file, local balance or synthetic/shared B/C ledger
- **AND** monetary stops apply only when explicitly specified by that frozen evaluation policy; otherwise accounting can record usage/cost without a development-currency hard stop
- **AND** request/history/tool validation, effects evidence and retry controls remain active, and the same frozen policy applies across private tasks
- **AND** documenting or selecting a policy does not lift the current live-execution pause

#### Scenario: One trial has uncertain usage while another is independent

- **GIVEN** two legitimate independent task/attempt identities and one frozen evaluation policy
- **WHEN** the first trial has spent money, times out or retains pending/unknown usage
- **THEN** its evidence and attempt identity remain intact without silently zeroing usage or replaying it
- **AND** the unrelated trial is not blocked by the first trial's local-development ledger or pending state
- **AND** unknown totals remain null with known prefixes separate, and the affected trial follows the frozen failure policy

#### Scenario: The package is checked before final submission

- **GIVEN** the final runnable package and explicit evaluation entry/configuration
- **WHEN** pre-submission acceptance runs in Docker with synthetic transports and isolated trial identities
- **THEN** sequential tasks and independent attempts demonstrate policy/state isolation, including an unknown-usage first trial
- **AND** duplicate invocation of the same attempt cannot overwrite evidence or automatically replay a request
- **AND** local-development cap regressions and shared request/history/retry validation still pass
- **AND** the frozen policy and reproduction instructions are included without development ledgers, credentials or protected artifacts

### Requirement: Dedicated evaluation delivery entry without development fallback

The delivery SHALL provide one explicit evaluation entry and a clean, identified offline directory bundle. Its default accounting policy SHALL be evaluation record_only with no monetary cap, while protocol/model limits and attempt safeguards remain active. This requirement SHALL NOT authorize actual model calls or establish final-system freeze/readiness.

#### Scenario: The dedicated entry is selected without budget flags

- **GIVEN** the candidate entry and its strictly validated configuration
- **WHEN** it inspects or rehearses an evaluation trial
- **THEN** it selects record_only with a null monetary cap without requiring a policy-selection flag
- **AND** development policy, balance/prior files, working-directory contents and budget environment variables cannot cause fallback to the local 5 CNY policy
- **AND** prohibited scope/cap/prior overrides fail explicitly; model/round/output/history/usage/tool/retry safeguards remain effective
- **AND** plan/preflight are read-only and report package/configuration, SDK/source, authentication and active execution pause separately
- **AND** successful preflight requires verified package/configuration and available pinned SDK/source identity; missing dependencies return a controlled nonzero technical-readiness result without granting execution permission
- **AND** live is refused before configuration, manifest, identity, credentials, client or output/claim access

#### Scenario: The program is exported for independent reproduction

- **GIVEN** the explicitly allowlisted participant-owned files, provider/entry configuration, model dependency lock/install script and runbook
- **WHEN** an offline bundle is built
- **THEN** only those files and an identified content manifest are exported into an exclusively acquired destination
- **AND** local-development policy, ledgers/runs, credentials, vendor checkout, data, protected handbook, tests and raw evidence are excluded without recursively copying the repository
- **AND** symlink/traversal/invalid destinations and source aliases are rejected before unsafe reads/writes, an existing destination is preserved, and partial failure cannot produce a complete bundle
- **AND** manifest parsing uses fixed allowed paths, rejects duplicate/unknown/malformed entries and never supplies arbitrary paths to read
- **AND** content hashes identify the candidate package without being represented as a signature or execution permission

#### Scenario: The clean package starts from an unrelated directory

- **GIVEN** only the exported package mounted read-only, fixed SDK/vendor as separate read-only dependencies and an independent writable output root
- **WHEN** its actual default evaluation CLI rehearses multiple legitimate task/attempt identities from an unrelated cwd
- **THEN** each legal above-5-CNY synthetic chain can complete without loading the development policy or original repository
- **AND** unknown usage affects its own trial while unrelated legitimate trials remain runnable, and changing run-id cannot replay an occupied attempt
- **AND** the evaluation registry binds verified entry/configuration/package identity as well as policy/profile; changing the package cannot silently continue the same evaluation
- **AND** all usage/cost/reward claims remain synthetic/unknown as appropriate, with no real task world, credentials, external model or judge invoked

### Requirement: Official launch contract through the guarded offline runner

The evaluation entry SHALL accept the pinned runner's instruction-file, MCP URL and logs-directory contract without bypassing the existing record_only policy, attempt claims, protocol guards or actual-execution pause. The offline launch SHALL use the real pinned SDK/official loop with synthetic HTTP, MCP and local-tool boundaries only.

#### Scenario: External task input reaches the official loop

- **GIVEN** a clean package, independently mounted fixed vendor/locked SDK, a bounded UTF-8 instruction file and a valid streamable-http MCP URL
- **WHEN** the actual evaluation CLI rehearses the launch from an unrelated cwd
- **THEN** that instruction and URL reach the official run_agent call, and the captured serialized model input contains that instruction
- **AND** no MCP/model network connection, protected fixture, credential or verifier is used
- **AND** uniquely reserved external logs retain run_result.json, available run_output.txt/trace.jsonl and run_log.txt, with synthetic provenance and null real usage/cost/reward

#### Scenario: Invalid input, failure or repeated attempt

- **GIVEN** missing/oversized/invalid-encoding/nonregular/unsafe input, an invalid URL, overlapping logs, an existing log destination or an occupied task/attempt
- **WHEN** launch is requested
- **THEN** it is rejected without overwriting input/package/evidence or replaying the occupied attempt
- **AND** a failure after reservation retains its evidence and claim; missing runner artifacts cannot be reported as successful launch
- **AND** live still refuses before input/configuration/credential/client/claim access, regardless of provided launch arguments

#### Scenario: Independent dependency installation and isolated startup

- **GIVEN** a newly created empty Docker dependency volume and the unchanged hashed model lock/installer from the clean package
- **WHEN** dependencies are installed inside the existing Python 3.12 Docker environment and the package is then launched offline without the original repository or installed SDK layer mounted
- **THEN** the actual installation, versions, consistency check, instruction/URL flow, retained artifacts and failure boundaries are recorded independently
- **AND** record_only/null cap and local shared 5 CNY behavior are preserved
- **AND** this evidence is reported as offline installation/startup reproduction, leaving F.5, real API/C and official grading unverified

### Requirement: Bounded real development model and official task runs

The system SHALL provide a separate local real-development entry for explicitly authorized real B and one conditional ungraded C, sharing one persistent 5 CNY campaign. Existing evaluation-package defaults and paused legacy live entries SHALL remain unchanged. Real model execution SHALL follow fixed-candidate independent offline acceptance; official grading SHALL remain disabled.

#### Scenario: Real provider smoke with dependent tool exchanges

- **GIVEN** explicit user authorization, a trusted fixed source/SDK/profile, valid credentials and a known real prior with provenance
- **WHEN** the local B smoke runs against the documented provider endpoint
- **THEN** the real model chooses tools and receives at least two dependent tool results before a nonempty final response can establish B success
- **AND** the actual serialized history, call IDs, reasoning fields, provider usage and estimated CNY costs are retained with provenance; estimates are not presented as billed costs
- **AND** a missing credential, unsupported metadata/model, malformed batch, timeout or unknown usage stops the run without silently retrying or creating a C world

#### Scenario: Persistent shared budget and one C attempt

- **GIVEN** the fixed first B/C campaign and explicitly initialized prior evidence
- **WHEN** any B/C model request is about to be sent
- **THEN** a conservative next-request reservation is durably recorded before transport, and returned usage is accounted before tools execute
- **AND** B and C share cumulative spend; pending/unknown state survives restart, and run-id/log-output changes cannot create a fresh budget or erase a C claim
- **AND** a changed source/SDK/profile, inconsistent state or insufficient known budget blocks rather than reinitializes execution

#### Scenario: Autonomous fresh-world ungraded C

- **GIVEN** a successful real B under matching source/profile/SDK and sufficient known remaining budget
- **WHEN** C is requested for the fixed selected provider task
- **THEN** a single durable claim is acquired before creating a new official world, and its runner starts at most once
- **AND** the model autonomously uses official MCP tools through the pinned official loop with finite turns/output and zero automatic model, HTTP, tool or outer retries
- **AND** actual task instruction and authorized resources are supplied without verifier-only content; official reward remains null and no judge is called
- **AND** runner artifacts, primary errors, pending accounting and separate cleanup errors survive success, partial creation, timeout or failure

#### Scenario: Agent-visible resources remain isolated

- **GIVEN** controller access to Docker and runner access to provider credentials
- **WHEN** model tools obtain file or business data
- **THEN** the runner is isolated from the controller socket and original project, and its local tools are confined to explicitly projected instruction/tool-reference/handbook and run scratch resources
- **AND** arbitrary shell/Python, environment files, credentials, code/vendor internals and hidden scoring fixtures are not model-visible
- **AND** only owned world/runner/network resources are cleaned up, without adding credentials or external access to the official world

### Requirement: Preserve official outcomes

The system SHALL preserve official verifier outcomes and distinguish process failures from scored task failures.

#### Scenario: An official task receives zero reward

- **GIVEN** a completed official evaluation with reward 0
- **WHEN** results are collected
- **THEN** reward remains 0 and the run is recorded as a completed evaluation
- **AND** the report does not describe the task as solved

#### Scenario: The process fails before a valid verdict

- **GIVEN** the process fails, times out or produces no valid official verdict
- **WHEN** results are collected
- **THEN** the actual failure is retained and reward is null
- **AND** the result is not converted into a successful evaluation

### Requirement: Traceable resource records

The system SHALL record measured resource use with provenance and represent unavailable measurements explicitly.

#### Scenario: Provider usage or pricing is unavailable

- **GIVEN** trustworthy token usage or cost is unavailable
- **WHEN** the manifest is written
- **THEN** unavailable values are null with a reason or source field
- **AND** no estimated value is presented as measured use

### Requirement: Local evidence and disclosure boundaries

The system SHALL keep credentials and restricted materials out of public deliverables and preserve the official separation between agent-visible context and verifier-only evidence.

#### Scenario: An agent is running

- **GIVEN** an official benchmark task is in progress
- **WHEN** the agent obtains context
- **THEN** it uses only authorized task and role resources
- **AND** hidden expectations and verifier-only evidence are not supplied to it

#### Scenario: Public metadata contains evaluation targets

- **GIVEN** a public index contains expected task statuses or other evaluation-only fields
- **WHEN** the Agent input or retrieval context is prepared
- **THEN** that index is excluded from runtime task context
- **AND** task-specific answers and expected outputs are not used to route the Agent

#### Scenario: Preparing a shareable report

- **GIVEN** a run directory contains raw traces, handbook-related content or credentials
- **WHEN** preparing a shareable report
- **THEN** credentials and restricted content are excluded
- **AND** output disclosure follows the actual license or organizer authorization

### Requirement: Honest implementation and verification status

The delivery SHALL distinguish offline checks, simulated outcomes, real baseline evidence and user acceptance.

#### Scenario: Only offline tests have passed

- **GIVEN** packaging tests pass but no real task has run
- **WHEN** the implementation is handed over
- **THEN** the report identifies offline verification as passed and real baseline as unverified
- **AND** task completion checkboxes do not claim a real run

### Requirement: Stage-specific stable handover

The delivery SHALL identify the requested stage, stable candidate and actual evidence. An implementation-ready signal SHALL NOT imply independent review or user acceptance, and a narrow implementation resume SHALL NOT activate later stages.

#### Scenario: Only offline repair is resumed

- **GIVEN** the user resumes D0 offline repair only
- **WHEN** the executor implements and hands over that stage
- **THEN** it does not start the task environment, a runtime model request or a task attempt
- **AND** live tools, model integration and task execution remain explicitly unverified

#### Scenario: The candidate includes uncommitted changes

- **GIVEN** the delivered implementation has not been committed or includes changes beyond HEAD
- **WHEN** its identity is recorded
- **THEN** a reviewable patch or equivalent file fingerprint set identifies the implementation changes in addition to the base commit
- **AND** the executor distinguishes its changes from modifications inherited at handover

#### Scenario: Implementation signals ready for review

- **GIVEN** actual self-checks and a handover report have been saved for one stage
- **WHEN** the executor publishes its stage-specific ready-for-review signal
- **THEN** it stops modifying that candidate until review or a follow-up repair task
- **AND** Codex review and user acceptance remain pending until performed by the corresponding reviewers
