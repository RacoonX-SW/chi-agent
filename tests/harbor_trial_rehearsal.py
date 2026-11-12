"""Controller-side, test-only Harbor trial on an isolated synthetic world.

The caller supplies an exported participant bundle and fixed vendor on PYTHONPATH.
The world image must contain the real synthetic B run and the test-only HTTP shim.
"""
import asyncio
import argparse
import json
import os
import subprocess
from pathlib import Path

from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, TrialConfig, VerifierConfig
from harbor.trial.trial import Trial
from harbor.trial.hooks import TrialEvent
from harbor.models.trial.result import TrialResult

parser = argparse.ArgumentParser()
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--bundle", type=Path, required=True)
parser.add_argument("--image", required=True)
parser.add_argument("--scenario", choices=("claim-blocked", "runner-nonzero"), required=True)
args = parser.parse_args()
ROOT = args.out
TASK = ROOT / "pa_t018_t018_o001_p01_new_referral_provider"
TASK.mkdir(parents=True, exist_ok=False)
(TASK / "instruction.md").write_text("Synthetic rehearsal: inspect the available provider contacts without changing data.\n")
(TASK / "task.toml").write_text('''schema_version = "1.1"
artifacts = []
[task]
name = "actava-ai/pa_t018_t018_o001_p01_new_referral_provider"
description = "Synthetic Harbor rehearsal"
authors = []
keywords = []
[agent]
timeout_sec = 180
[environment]
network_mode = "no-network"
[[environment.mcp_servers]]
name = "provider"
transport = "streamable-http"
url = "http://localhost:8020/mcp"
''')
bundle_digest = json.loads((args.bundle / "bundle-manifest.json").read_text())["manifest_sha256"]
metadata = {"CHI_GO_BUNDLE_ROOT": "/opt/chi-go", "CHI_GO_STATE_ROOT": "/test/state",
            "CHI_GO_ROLE": "provider", "CHI_GO_EVALUATION_ID": "harbor-e",
            "CHI_GO_TASK_ID": "synthetic-trial", "CHI_GO_ATTEMPT_ID": "c", "CHI_GO_RUN_ID": "c",
            "CHI_GO_BUNDLE_SHA256": bundle_digest, "CHI_GO_HISTORY_MODE": "external"}
config = TrialConfig(task=TaskConfig(path=TASK), trial_name="synthetic-" + args.scenario,
    trials_dir=ROOT / "trials", agent=AgentConfig(import_path="go_chi_harness:GoChiHarness", env=metadata),
    environment=EnvironmentConfig(import_path="chi_bench.experiment.docker_env:ChiBenchDockerEnvironment",
                                  kwargs={"image": args.image, "host_env": {}}),
    verifier=VerifierConfig(disable=True))


async def main():
    trial = await Trial.create(config)
    async def before_agent(_event):
        paths = await trial.agent_environment.exec(
            "ls -ld /input /input/tool_reference.md /opt/healthverse-task-assets "
            "/opt/healthverse-task-assets/tool_reference.md /opt/chi-bench-task-assets "
            "/opt/chi-bench-task-assets/tool_reference.md 2>&1; true")
        (ROOT / "reference-paths.txt").write_text(paths.stdout or "")
        provision = await trial.agent_environment.exec(
            'src=$(readlink -f /opt/chi-bench-task-assets/tool_reference.md) && '
            'test "$src" = /opt/chi-bench/tasks/pa_t018_t018_o001_p01_new_referral_provider/tool_reference.md && '
            'test -f "$src" && printf "source=%s\\n" "$src" && sha256sum "$src" && wc -c < "$src" && '
            'mkdir -p /input && test ! -e /input/tool_reference.md && cp "$src" /input/tool_reference.md')
        (ROOT / "reference-provision.txt").write_text(provision.stdout or "")
        if provision.return_code != 0:
            raise RuntimeError("synthetic_reference_provision_failed")
        await trial.agent_environment.upload_file("/mcp_probe.py", "/tmp/harbor_mcp_probe.py")
        result = await trial.agent_environment.exec(
            "/workspace/.venv/bin/python /tmp/harbor_mcp_probe.py --invoke")
        (ROOT / "mcp-readonly.jsonl").write_text(result.stdout or "")
        if result.return_code != 0:
            raise RuntimeError("synthetic_mcp_probe_failed")
        result = await trial.agent_environment.exec("printf %s " + args.scenario + " > /test/scenario")
        if result.return_code != 0:
            raise RuntimeError("synthetic_scenario_setup_failed")

    async def after_agent(_event):
        await trial.agent_environment.download_dir("/test/state", ROOT / "state")

    trial.add_hook(TrialEvent.AGENT_START, before_agent)
    trial.add_hook(TrialEvent.AGENT_END, after_agent)
    old = os.environ.get("OPENCODE_API_KEY")
    os.environ["OPENCODE_API_KEY"] = "synthetic-harbor-key-only"
    try:
        result = await trial.run()
    finally:
        if old is None:
            os.environ.pop("OPENCODE_API_KEY", None)
        else:
            os.environ["OPENCODE_API_KEY"] = old
    if result.finished_at is None or not trial.paths.result_path.is_file():
        raise RuntimeError("synthetic_trial_not_finalized")
    persisted = TrialResult.model_validate_json(trial.paths.result_path.read_text())
    if persisted.finished_at is None or persisted.id != result.id or persisted.verifier_result is not None:
        raise RuntimeError("synthetic_trial_result_invalid")
    if result.verifier_result is not None:
        raise RuntimeError("synthetic_verifier_unexpected")
    check = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"],
                           check=True, capture_output=True, text=True)
    if trial.agent_environment.container_name in check.stdout.splitlines():
        raise RuntimeError("synthetic_trial_container_not_cleaned")
    secret = b"synthetic-harbor-key-only"
    leaked = []
    for path in (ROOT / "trials").rglob("*"):
        if path.is_file() and secret in path.read_bytes():
            leaked.append(str(path.relative_to(ROOT)))
    if leaked:
        raise RuntimeError("synthetic_secret_in_trial_output")
    print(json.dumps({"trial_class": type(trial).__name__, "exception": result.exception_info.model_dump()
        if result.exception_info else None, "agent_result": result.agent_result.model_dump()
        if result.agent_result else None, "verifier": result.verifier_result.model_dump()
        if result.verifier_result else None, "synthetic_key_leaked": False}, default=str, sort_keys=True))
    if result.exception_info is None or result.exception_info.exception_message != "chi_runner_failed":
        raise RuntimeError("synthetic_runner_failure_missing")
    summary_path = trial.paths.result_path.parent / "agent/chi-exec-summary.json"
    summary = json.loads(summary_path.read_text())
    if args.scenario == "claim-blocked":
        state = json.loads((ROOT / "state/chi-accounting.json").read_text())
        run = next(attempt for attempt in state["attempts"] if attempt["run"] == "c")
        assert summary["safe_error_code"] == "chi_claim_required" and not run["claim_done"]
        assert len(run["requests"]) == 3 and all(req["status"] == "settled" for req in run["requests"])
    else:
        assert summary["return_code"] == 23


asyncio.run(main())
