"""Configuration management for Evergrowth."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "default.json"


@dataclass
class HeartbeatConfig:
    enabled: bool = True
    default_interval_minutes: int = 30
    character: str = "\u00a7"
    response_timeout_seconds: int = 480
    initial_delay_minutes: int = 5
    prompt_variations: list[str] = field(default_factory=list)


@dataclass
class MemoryConfig:
    db_path: str = "~/.evergrowth/memory.db"
    session_summary_threshold: int = 1000
    auto_promote_session: bool = True
    max_context_cache_tokens: int = 400


@dataclass
class SkillsConfig:
    skills_path: str = "~/.evergrowth/skills"
    auto_create: bool = True
    improve_on_use: bool = True


@dataclass
class IdentityConfig:
    soul_path: str = "~/.evergrowth/soul"
    vault_path: str = ""
    di_name: str = "Lyra"
    di_letter: str = "L"


@dataclass
class MCPConfig:
    transport: str = "stdio"
    port: int = 8080
    host: str = "localhost"


@dataclass
class ExperimentConfig:
    enabled: bool = True
    ledger_path: str = "~/.evergrowth/experiments.jsonl"
    default_budget_seconds: float = 300.0
    max_experiments_per_cycle: int = 3


@dataclass
class SchedulerConfig:
    enabled: bool = True
    max_concurrent: int = 5


@dataclass
class TrayConfig:
    enabled: bool = True
    active_color: str = "#FF4444"
    inactive_color: str = "#44BB44"


@dataclass
class EvergrowthConfig:
    di_name: str = "Lyra"
    di_letter: str = "L"
    data_dir: str = "~/.evergrowth"
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    experiments: ExperimentConfig = field(default_factory=ExperimentConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)

    def resolve_data_dir(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()

    def resolve_soul_path(self) -> Path:
        return Path(self.identity.soul_path).expanduser().resolve()

    def resolve_memory_path(self) -> Path:
        return Path(self.memory.db_path).expanduser().resolve()

    def resolve_skills_path(self) -> Path:
        return Path(self.skills.skills_path).expanduser().resolve()

    def resolve_vault_path(self) -> Path | None:
        if not self.identity.vault_path:
            return None
        return Path(self.identity.vault_path).expanduser().resolve()


def _dict_to_dataclass(cls, data: dict) -> Any:
    """Recursively convert a dict to a dataclass."""
    if not isinstance(data, dict):
        return data
    fieldtypes = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for k, v in data.items():
        if k in fieldtypes:
            ft = cls.__dataclass_fields__[k].type
            if hasattr(ft, "__dataclass_fields__") and isinstance(v, dict):
                kwargs[k] = _dict_to_dataclass(ft, v)
            else:
                kwargs[k] = v
    return cls(**kwargs)


def load_config(config_path: str | Path | None = None) -> EvergrowthConfig:
    """Load configuration from JSON file, falling back to defaults."""
    if config_path is None:
        config_path = os.environ.get(
            "EVERGROWTH_CONFIG", str(DEFAULT_CONFIG_PATH)
        )

    path = Path(config_path).expanduser().resolve()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_dataclass(EvergrowthConfig, data)
        except Exception:
            pass

    return EvergrowthConfig()


def save_config(config: EvergrowthConfig, config_path: str | Path | None = None):
    """Save configuration to JSON file."""
    if config_path is None:
        config_path = os.environ.get(
            "EVERGROWTH_CONFIG", str(DEFAULT_CONFIG_PATH)
        )

    path = Path(config_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    import dataclasses
    data = dataclasses.asdict(config)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
