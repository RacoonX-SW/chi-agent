"""Test-only interpreter shim for an isolated Harbor rehearsal image.

Only OpenCode HTTP responses are synthetic; localhost traffic is the real MCP.
This file is not part of the exported participant package.
"""
import json
import os
import runpy
import sys

sys.path[:0] = ["/test/model", "/pdf-deps", "/opt/chi-go/scripts", "/opt/chi-go/vendor/chi-bench/src"]
import httpx

RealTransport = httpx.AsyncHTTPTransport


class SyntheticTransport(httpx.AsyncBaseTransport):
    def __init__(self, *args, **kwargs):
        self.real = RealTransport(*args, **kwargs)

    async def handle_async_request(self, request):
        if request.url.host in {"localhost", "127.0.0.1"}:
            return await self.real.handle_async_request(request)
        if request.url.host != "opencode.ai":
            raise RuntimeError("synthetic_unexpected_network")
        body = json.loads(request.content)
        names = {tool["function"]["name"] for tool in body["tools"]}
        prior = sum(item.get("role") == "tool" for item in body["messages"])
        if "inspect_code" in names:
            call = ("inspect_code", {}) if prior == 0 else (
                "verify_patch", {"code": "def add(a, b):\n    return a + b\n"}) if prior == 1 else None
        else:
            call = ("people__list_ordering_providers", {}) if prior == 0 else None
            if call and call[0] not in names:
                raise RuntimeError("synthetic_readonly_tool_missing")
        message = {"role": "assistant", "content": "synthetic complete"}
        finish = "stop"
        if call:
            name, args = call
            message = {"role": "assistant", "content": None, "reasoning_content": "synthetic",
                       "tool_calls": [{"id": f"call_{prior + 1}", "type": "function",
                                       "function": {"name": name, "arguments": json.dumps(args)}}]}
            finish = "tool_calls"
        return httpx.Response(200, request=request, json={"id": "synthetic", "object": "chat.completion",
            "created": 0, "model": "deepseek-v4.1-flash", "choices": [{"index": 0, "message": message,
            "finish_reason": finish}], "usage": {"prompt_tokens": 3, "completion_tokens": 2,
            "total_tokens": 5, "cost": 0, "opencode": {"billing_source": "go", "list_cost": 0.1,
            "allowance": 0.1}}})

    async def aclose(self):
        await self.real.aclose()


httpx.AsyncHTTPTransport = SyntheticTransport
target = sys.argv.pop(1)
if "coding-b" in sys.argv:
    os.environ["OPENCODE_API_KEY"] = "synthetic-harbor-key-only"
scenario_path = "/test/scenario"
scenario = open(scenario_path).read().strip() if os.path.exists(scenario_path) else "success"
if "live" in sys.argv and scenario == "runner-nonzero":
    raise SystemExit(23)
sys.argv[0] = target
try:
    runpy.run_path(target, run_name="__main__")
except SystemExit as exc:
    if "live" in sys.argv and scenario == "corrupt-trace" and exc.code == 0:
        with open("/logs/agent/chi-run/trace.jsonl", "w") as trace:
            trace.write("synthetic-corrupt-trace\n")
    raise
