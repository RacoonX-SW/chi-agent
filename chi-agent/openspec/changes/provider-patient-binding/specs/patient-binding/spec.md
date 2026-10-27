## ADDED Requirements

### Requirement: Confirm patient selection from public observations
The local continued C entry SHALL require a source-bound selection confirmation before operational mutation. Confirmation MUST use only public task input, actual provider observations and the existing guarded DeepSeek client; it MUST NOT use hidden targets or task-specific answers.

#### Scenario: Similar candidates have different clinical histories
- **WHEN** several public candidates share broad demographics or diagnosis
- **THEN** the confirmation assesses the full public description and observed differentiating facts, keeps unobserved plausible candidates unresolved, and refuses ambiguous, contradictory or unsupported selection
- **AND** raw evidence, references, candidate identity and completeness are checked without claiming deterministic clinical entailment

### Requirement: Preserve ownership at every side effect
Known patient/order/case/form/document and workspace relationships SHALL be checked before each mutation and after relevant returned identities, under one shared serialization boundary.

#### Scenario: Cross-patient, forged or unknown identity is supplied
- **WHEN** an operation cannot be proved to belong to the bound patient from prior successful observations
- **THEN** the backend is not called and a refusal is recorded
- **AND** a dispatched operation with unknown/conflicting effect blocks continuation rather than switching patients or retrying

#### Scenario: Confirmation or new identity is used concurrently
- **WHEN** confirmation shares a batch with another call, a write uses an unreturned identity, or an unknown tool appears
- **THEN** the batch cannot cause a side effect by racing the guard

### Requirement: Share guarded accounting and preserve failures
Confirmation requests SHALL count toward the same provider request/output limits and persistent accounting, with separate purpose and prompt/evidence provenance, zero automatic retry and at most two explicit confirmations.

#### Scenario: A request settles but confirmation is invalid
- **WHEN** JSON, references or semantic completeness fail
- **THEN** the cost remains settled and the patient remains unbound

#### Scenario: Usage or execution becomes uncertain
- **WHEN** timeout, cancellation, observer failure or unknown result leaves a pending request/effect
- **THEN** the trial stops and subsequent calls remain blocked, without clearing history or declaring zero cost

### Requirement: Validate whole-world effects in controlled regression
The operator SHALL independently review fixed synthetic behavior and then run the two existing development tasks with unchanged remaining settings, fresh attempts and complete terminal evidence. Full operational effects, normal completion and costs SHALL be compared alongside local partial verdicts.

#### Scenario: Local target verdicts pass while another patient is affected
- **WHEN** complete export contains a non-target operational write
- **THEN** the report retains the failure and does not count the trial as successful from target rubrics alone
