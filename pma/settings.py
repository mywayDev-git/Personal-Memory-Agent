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
    embedding_profile: str = field(default="raw-v1", kw_only=True)
    answer_validation: bool = False
    evaluation_enabled: bool = False
    evaluation_details: bool = False
    context_tokens: int = 16384
    llm: Settings = field(default_factory=Settings)
    diagnostics: bool = field(default=False, kw_only=True)
    diagnostics_path: str | Path | None = field(default=None, kw_only=True)
    chat_timeout: float = field(default=300, kw_only=True)
    request_token_cache: bool = field(default=False, kw_only=True)
    request_reuse: bool = field(default=False, kw_only=True)
    source_stop_drafts: bool = field(default=True, kw_only=True)
    selection_batch_size: int = field(default=4, kw_only=True)
    chat_presentation: str = field(default="reviewed", kw_only=True)
    # None preserves the legacy bundled request_reuse switch.
    selection_reuse: bool | None = field(default=None, kw_only=True)
    explicit_context_shortcut: bool | None = field(default=None, kw_only=True)
    prompt_cache: bool | None = field(default=None, kw_only=True)
    compact_search_planning: bool = field(default=False, kw_only=True)
    fair_model_scheduling: bool = field(default=False, kw_only=True)
    compact_model_ids: bool = field(default=False, kw_only=True)
    source_fact_drafts: bool = field(default=False, kw_only=True)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.port}"

    @property
    def embedding_key(self):
        key = f"{self.embedding_model}:{self.embedding_revision}:{self.embedding_dimensions}"
        return key if self.embedding_profile == "raw-v1" else f"{key}:{self.embedding_profile}"

    def validate(self):
        if self.embedding_profile not in {"raw-v1", "qwen3-retrieval-v1"}:
            raise ValueError("INVALID_EMBEDDING_PROFILE")
        if self.selection_batch_size not in {4, 8} or self.chat_presentation not in {"reviewed", "plain"}:
            raise ValueError("INVALID_RESPONSE_OPTIMIZATION")
        if not 0 < self.chat_timeout <= 3600:
            raise ValueError("INVALID_CHAT_TIMEOUT")
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
            embedding_profile=os.getenv("PMA_EMBEDDING_PROFILE", "raw-v1"),
            answer_validation=os.getenv("PMA_ANSWER_VALIDATION", "0") == "1",
            evaluation_enabled=os.getenv("PMA_EVALUATION", "0") == "1",
            evaluation_details=os.getenv("PMA_EVALUATION_DETAILS", "0") == "1",
            context_tokens=int(os.getenv("PMA_CONTEXT_TOKENS", "16384")),
            llm=Settings.from_env(),
            diagnostics=os.getenv("PMA_DIAGNOSTICS", "0") == "1",
            # Preserve the supplied path without filesystem access. A bad logging
            # destination must not prevent startup; the collector handles failure.
            diagnostics_path=os.getenv("PMA_DIAGNOSTICS_PATH") or None,
            chat_timeout=float(os.getenv("PMA_CHAT_TIMEOUT", "300")),
            request_token_cache=os.getenv("PMA_REQUEST_TOKEN_CACHE", "0") == "1",
            request_reuse=os.getenv("PMA_REQUEST_REUSE", "0") == "1",
            source_stop_drafts=os.getenv("PMA_SOURCE_STOP_DRAFTS", "1") == "1",
            selection_batch_size=int(os.getenv("PMA_SELECTION_BATCH_SIZE", "4")),
            chat_presentation=os.getenv("PMA_CHAT_PRESENTATION", "reviewed"),
            selection_reuse=(os.getenv("PMA_SELECTION_REUSE") == "1"
                             if "PMA_SELECTION_REUSE" in os.environ else None),
            explicit_context_shortcut=(os.getenv("PMA_CONTEXT_SHORTCUT") == "1"
                                       if "PMA_CONTEXT_SHORTCUT" in os.environ else None),
            prompt_cache=(os.getenv("PMA_PROMPT_CACHE") == "1"
                          if "PMA_PROMPT_CACHE" in os.environ else None),
            compact_search_planning=os.getenv("PMA_COMPACT_SEARCH_PLANNING", "0") == "1",
            fair_model_scheduling=os.getenv("PMA_FAIR_MODEL_SCHEDULING", "0") == "1",
            compact_model_ids=os.getenv("PMA_COMPACT_MODEL_IDS", "0") == "1",
            source_fact_drafts=os.getenv("PMA_SOURCE_FACT_DRAFTS", "0") == "1",
        )
        result.validate()
        return result
