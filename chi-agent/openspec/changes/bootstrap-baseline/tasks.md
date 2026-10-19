## 1. Inspect and freeze the baseline

- [ ] 1.1 Read project instructions and these artifacts; record repository state and actual executor identity.
- [ ] 1.2 Check Python, uv and Docker availability without invoking a model; report missing dependencies.
- [ ] 1.3 Fetch the official source into an ignored directory and pin its actual commit; inspect that version's installation, task and CLI contracts.
- [ ] 1.4 Record user-controlled prerequisites separately: registration, handbook approval and local credentials; do not claim they are complete without evidence.

## 2. Implement the bounded wrapper

- [ ] 2.1 Add the minimal project manifest and configuration example required by the wrapper; use environment-variable references for secrets.
- [ ] 2.2 Implement a no-model readiness command with clear missing-dependency/configuration output.
- [ ] 2.3 Add a single-task baseline entry point with actual argv invocation, finite limits, isolated result directory and failure reporting.
- [ ] 2.4 Produce a local manifest linked to real upstream results; preserve reward 0 and null verdicts, and retain unknown usage as null.
- [ ] 2.5 Add focused offline checks for missing dependencies/configuration, command failure, timeout, missing verdict and fixture success; default checks require no network or API key.

## 3. Verify and hand over

- [ ] 3.1 Run and record actual offline checks; provide diff, exact commands, exit codes and limitations.
- [ ] 3.2 Once prerequisites are available, run one real official task and retain local evidence; leave this unchecked if blocked.
- [ ] 3.3 Report measured duration and available usage/cost, failed stages and implications for the next change; identify unmeasured fields.
- [ ] 3.4 Codex independently reviews the code and applicable offline checks; user inspects the demonstrated result.

Do not check 3.2 based on a dry run or fixture. Do not mark Codex/user acceptance complete on their behalf. If access is pending, hand over completed offline work with the real-run prerequisite still open.
