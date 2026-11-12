"""Development lifecycle failures must never claim an authoritative world state."""
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import pytest

import chi_agent.mcp_tools as go_chi_mcp
import scripts.development.run_role_in_bundle as role_runner


def test_normal_runner_marks_world_quiescent(tmp_path, monkeypatch):
    status = tmp_path / 'status.json'
    monkeypatch.setattr(role_runner, 'STATUS_PATH', status)

    async def complete(*args, **kwargs):
        return 'done'

    result = asyncio.run(role_runner.development(None, 'key', complete, {'role': 'payer'}))
    assert result == 'done'
    assert json.loads(status.read_text()) == {'broker_drained': True, 'world_quiescence': 'confirmed'}


def test_cancelled_request_never_claims_world_quiescence(tmp_path, monkeypatch):
    status = tmp_path / 'status.json'
    monkeypatch.setattr(role_runner, 'STATUS_PATH', status)
    started = asyncio.Event()
    mutated = asyncio.Event()

    class Server:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def call_tool(self, *_args):
            async def world():
                started.set()
                await asyncio.sleep(.05)
                mutated.set()
            task = asyncio.create_task(world())
            await asyncio.shield(task)
    monkeypatch.setattr(go_chi_mcp, 'selected_server', lambda *args, **kwargs: Server())

    async def run(*args, **kwargs):
        async with kwargs['server_factory']('unused') as server:
            await server.call_tool('write', {})

    async def scenario():
        runner = asyncio.create_task(role_runner.development(None, 'key', run, {'role': 'payer'}))
        await started.wait()
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await runner
        assert not mutated.is_set()
        assert json.loads(status.read_text())['world_quiescence'] == 'unproven'
        await asyncio.wait_for(mutated.wait(), 1)

    asyncio.run(scenario())


def test_model_failure_after_completed_tool_keeps_quiescence(tmp_path, monkeypatch):
    status = tmp_path / 'status.json'
    monkeypatch.setattr(role_runner, 'STATUS_PATH', status)

    class Server:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def call_tool(self, *_args): return {'isError': True}
    monkeypatch.setattr(go_chi_mcp, 'selected_server', lambda *args, **kwargs: Server())

    async def fail(*args, **kwargs):
        async with kwargs['server_factory']('unused') as server:
            await server.call_tool('write', {})
        raise RuntimeError('upstream')

    with pytest.raises(RuntimeError, match='upstream'):
        asyncio.run(role_runner.development(None, 'key', fail, {'role': 'provider'}))
    assert json.loads(status.read_text())['world_quiescence'] == 'confirmed'


def test_sigterm_cancels_runner_and_drains_broker(tmp_path):
    status, started, capability = tmp_path / 'status.json', tmp_path / 'started', tmp_path / 'capability'
    capability.write_text('c' * 48)
    script = '''
import asyncio, os, pathlib, sys
import scripts.development.run_role_in_bundle as role_runner
role_runner.STATUS_PATH = pathlib.Path(sys.argv[1])
role_runner.CAPABILITY_PATH = pathlib.Path(sys.argv[3])
os.environ['CHI_DEV_WORLD_HOST'] = '127.0.0.1'
async def run(*a, **kw):
    pathlib.Path(sys.argv[2]).write_text('ready')
    await asyncio.Event().wait()
try:
    asyncio.run(role_runner.development(None, 'key', run, {'role': 'cm'}))
except asyncio.CancelledError:
    pass
'''
    process = subprocess.Popen([sys.executable, '-c', script, str(status), str(started), str(capability)])
    try:
        deadline = time.monotonic() + 10
        while not started.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.02)
        assert started.exists()
        os.kill(process.pid, signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert json.loads(status.read_text()) == {'broker_drained': True, 'world_quiescence': 'confirmed'}
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
