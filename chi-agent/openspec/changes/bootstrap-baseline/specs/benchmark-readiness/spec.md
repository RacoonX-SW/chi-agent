## ADDED Requirements

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
