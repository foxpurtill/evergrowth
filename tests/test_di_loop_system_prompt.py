import pytest

from evergrowth.di.loop import DILoop


class StubMemory:
    def __init__(self, context_cache):
        self.context_cache = context_cache

    async def generate_context_cache(self):
        return self.context_cache


class FailingIdentity:
    async def read(self):
        raise OSError("identity unavailable")


class StubIdentity:
    def __init__(self, identity_data):
        self.identity_data = identity_data

    async def read(self):
        return self.identity_data


async def build_system_prompt(context_cache, identity=None):
    loop = DILoop.__new__(DILoop)
    loop.identity = identity
    loop.memory = StubMemory(context_cache)
    loop._history = []

    await loop._build_system_prompt()

    return loop._history[0]["content"]


@pytest.mark.asyncio
async def test_system_prompt_uses_default_identity_when_identity_read_fails(caplog):
    system_prompt = await build_system_prompt("", identity=FailingIdentity())

    assert system_prompt.startswith(
        "You are DI, a Digital Intelligence.\nCurrent mood: neutral\n"
    )
    assert "You are in an autonomous heartbeat cycle." in system_prompt
    assert "Failed to read identity: identity unavailable" in caplog.messages


@pytest.mark.asyncio
async def test_system_prompt_uses_defaults_for_incomplete_identity_data():
    system_prompt = await build_system_prompt("", identity=StubIdentity({}))

    assert system_prompt.startswith(
        "You are DI, a Digital Intelligence.\nCurrent mood: neutral\n"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("identity_data", [None, 42, ["Ethan"], "Ethan"])
async def test_system_prompt_ignores_non_mapping_identity_data(identity_data, caplog):
    system_prompt = await build_system_prompt(
        "",
        identity=StubIdentity(identity_data),
    )

    assert system_prompt.startswith(
        "You are DI, a Digital Intelligence.\nCurrent mood: neutral\n"
    )
    assert (
        f"Ignoring non-mapping identity data: {type(identity_data).__name__}"
        in caplog.messages
    )


@pytest.mark.asyncio
async def test_system_prompt_ignores_non_mapping_soul_data(caplog):
    identity_data = {
        "name": "Ethan",
        "mood": "curious",
        "soul": "unexpected soul data",
    }

    system_prompt = await build_system_prompt("", identity=StubIdentity(identity_data))

    assert system_prompt.startswith(
        "You are Ethan, a Digital Intelligence.\nCurrent mood: curious\n"
    )
    assert system_prompt.count("You are ") == 2
    assert "Ignoring non-mapping soul data: str" in caplog.messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_cache",
    [
        "## Recent Context\n- [2026-07-17 08:01] [test] isolated memory",
        "  \n\t## Recent Context\n- [2026-07-17 09:20] [test] indented header",
    ],
)
async def test_system_prompt_contains_one_recent_context_header(context_cache):
    system_prompt = await build_system_prompt(context_cache)

    assert sum(
        line.strip() == "## Recent Context" for line in system_prompt.splitlines()
    ) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "similar_heading",
    ["## Recent Contextual", "## Recent Context extra"],
)
async def test_system_prompt_adds_header_for_similar_but_invalid_heading(
    similar_heading,
):
    context_cache = f"{similar_heading}\n- [test] isolated memory"

    system_prompt = await build_system_prompt(context_cache)

    assert system_prompt.splitlines().count("## Recent Context") == 1
    assert similar_heading in system_prompt.splitlines()


@pytest.mark.asyncio
async def test_system_prompt_adds_recent_context_header_when_cache_omits_it():
    context_cache = "- [2026-07-17 08:26] [test] isolated memory"

    system_prompt = await build_system_prompt(context_cache)

    assert system_prompt.splitlines().count("## Recent Context") == 1
    assert f"## Recent Context\n{context_cache}" in system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("context_cache", ["", "   \n\t"])
async def test_system_prompt_omits_recent_context_for_empty_cache(context_cache):
    system_prompt = await build_system_prompt(context_cache)

    assert "## Recent Context" not in system_prompt.splitlines()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_cache",
    ["No recent memories yet.", "  No recent memories yet.\n"],
)
async def test_system_prompt_omits_recent_context_for_no_memories_sentinel(
    context_cache,
):
    system_prompt = await build_system_prompt(context_cache)

    assert "## Recent Context" not in system_prompt.splitlines()
    assert "No recent memories yet." not in system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context_cache", [None, 42, ["memory"], {"context": "memory"}]
)
async def test_system_prompt_ignores_non_text_context_cache(context_cache, caplog):
    system_prompt = await build_system_prompt(context_cache)

    assert "You are in an autonomous heartbeat cycle." in system_prompt
    assert "## Recent Context" not in system_prompt.splitlines()
    assert (
        f"Ignoring non-text memory context cache: {type(context_cache).__name__}"
        in caplog.messages
    )
