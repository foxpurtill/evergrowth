import asyncio
from pathlib import Path

from evergrowth.di.providers import HermesProvider, load_provider


def test_load_hermes_provider():
    provider = load_provider({
        "provider": "hermes",
        "model": "gpt-5.6",
        "wrapper_path": r"C:\Users\susur\Ethan\hermes_delegate.py",
        "cwd": r"C:\Users\susur\Ethan",
        "timeout": 30,
    })
    assert isinstance(provider, HermesProvider)
    assert provider.name() == "hermes/gpt-5.6"


def test_hermes_provider_renders_messages(tmp_path: Path):
    wrapper = tmp_path / "fake_wrapper.py"
    wrapper.write_text(
        "import sys\nprint(sys.argv[1])\n",
        encoding="utf-8",
    )
    provider = HermesProvider(str(wrapper), str(tmp_path), timeout=5)
    result = asyncio.run(provider.complete([
        {"role": "system", "content": "Keep it bounded."},
        {"role": "user", "content": "Return TEST_OK."},
    ]))
    assert "[SYSTEM]" in result
    assert "Keep it bounded." in result
    assert "[USER]" in result
    assert "Return TEST_OK." in result


def test_hermes_provider_includes_policy(tmp_path: Path):
    wrapper = tmp_path / "fake_wrapper.py"
    wrapper.write_text("import sys\nprint(sys.argv[1])\n", encoding="utf-8")
    policy = tmp_path / "policy.md"
    policy.write_text("Internal reversible work: act.", encoding="utf-8")
    provider = HermesProvider(
        str(wrapper), str(tmp_path), timeout=5, policy_path=str(policy)
    )
    result = asyncio.run(provider.complete([
        {"role": "user", "content": "Return POLICY_OK."},
    ]))
    assert "[AUTONOMY POLICY]" in result
    assert "Internal reversible work: act." in result
