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

### Requirement: Respect the selected first-round runtime budget

The system SHALL account for the selected 5 CNY first-round runtime budget across integration checks and the one task attempt, separately from coding costs. A budget plan SHALL NOT lift an active implementation or paid-run pause.

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
