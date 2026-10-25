"""Runtime configuration for the multi-model context protocol stack."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ModelEndpoint:
    """One callable model backend."""

    name: str
    provider: str  # llama_cpp | openai_compat | mmdeploy
    model: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    roles: List[str] = field(default_factory=lambda: ["chat"])
    max_tokens: int = 2048
    temperature: float = 0.2
    timeout_s: float = 120.0
    priority: int = 100  # lower = preferred
    enabled: bool = True

    def api_key(self) -> Optional[str]:
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env) or None


@dataclass
class MMCPConfig:
    """Production knobs for MCP server, routing, HAR, and vision."""

    server_name: str = "termux-agent-mmcp"
    server_version: str = "1.0.0"
    transport: str = field(default_factory=lambda: os.environ.get("MMCP_TRANSPORT", "stdio"))
    http_host: str = field(default_factory=lambda: os.environ.get("MMCP_HOST", "127.0.0.1"))
    http_port: int = field(default_factory=lambda: int(os.environ.get("MMCP_PORT", "8765")))

    default_role: str = "chat"
    fallback_enabled: bool = True
    max_retries: int = 2
    circuit_fail_threshold: int = 3
    circuit_cooldown_s: float = 30.0

    llama_cli: str = field(
        default_factory=lambda: os.environ.get("LLAMA_CLI", "llama-cli")
    )
    llama_model_dir: str = field(
        default_factory=lambda: os.environ.get(
            "LLAMA_MODEL_DIR",
            os.path.expanduser("~/llama.cpp/models"),
        )
    )
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )

    mmdeploy_model_path: str = field(
        default_factory=lambda: os.environ.get("MMDEPLOY_MODEL", "")
    )
    mmdeploy_device: str = field(
        default_factory=lambda: os.environ.get("MMDEPLOY_DEVICE", "cpu")
    )
    mmdeploy_backend: str = field(
        default_factory=lambda: os.environ.get("MMDEPLOY_BACKEND", "onnxruntime")
    )

    har_max_entries: int = 10_000
    har_max_body_bytes: int = 512_000
    har_capture_bodies: bool = True
    har_redact_secrets: bool = True
    har_multi_tab: bool = True
    chrome_debug_port: int = field(
        default_factory=lambda: int(os.environ.get("CHROME_DEBUG_PORT", "9222"))
    )

    use_langgraph: bool = field(
        default_factory=lambda: _env_bool("MMCP_USE_LANGGRAPH", True)
    )
    use_mmdeploy: bool = field(
        default_factory=lambda: _env_bool("MMCP_USE_MMDEPLOY", True)
    )

    models: List[ModelEndpoint] = field(default_factory=list)

    def resolve_models(self) -> List[ModelEndpoint]:
        if self.models:
            return [m for m in self.models if m.enabled]
        built: List[ModelEndpoint] = []
        # Local GGUF (Termux / llama.cpp) — always preferred when present
        built.append(
            ModelEndpoint(
                name="local-llama",
                provider="llama_cpp",
                model=os.environ.get("LLAMA_MODEL", ""),
                roles=["chat", "plan", "extract"],
                priority=10,
            )
        )
        if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
            built.append(
                ModelEndpoint(
                    name="openai-compat",
                    provider="openai_compat",
                    model=self.openai_model,
                    base_url=self.openai_base_url,
                    api_key_env="OPENAI_API_KEY",
                    roles=["chat", "plan", "extract", "vision"],
                    priority=50,
                )
            )
        if self.use_mmdeploy and self.mmdeploy_model_path:
            built.append(
                ModelEndpoint(
                    name="mmdeploy-vision",
                    provider="mmdeploy",
                    model=self.mmdeploy_model_path,
                    roles=["vision", "detect"],
                    priority=20,
                )
            )
        return [m for m in built if m.enabled]


def load_config() -> MMCPConfig:
    return MMCPConfig()
