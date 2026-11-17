"""Thin Harbor adapter for the Go CHI package (full Harbor delivery unverified)."""
from __future__ import annotations

import os
import re
import shlex
import json
import hashlib
import stat
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from chi_bench.experiment.agents.openai_agents_harness import OpenAIAgentsHarness
from chi_agent.evaluation_bundle import _check_components, _read_regular_bounded
from chi_agent.delivery import FORBIDDEN_ENV

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _json(text):
    return json.loads(text, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))


def _read(path, limit):
    path = _check_components(path, "chi_harness_log_invalid", final_may_be_missing=False)
    return _read_regular_bounded(path, limit, "chi_harness_log_invalid").decode("utf-8")


def _nonnegative(value):
    return type(value) is int and 0 <= value <= 10**12


class GoChiHarness(OpenAIAgentsHarness):
    """Launch the installed package with one selected MCP and only the Go key."""

    CLI_FLAGS = []

    @staticmethod
    def name() -> str:
        return "chi-go"

    @property
    def extra_env(self) -> dict[str, str]:
        # Trial snapshots this property into a high-priority environment scope
        # before run(). Pass the one credential explicitly after input checks.
        return {}

    async def install(self, environment) -> None:
        """Intentionally no network install.

        The caller supplies the exported package, pinned model/PDF dependencies,
        official source checkout, public resources and writable state/log
        directories in the world image. ``run()`` performs the no-key package
        preflight before any model credential is read; a missing package or
        dependency fails there rather than being downloaded here.
        """
        del environment
        return None

    def populate_context_post_run(self, context) -> None:
        original = self.logs_dir
        try:
            self.logs_dir = original / "chi-run"
            if getattr(self, "_runner_succeeded", False):
                try:
                    result = _json(_read(self.logs_dir / "run_result.json", 1024 * 1024))
                    log = _json(_read(self.logs_dir / "run_log.txt", 1024 * 1024))
                    output = _read(self.logs_dir / "run_output.txt", 16 * 1024 * 1024)
                    trace = [_json(line) for line in _read(self.logs_dir / "trace.jsonl", 64 * 1024 * 1024).splitlines()]
                    if (type(result) is not dict or result.get("error", "missing") is not None
                            or not all(_nonnegative(result.get(key)) for key in ("input_tokens", "output_tokens", "turns"))
                            or result["turns"] == 0 or result.get("cost_usd", "missing") is not None
                            or "cached_tokens" not in result
                            or (result["cached_tokens"] is not None and not _nonnegative(result["cached_tokens"]))
                            or result.get("model") != "deepseek-v4.1-flash"
                            or type(result.get("final_output")) is not str
                            or result["final_output"] != output or not output
                            or type(log) is not dict or log.get("status") != "complete"
                            or log.get("safe_error_code", "missing") is not None or len(trace) < 3
                            or any(type(row) is not dict or row.get("role") not in {"system", "user", "assistant", "tool", "reasoning"}
                                   or type(row.get("content")) is not str for row in trace)
                            or trace[1].get("role") != "user"
                            or hashlib.sha256(trace[1]["content"].encode()).hexdigest() != self._instruction_sha256
                            or trace[-1].get("role") != "assistant" or trace[-1]["content"] != output):
                        raise ValueError
                except Exception:
                    raise RuntimeError("chi_runner_logs_invalid") from None
                try:
                    (self.logs_dir / "trajectory.json").lstat()
                except FileNotFoundError:
                    pass
                except OSError:
                    raise RuntimeError("chi_runner_trajectory_invalid") from None
                else:
                    # The parent must create a new file, not follow or reuse an
                    # agent-supplied trajectory (including a symlink).
                    raise RuntimeError("chi_runner_trajectory_invalid")
            super().populate_context_post_run(context)
            if getattr(self, "_runner_succeeded", False):
                try:
                    from harbor.models.trajectories.trajectory import Trajectory
                    from harbor.models.trajectories.final_metrics import FinalMetrics
                    path = self.logs_dir / "trajectory.json"
                    trajectory = Trajectory.model_validate(_json(_read(path, 64 * 1024 * 1024)))
                    metrics = trajectory.final_metrics or FinalMetrics(total_steps=len(trajectory.steps))
                    metrics.total_prompt_tokens = result["input_tokens"]
                    metrics.total_completion_tokens = result["output_tokens"]
                    metrics.total_cached_tokens = result["cached_tokens"]
                    metrics.total_cost_usd = None
                    trajectory.final_metrics = metrics
                    note = "Aggregate token totals come from settled run results; step usage may omit tool-call responses."
                    trajectory.notes = (trajectory.notes + "\n" if trajectory.notes else "") + note
                    data = trajectory.to_json_dict()
                    data["final_metrics"]["total_cached_tokens"] = result["cached_tokens"]
                    data["final_metrics"]["total_cost_usd"] = None
                    encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode()
                    Trajectory.model_validate(_json(encoded.decode()))
                    if (context.n_input_tokens != result["input_tokens"]
                            or context.n_output_tokens != result["output_tokens"]
                            or context.n_cache_tokens != result["cached_tokens"] or context.cost_usd is not None):
                        raise ValueError
                    fd = os.open(path, os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                    with os.fdopen(fd, "wb") as file:
                        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                            raise ValueError
                        os.ftruncate(file.fileno(), 0)
                        file.write(encoded)
                    Trajectory.model_validate(_json(_read(path, 64 * 1024 * 1024)))
                except Exception:
                    raise RuntimeError("chi_runner_trajectory_invalid") from None
        finally:
            self.logs_dir = original

    async def run(self, instruction, environment, context) -> None:
        del context
        urls = [server.url for server in self.mcp_servers if server.url]
        if len(urls) != 1 or type(instruction) is not str or not instruction.strip():
            raise RuntimeError("chi_harness_input_invalid")
        self._instruction_sha256 = hashlib.sha256(instruction.encode()).hexdigest()
        saved = self._extra_env
        self._runner_succeeded = False
        values = {key: saved.get(key, os.environ.get(key)) for key in (
            "CHI_GO_BUNDLE_ROOT", "CHI_GO_STATE_ROOT", "CHI_GO_ROLE",
            "CHI_GO_EVALUATION_ID", "CHI_GO_TASK_ID", "CHI_GO_ATTEMPT_ID", "CHI_GO_RUN_ID",
            "CHI_GO_BUNDLE_SHA256", "CHI_GO_HISTORY_MODE", "CHI_GO_Q_ROOT")}
        if values["CHI_GO_ROLE"] not in {"provider", "payer", "cm"}:
            raise RuntimeError("chi_harness_role_invalid")
        try:
            parsed = urlsplit(urls[0])
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or parsed.path != "/mcp"
                    or parsed.port != {"provider": 8020, "payer": 8100, "cm": 8200}[values["CHI_GO_ROLE"]]
                    or any(ch.isspace() for ch in urls[0])):
                raise ValueError
        except (ValueError, TypeError):
            raise RuntimeError("chi_harness_mcp_invalid") from None
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
        # Trial's scoped and persistent environment overlays would otherwise
        # reach docker exec before env -i removes them from the runner process.
        if environment._merge_env(None):
            raise RuntimeError("chi_harness_environment_invalid")
        # The official Docker backend forwards these host credentials at start.
        # Inspect names only; do not read their values.
        host_env = getattr(environment, "_host_env", {})
        # Keep this list identical to the delivery plan: the direct DeepSeek
        # key is as forbidden as the other provider credentials.
        if any(name in host_env for name in FORBIDDEN_ENV):
            raise RuntimeError("chi_harness_environment_invalid")
        preflight = shlex.join(["python", values["CHI_GO_BUNDLE_ROOT"] + "/scripts/go_chi_entry.py",
                                "preflight", "--bundle-sha256", values["CHI_GO_BUNDLE_SHA256"]])
        try:
            checked = await environment.exec(
                command="set -o pipefail; env -i PATH=/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin "
                        "PYTHONDONTWRITEBYTECODE=1 " + preflight, env={})
        except Exception:
            raise RuntimeError("chi_harness_preflight_failed") from None
        preflight_code = getattr(checked, "return_code", None)
        try:
            (self.logs_dir / "chi-preflight-summary.json").write_text(json.dumps({
                "status": "complete" if type(preflight_code) is int and preflight_code == 0 else "failed",
                "return_code": preflight_code if type(preflight_code) is int else None}, sort_keys=True))
        except OSError:
            raise RuntimeError("chi_harness_preflight_log_failed") from None
        if type(preflight_code) is not int or preflight_code != 0:
            raise RuntimeError("chi_harness_preflight_failed")
        values["OPENCODE_API_KEY"] = (saved["OPENCODE_API_KEY"] if "OPENCODE_API_KEY" in saved
                                      else os.environ.get("OPENCODE_API_KEY"))
        if type(values["OPENCODE_API_KEY"]) is not str or not values["OPENCODE_API_KEY"].strip():
            raise RuntimeError("chi_harness_key_missing")
        instruction_path = "/tmp/chi-go-instruction-" + values["CHI_GO_RUN_ID"] + ".md"
        logs_dir = "/logs/agent/chi-run"
        command_args = ["python", values["CHI_GO_BUNDLE_ROOT"] + "/scripts/go_chi_entry.py", "live",
            "--instruction-file", instruction_path, "--mcp-url", urls[0], "--logs-dir", logs_dir,
            "--output-root", values["CHI_GO_STATE_ROOT"], "--role", values["CHI_GO_ROLE"],
            "--bundle-sha256", values["CHI_GO_BUNDLE_SHA256"], "--history-mode", values["CHI_GO_HISTORY_MODE"],
            "--evaluation-id", values["CHI_GO_EVALUATION_ID"], "--task-id", values["CHI_GO_TASK_ID"],
            "--attempt-id", values["CHI_GO_ATTEMPT_ID"], "--run-id", values["CHI_GO_RUN_ID"]]
        if qroot is not None:
            command_args.extend(["--local-q-root", qroot])
        command = ("umask 077; set --; for f in /input/tool_reference.md "
                   "/opt/healthverse-task-assets/tool_reference.md /opt/chi-bench-task-assets/tool_reference.md; "
                   'do if [ -f "$f" ] && [ ! -L "$f" ] && [ ! -L "${f%/*}" ]; '
                   'then set -- "$@" --tool-reference "$f"; fi; done; '
                   "(set -C; printf %s " + shlex.quote(instruction) + " > "
                   + shlex.quote(instruction_path) + ") && env -i "
                   + "PATH=/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "
                   + 'OPENCODE_API_KEY="$OPENCODE_API_KEY" ' + shlex.join(command_args) + ' "$@"')
        try:
            # BaseInstalledAgent merges _extra_env over env; discard every extra
            # for this process so no unrelated provider key is forwarded.
            self._extra_env = {}
            # Avoid BaseInstalledAgent._exec debug logging the credential env.
            try:
                result = await environment.exec(command="set -o pipefail; " + command,
                                                env={"OPENCODE_API_KEY": values["OPENCODE_API_KEY"]})
            except BaseException as exc:
                try:
                    (self.logs_dir / "chi-exec-summary.json").write_text(
                        json.dumps({"status": "exec_exception", "return_code": None}))
                except OSError:
                    self.logger.warning("chi_harness_log_failed")
                if not isinstance(exc, Exception) or isinstance(exc, TimeoutError):
                    raise
                raise RuntimeError("chi_harness_exec_failed") from None
            code = getattr(result, "return_code", getattr(result, "exit_code", None))
            summary = {"status": "complete" if type(code) is int and code == 0 else "failed",
                       "return_code": code if type(code) is int else None}
            try:
                if values["OPENCODE_API_KEY"] in result.stdout:
                    raise ValueError
                runner_status = json.loads(result.stdout)
                if (type(runner_status) is dict and runner_status.get("status") in {"blocked", "incomplete"}
                        and type(runner_status.get("safe_error_code")) is str
                        and re.fullmatch(r"[a-z0-9_]{1,64}", runner_status["safe_error_code"])):
                    summary["safe_error_code"] = runner_status["safe_error_code"]
            except (ValueError, TypeError, AttributeError):
                pass
            for name in ("stdout", "stderr"):
                raw = getattr(result, name, None)
                if isinstance(raw, str):
                    encoded = raw.encode("utf-8")
                    summary[name] = {"bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
                else:
                    summary[name] = None
            try:
                (self.logs_dir / "chi-exec-summary.json").write_text(json.dumps(summary, sort_keys=True))
            except OSError:
                if type(code) is int and code == 0:
                    raise RuntimeError("chi_harness_log_failed") from None
                self.logger.warning("chi_harness_log_failed")
            if type(code) is not int or code != 0:
                raise RuntimeError("chi_runner_failed")
            self._runner_succeeded = True
        finally:
            self._extra_env = saved
