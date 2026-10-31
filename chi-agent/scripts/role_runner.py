"""Explicit package-external development wrapper around the reviewed Go entry."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import sys
from pathlib import Path

import httpx
import uvicorn

from dev_patient_broker import PatientBroker
from go_chi_entry import main

STATUS_PATH = Path('/runner-logs/lifecycle.json')
CAPABILITY_PATH = Path('/run/chi-capability')


class TrackedServer:
    """Remember whether an MCP mutation might still be running remotely."""
    def __init__(self, server, state):
        self.server, self.state = server, state

    async def __aenter__(self):
        self.opened = await self.server.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.server.__aexit__(*args)

    async def list_tools(self):
        return await self.opened.list_tools()

    async def call_tool(self, *args, **kwargs):
        self.state['active'] += 1
        try:
            return await self.opened.call_tool(*args, **kwargs)
        except BaseException:
            self.state['uncertain'] = True
            raise
        finally:
            self.state['active'] -= 1


async def development(journal, secret, run_chi, kwargs):
    """Own the broker and runner in one loop, before the entry closes its journal."""
    state = {'world_quiescence': 'unproven', 'broker_drained': False}
    tracking = {'active': 0, 'uncertain': False}
    broker = server = server_task = None
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    old_term = signal.getsignal(signal.SIGTERM)
    loop.add_signal_handler(signal.SIGTERM, task.cancel)
    try:
        from go_chi_mcp import selected_server
        kwargs['server_factory'] = lambda url: TrackedServer(selected_server(url, auxiliary=kwargs['role'] == 'cm'), tracking)
        if kwargs['role'] == 'cm':
            capability = CAPABILITY_PATH.read_text(encoding='ascii').strip()
            lock = asyncio.Lock()
            broker = PatientBroker(journal, secret, capability, lock,
                                   lambda: httpx.AsyncHTTPTransport(retries=0, verify=True))
            # The route to the world selects the runner's internal-interface address.
            host = os.environ['CHI_DEV_WORLD_HOST']
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((socket.gethostbyname(host), 8200))
                bind = probe.getsockname()[0]
            config = uvicorn.Config(broker.app(), host=bind, port=8765, log_config=None,
                                    access_log=False, lifespan='off', timeout_graceful_shutdown=450)
            server = uvicorn.Server(config)
            # Uvicorn 0.54 wraps serve() with capture_signals(), not the
            # historical install_signal_handlers() API. The runner owns TERM.
            server.capture_signals = contextlib.nullcontext
            server_task = asyncio.create_task(server.serve())
            async with asyncio.timeout(30):
                while not server.started:
                    if server_task.done(): raise RuntimeError('broker_start_failed')
                    await asyncio.sleep(.05)
            kwargs['auxiliary'] = broker
        async with asyncio.timeout(1500):
            result = await run_chi(journal, secret, **kwargs)
        return result
    finally:
        prior_error = sys.exc_info()[0] is not None
        cleanup_error = None
        try:
            if server is not None:
                server.should_exit = True
                async with asyncio.timeout(450):
                    if server_task is not None:
                        await server_task
                    await broker.close()
                    state['broker_drained'] = not broker.busy
            else:
                state['broker_drained'] = True
            if (state['broker_drained'] and tracking['active'] == 0 and not tracking['uncertain']
                    and (broker is None or (not broker.busy and broker.parent is None))):
                state['world_quiescence'] = 'confirmed'
        except BaseException as exc:
            cleanup_error = exc
            state['world_quiescence'] = 'unproven'
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
            signal.signal(signal.SIGTERM, old_term)
            STATUS_PATH.write_text(json.dumps(state, sort_keys=True), encoding='utf-8')
        if cleanup_error is not None and not prior_error:
            raise cleanup_error


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:], development=development))
