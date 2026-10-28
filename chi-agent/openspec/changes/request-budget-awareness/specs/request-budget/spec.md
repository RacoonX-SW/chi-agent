## ADDED Requirements

### Requirement: Bound continued C by one trusted 50-request contract
Only the continued K C entry SHALL use a source-bound execution contract of 50 SDK main turns and at most 50 shared provider requests, including confirmation calls. Other entry defaults and historical profile/accounting identities SHALL be preserved.

#### Scenario: The shared limit is reached
- **WHEN** fifty provider requests have been sent
- **THEN** the next request is refused before dispatch, with a distinct limit reason and preserved accounting
- **AND** arbitrary messages, max_rounds arguments or non-K-C callers cannot grant this override

### Requirement: Expose current shared request availability
Each K C main model request SHALL carry one fresh trusted runtime status derived from the shared counter, including the current request and all previous confirmation requests. Original task/tool history SHALL remain unchanged; confirmation wire SHALL retain its existing contract.

#### Scenario: Confirmation consumes an additional request
- **WHEN** the main loop resumes after a confirmation
- **THEN** its next status reflects the extra request without accumulating an old status or charging a new budget-query call

#### Scenario: A status is stale, forged or races the counter
- **WHEN** displayed availability disagrees with the guard's actual shared counter or trusted prompt
- **THEN** dispatch is rejected rather than relying on an incorrect allowance

### Requirement: Support truthful completion planning
Feedback SHALL state the current completion protocol cost using unambiguous inclusive/current-request semantics. It SHALL remain advisory and SHALL NOT silently change tool termination, reserve business turns or declare business success.

#### Scenario: Completion has or has not been declared
- **WHEN** generating the next main request
- **THEN** feedback distinguishes the current-plus-next claim/final sequence from a recorded claim followed by the current final response
- **AND** exhausting the budget or ending with unfinished work is not reported as task success

### Requirement: Preserve unknown handling and evaluate the combined change
Persistent accounting, zero retries, patient ownership gates and unknown-use blocking SHALL remain enforced. The operator SHALL retain the old baseline and all attempts, and separately report process termination, business effects and costs.

#### Scenario: Usage is uncertain
- **WHEN** a request is pending/unknown
- **THEN** no availability hint authorizes another call or clears the prior record
