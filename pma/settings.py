import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import Settings
from scripts.memory_agent.llm_client import validate_endpoint


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path = field(
        default_factory=lambda: (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
            / "PersonalMemoryAgent"
        )
    )
    port: int = 8765
    embedding_endpoint: str = "http://127.0.0.1:8082/v1/embeddings"
    embedding_model: str = "bge-m3"
    embedding_revision: str = "unconfigured"
    embedding_dimensions: int = 1024
    context_tokens: int = 16384
    llm: Settings = field(default_factory=Settings)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    @property
    def embedding_key(self):
        return f"{self.embedding_model}:{self.embedding_revision}:{self.embedding_dimensions}"

    def validate(self):
        validate_endpoint(self.llm.endpoint)
        validate_endpoint(self.embedding_endpoint)
        if not 1024 <= self.port <= 65535 or self.embedding_dimensions < 1:
            raise ValueError("INVALID_APP_SETTINGS")
        if self.llm.language != "ko" or self.llm.schema_version != "4.0":
            raise ValueError("Only Korean extraction schema 4.0 is supported.")
        if self.llm.timeout <= 0 or not 0 < self.llm.max_tokens < self.context_tokens:
            raise ValueError("INVALID_MODEL_BUDGET")
        if self.embedding_revision != "unconfigured" and not re.fullmatch(
            r"[a-fA-F0-9]{64}", self.embedding_revision
        ):
            raise ValueError("PMA_EMBEDDING_REVISION must be the model file SHA-256.")

    @classmethod
    def from_env(cls):
        default = cls()
        result = cls(
            data_dir=Path(os.getenv("PMA_DATA_DIR", str(default.data_dir))).resolve(),
            port=int(os.getenv("PMA_PORT", "8765")),
            embedding_endpoint=os.getenv("PMA_EMBEDDING_ENDPOINT", default.embedding_endpoint),
            embedding_model=os.getenv("PMA_EMBEDDING_MODEL", default.embedding_model),
            embedding_revision=os.getenv("PMA_EMBEDDING_REVISION", "unconfigured"),
            embedding_dimensions=int(os.getenv("PMA_EMBEDDING_DIMENSIONS", "1024")),
            context_tokens=int(os.getenv("PMA_CONTEXT_TOKENS", "16384")),
            llm=Settings.from_env(),
        )
        result.validate()
        return result
