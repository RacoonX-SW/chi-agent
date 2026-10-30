"""Test-only role MCP discovery; list schemas, never mutate world state."""
import asyncio
import json
import sys
import hashlib
import time
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    for role, port in (("provider", 8020), ("payer", 8100), ("cm", 8200)):
        async with streamablehttp_client(f"http://127.0.0.1:{port}/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                print(json.dumps({"role": role, "tools": [{"name": tool.name,
                    "inputSchema": tool.inputSchema} for tool in result.tools]}, sort_keys=True))
                if "--invoke" in sys.argv:
                    name = {"provider": "people.list_ordering_providers",
                            "payer": "payer_intake_hub.list_intake_queue",
                            "cm": "cm_intake.list_referral_queue"}[role]
                    schema = next(tool.inputSchema for tool in result.tools if tool.name == name)
                    schema_bytes = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
                    started = time.monotonic()
                    response = await session.call_tool(name, {})
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    payload = response.model_dump_json(exclude_none=True).encode()
                    print(json.dumps({"role": role, "invoked": name,
                                      "arguments": {}, "isError": response.isError,
                                      "blocks": len(response.content), "response_bytes": len(payload),
                                      "response_sha256": hashlib.sha256(payload).hexdigest(),
                                      "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
                                      "elapsed_ms": elapsed_ms}))
                    if response.isError:
                        raise RuntimeError("readonly_mcp_call_failed")


asyncio.run(main())
