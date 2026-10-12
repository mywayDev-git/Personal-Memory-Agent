
"""Central configuration for the Personal Memory Agent."""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be an integer."
        ) from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be a number."
        ) from exc


@dataclass(frozen=True)
class Settings:
    """Application configuration."""

    endpoint: str = "http://127.0.0.1:8081/v1/chat/completions"
    model: str | None = None

    timeout: float = 180.0
    max_tokens: int = 4096
    temperature: float = 0.0
    seed: int = 42
    top_p: float = 1.0

    schema_version: str = "4.0"
    language: str = "ko"

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        return cls(
            endpoint=os.getenv(
                "PMA_ENDPOINT",
                cls.endpoint,
            ),
            model=os.getenv("PMA_MODEL") or None,
            timeout=_env_float("PMA_TIMEOUT", 180.0),
            max_tokens=_env_int("PMA_MAX_TOKENS", 4096),
            temperature=_env_float("PMA_TEMPERATURE", 0.0),
            seed=_env_int("PMA_SEED", 42),
            top_p=_env_float("PMA_TOP_P", 1.0),
            schema_version=os.getenv("PMA_SCHEMA_VERSION", "4.0"),
            language=os.getenv("PMA_LANGUAGE", "ko"),
        )


@dataclass(frozen=True)
class Paths:
    """Project file and directory paths."""

    root: Path = PROJECT_ROOT

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def prompt(self) -> Path:
        return self.root / "prompts" / "extraction.txt"

    @property
    def output_schema(self) -> Path:
        return self.root / "schema" / "memory_extraction_output.schema.json"

    @property
    def final_schema(self) -> Path:
        return self.root / "schema" / "memory_extraction.schema.json"

    @property
    def datasets_dir(self) -> Path:
        return self.root / "datasets"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"


settings = Settings.from_env()
paths = Paths()
