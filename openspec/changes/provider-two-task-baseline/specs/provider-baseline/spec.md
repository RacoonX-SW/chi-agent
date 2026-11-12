## ADDED Requirements

### Requirement: Frozen compatible tasks and controlled conditions
The development baseline SHALL select two new public PA provider tasks from pinned public inputs, validate current review-contract and runtime compatibility, and freeze task/resource identities before C. It MUST preserve one common participant configuration and one common reviewer configuration across the first runs.

#### Scenario: A public candidate is incompatible
- **WHEN** a candidate does not satisfy the existing official PA review eligibility or required runtime resources
- **THEN** it is excluded with a recorded reason before trial, without weakening the contract or inspecting hidden answers to tune the participant

#### Scenario: An unknown task or changed resource is requested
- **WHEN** task-id is outside the frozen allowlist or its pinned files/version/path/hash/metadata disagree
- **THEN** execution is refused before provider requests or world creation

### Requirement: Explicit task provenance with shared history
The local C entry SHALL carry task identity and fixed resource identity through the official world, worker/claim, logs, capture and review. It SHALL reuse the existing loop, source-level B, shared accounting and attempt exclusion without per-task answers or flows.

#### Scenario: Two tasks run under one reviewed source
- **WHEN** the current source has a successful real B and settled prior attempts
- **THEN** each selected C creates a fresh world and independent attempt, retains all prior costs/failures/claims, and uses its own public input and fixed fixtures
- **AND** hidden grading data stays outside participant-visible resources and unknown usage blocks later calls

#### Scenario: Identity or source changes
- **WHEN** source changes or capture/claim/world/task/resource identities conflict
- **THEN** source changes require an explicit preserved rebind and new B; conflicting evidence cannot be reviewed or relabelled

### Requirement: Complete terminal evidence and honest failure diagnosis
Every started C SHALL attempt a bounded authoritative export after the participant is quiescent and before world cleanup, preserving actual success/failure status and exact owned cleanup.

#### Scenario: The runner exits nonzero or waiting fails
- **WHEN** a runner fails
- **THEN** its failure and usage remain recorded, the controller confirms exit or stops the exact owned runner before capture, and inability to prove a terminal state makes capture unavailable
- **AND** available complete settled evidence may be checked as failed-run diagnosis without promoting the attempt to success

#### Scenario: Review or accounting is incomplete
- **WHEN** evidence/provenance is missing, cleanup is unverified, usage is unknown, or verdicts are incomplete
- **THEN** no successful verdict is inferred and no automatic paid retry occurs

### Requirement: Distinct observations and reproducible improvement
Reports SHALL include every actual attempt, tool calls, usage, measured elapsed time and cost-estimate provenance. They SHALL distinguish engineering results, observed business state, deterministic partial checks and DeepSeek development verdicts; official reward SHALL remain null.

#### Scenario: New-task findings suggest an improvement
- **WHEN** failures are observed
- **THEN** the report identifies evidence supporting engineering versus decision causes, proposes a general mechanism and a fixed-condition validation plan, and does not claim cross-task competence from a single task or local verdicts as official scores
