import os
from dataclasses import dataclass, field
from pathlib import Path

# chrome-launcher root: parent of this package (agent/)
_LAUNCHER_ROOT = Path(__file__).resolve().parent.parent


def _launcher_dir() -> str:
    return os.environ.get("CHROME_LAUNCHER_DIR", str(_LAUNCHER_ROOT))


@dataclass
class AgentConfig:
    db_path: str = field(
        default_factory=lambda: os.environ.get(
            "AGENT_DB_PATH", str(_LAUNCHER_ROOT / "agent.db")
        )
    )
    worker_count: int = field(
        default_factory=lambda: int(os.environ.get("AGENT_WORKERS", "3"))
    )
    poll_interval: float = field(
        default_factory=lambda: float(os.environ.get("AGENT_POLL_INTERVAL", "1.0"))
    )
    default_timeout: int = field(
        default_factory=lambda: int(os.environ.get("AGENT_DEFAULT_TIMEOUT", "300"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("AGENT_MAX_RETRIES", "3"))
    )
    retry_base_delay: float = field(
        default_factory=lambda: float(os.environ.get("AGENT_RETRY_BASE_DELAY", "2.0"))
    )
    chrome_launcher_dir: str = field(default_factory=_launcher_dir)
    api_host: str = field(
        default_factory=lambda: os.environ.get("AGENT_API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.environ.get("AGENT_API_PORT", "9227"))
    )
