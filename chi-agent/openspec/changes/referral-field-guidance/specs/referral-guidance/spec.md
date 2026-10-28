# Referral Field Guidance

### Requirement: Add public-evidence guidance only to K C tool descriptions
The K C entry SHALL append source-bound versioned guidance to the existing case-creation and authorization-submission tool descriptions, without changing their names, schemas, callbacks or results. Other entries and unrelated tools SHALL retain their original metadata and behavior.

#### Scenario: Real SDK serialization
Given K C tools converted by the existing SDK path, when a main request is serialized, each selected description contains its original text and exactly one guidance block; the schema and tool dispatch remain unchanged, and no extra model request or tool is introduced.

### Requirement: Keep decisions grounded in public observations
Guidance SHALL distinguish service category from care setting, prefer explicit public sources to unsupported inference, and request concise source and pre-submission consistency checks. It SHALL NOT encode task IDs, patient IDs, clinical-case answer mappings, fixed default settings or hidden acceptable values.

#### Scenario: Different supported care settings
Synthetic source examples with differing settings remain selectable by the model through the unchanged tool schema; the guidance does not force one enum or rewrite arguments. Conflicting or missing support is treated as a decision uncertainty to investigate, not automatic proof of success.

### Requirement: Preserve accounting and isolate paid validation
The guidance module SHALL enter K execution identity and record its version and applied description hashes. Existing patient binding, shared 50-request accounting, confirmation/output limits, zero retry and unknown-usage blocking SHALL remain effective.

#### Scenario: Validation remains within authorization
Offline verification runs in Docker with synthetic inputs. Paid work follows the documented time windows, current-source B prerequisite and a single t013 development attempt/review; t019 paid reruns remain paused. No timing gate or background wakeup is added. Missing live evidence is reported as unverified.
