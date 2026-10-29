"""Thin Harbor adapter for the Go CHI package (full Harbor delivery unverified)."""
from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePosixPath

from chi_bench.experiment.agents.openai_agents_harness import OpenAIAgentsHarness

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class GoChiHarness(OpenAIAgentsHarness):
    """Launch the installed package with one selected MCP and only the Go key."""

    CLI_FLAGS = []

    @staticmethod
    def name() -> str:
        return "chi-go"

    async def install(self, environment) -> None:
        # Package and its pinned dependencies are supplied by the caller.
        return None

    def populate_context_post_run(self, context) -> None:
        original = self.logs_dir
        try:
            self.logs_dir = original / "chi-run"
            super().populate_context_post_run(context)
        finally:
            self.logs_dir = original

    async def run(self, instruction, environment, context) -> None:
        del context
        urls = [server.url for server in self.mcp_servers if server.url]
        if len(urls) != 1 or type(instruction) is not str or not instruction.strip():
            raise RuntimeError("chi_harness_input_invalid")
        saved = self._extra_env
        values = {key: saved.get(key, os.environ.get(key)) for key in (
            "OPENCODE_API_KEY", "CHI_GO_BUNDLE_ROOT", "CHI_GO_STATE_ROOT", "CHI_GO_ROLE",
            "CHI_GO_EVALUATION_ID", "CHI_GO_TASK_ID", "CHI_GO_ATTEMPT_ID", "CHI_GO_RUN_ID",
            "CHI_GO_BUNDLE_SHA256", "CHI_GO_HISTORY_MODE", "CHI_GO_Q_ROOT")}
        if type(values["OPENCODE_API_KEY"]) is not str or not values["OPENCODE_API_KEY"].strip():
            raise RuntimeError("chi_harness_key_missing")
        if values["CHI_GO_ROLE"] not in {"provider", "payer", "cm"}:
            raise RuntimeError("chi_harness_role_invalid")
        if type(values["CHI_GO_BUNDLE_SHA256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", values["CHI_GO_BUNDLE_SHA256"]):
            raise RuntimeError("chi_harness_identity_invalid")
        if values["CHI_GO_HISTORY_MODE"] not in {"local", "external"}:
            raise RuntimeError("chi_harness_history_invalid")
        for key in ("CHI_GO_EVALUATION_ID", "CHI_GO_TASK_ID", "CHI_GO_ATTEMPT_ID", "CHI_GO_RUN_ID"):
            if type(values[key]) is not str or not ID.fullmatch(values[key]):
                raise RuntimeError("chi_harness_identity_invalid")
        for key in ("CHI_GO_BUNDLE_ROOT", "CHI_GO_STATE_ROOT"):
            value = values[key]
            if (type(value) is not str or not value.startswith("/") or ".." in PurePosixPath(value).parts):
                raise RuntimeError("chi_harness_path_invalid")
        qroot = values["CHI_GO_Q_ROOT"]
        if values["CHI_GO_HISTORY_MODE"] == "local":
            if type(qroot) is not str or not qroot.startswith("/") or ".." in PurePosixPath(qroot).parts:
                raise RuntimeError("chi_harness_path_invalid")
        elif qroot is not None:
            raise RuntimeError("chi_harness_history_invalid")
        instruction_path = "/tmp/chi-go-instruction-" + values["CHI_GO_RUN_ID"] + ".md"
        logs_dir = "/logs/agent/chi-run"
        command_args = ["python", values["CHI_GO_BUNDLE_ROOT"] + "/scripts/go_chi_entry.py", "live",
            "--instruction-file", instruction_path, "--mcp-url", urls[0], "--logs-dir", logs_dir,
            "--output-root", values["CHI_GO_STATE_ROOT"], "--role", values["CHI_GO_ROLE"],
            "--bundle-sha256", values["CHI_GO_BUNDLE_SHA256"], "--history-mode", values["CHI_GO_HISTORY_MODE"],
            "--evaluation-id", values["CHI_GO_EVALUATION_ID"], "--task-id", values["CHI_GO_TASK_ID"],
            "--attempt-id", values["CHI_GO_ATTEMPT_ID"], "--run-id", values["CHI_GO_RUN_ID"],
            "--tool-reference", "/input/tool_reference.md",
            "--tool-reference", "/opt/healthverse-task-assets/tool_reference.md",
            "--tool-reference", "/opt/chi-bench-task-assets/tool_reference.md"]
        if qroot is not None:
            command_args.extend(["--local-q-root", qroot])
        command = ("umask 077; (set -C; printf %s " + shlex.quote(instruction) + " > "
                   + shlex.quote(instruction_path) + ") && env -i "
                   + "PATH=/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "
                   + 'OPENCODE_API_KEY="$OPENCODE_API_KEY" ' + shlex.join(command_args))
        try:
            # BaseInstalledAgent merges _extra_env over env; discard every extra
            # for this process so no unrelated provider key is forwarded.
            self._extra_env = {}
            result = await self.exec_as_agent(environment, command=command,
                                              env={"OPENCODE_API_KEY": values["OPENCODE_API_KEY"]})
            code = getattr(result, "return_code", getattr(result, "exit_code", None))
            if type(code) is not int or code != 0:
                raise RuntimeError("chi_runner_failed")
        finally:
            self._extra_env = saved
