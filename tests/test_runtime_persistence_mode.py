from types import SimpleNamespace

import pytest

from evergrowth.core.runtime import EvergrowthRuntime


def make_runtime(tmp_path):
    config = SimpleNamespace(
        di_name="Ethan",
        resolve_data_dir=lambda: tmp_path,
        heartbeat=SimpleNamespace(enabled=True),
        tray=SimpleNamespace(enabled=False),
    )
    runtime = EvergrowthRuntime(config)
    calls = []

    async def noop():
        return None

    for name in (
        "_init_memory", "_init_identity", "_init_skills", "_init_self_prompt",
        "_init_experiments", "_init_autonomy", "_init_live_telemetry",
        "_init_scheduler", "_init_mcp",
    ):
        setattr(runtime, name, noop)

    async def init_heartbeat():
        runtime.heartbeat = SimpleNamespace(start=lambda: calls.append("heartbeat"))

    async def init_di_loop():
        calls.append("di_loop")

    runtime._init_heartbeat = init_heartbeat
    runtime._init_di_loop = init_di_loop
    return runtime, calls


@pytest.mark.asyncio
async def test_nonpersistent_runtime_suppresses_autonomous_services(tmp_path):
    runtime, calls = make_runtime(tmp_path)

    await runtime.start(persistent=False)

    assert calls == []


@pytest.mark.asyncio
async def test_persistent_runtime_starts_autonomous_services(tmp_path):
    runtime, calls = make_runtime(tmp_path)

    await runtime.start(persistent=True)

    assert calls == ["heartbeat", "di_loop"]
