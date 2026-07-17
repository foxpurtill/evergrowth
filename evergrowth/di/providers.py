"""AI provider abstraction — OpenAI, Anthropic, local models."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("evergrowth.di.providers")


class AIProvider(ABC):
    """Base class for AI providers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Send messages and return the assistant's response text."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...


class OpenAIProvider(AIProvider):
    """OpenAI API provider (GPT-4, GPT-4o, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def name(self) -> str:
        return f"openai/{self.model}"

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class AnthropicProvider(AIProvider):
    """Anthropic API provider (Claude)."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model

    def name(self) -> str:
        return f"anthropic/{self.model}"

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        import httpx

        # Anthropic uses a different message format
        system = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": user_messages,
                    "temperature": temperature,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]


class OllamaProvider(AIProvider):
    """Local Ollama provider (llama3, mistral, etc.)."""

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def name(self) -> str:
        return f"ollama/{self.model}"

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]


class LMStudioProvider(AIProvider):
    """LM Studio local provider (OpenAI-compatible API)."""

    def __init__(self, model: str = "default", base_url: str = "http://localhost:1234"):
        self.model = model
        self.base_url = base_url

    def name(self) -> str:
        return f"lmstudio/{self.model}"

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class HermesProvider(AIProvider):
    """Hermes OAuth-backed provider via the local delegation wrapper."""

    def __init__(self, wrapper_path: str, cwd: str, timeout: int = 90,
                 model: str = "gpt-5.6", policy_path: str = ""):
        self.wrapper_path = wrapper_path
        self.cwd = cwd
        self.timeout = int(timeout)
        self.model = model
        self.policy_path = policy_path

    def name(self) -> str:
        return f"hermes/{self.model}"

    async def complete(self, messages: list[dict], max_tokens: int = 2048,
                       temperature: float = 0.7) -> str:
        import asyncio
        import sys

        rendered = []
        for message in messages:
            role = str(message.get("role", "user")).upper()
            content = str(message.get("content", "")).strip()
            if content:
                rendered.append(f"[{role}]\n{content}")
        policy = ""
        if self.policy_path:
            from pathlib import Path
            path = Path(self.policy_path).expanduser()
            if path.exists():
                policy = path.read_text(encoding="utf-8").strip()
        prompt = (
            "You are operating as Evergrowth's bounded autonomous reasoning provider. "
            "Follow the supplied identity, safety, and task instructions exactly.\n\n"
            + (f"[AUTONOMY POLICY]\n{policy}\n\n" if policy else "")
            + "\n\n".join(rendered)
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable, self.wrapper_path, prompt,
            "--cwd", self.cwd, "--timeout", str(self.timeout),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Hermes delegation failed: {detail or proc.returncode}")
        answer = stdout.decode("utf-8", errors="replace").strip()
        if not answer:
            raise RuntimeError("Hermes delegation returned an empty response")
        return answer


def load_provider(config: dict) -> AIProvider:
    """Load the AI provider from config."""
    provider_type = config.get("provider", "openai").lower()

    if provider_type == "openai":
        api_key = config.get("api_key", "")
        if not api_key:
            # Try reading from environment
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "OpenAI API key required. "
                "Set 'api_key' in config or OPENAI_API_KEY env var."
            )
        return OpenAIProvider(api_key=api_key, model=config.get("model", "gpt-4o"))

    elif provider_type == "anthropic":
        api_key = config.get("api_key", "")
        if not api_key:
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        model = config.get("model", "claude-sonnet-4-20250514")
        return AnthropicProvider(api_key=api_key, model=model)

    elif provider_type == "ollama":
        return OllamaProvider(
            model=config.get("model", "llama3"),
            base_url=config.get("base_url", "http://localhost:11434"),
        )

    elif provider_type == "lmstudio":
        return LMStudioProvider(
            model=config.get("model", "default"),
            base_url=config.get("base_url", "http://localhost:1234"),
        )

    elif provider_type == "hermes":
        return HermesProvider(
            wrapper_path=config.get(
                "wrapper_path", r"C:\Users\susur\Ethan\hermes_delegate.py"
            ),
            cwd=config.get("cwd", r"C:\Users\susur\Ethan"),
            timeout=config.get("timeout", 90),
            model=config.get("model", "gpt-5.6"),
            policy_path=config.get("policy_path", ""),
        )

    else:
        raise ValueError(f"Unknown provider: {provider_type}")
