"""Safe, structured failure details: no source or model response in messages."""

import requests

from .exceptions import ExtractionError, SchemaValidationError


class ProcessingError(ValueError):
    def __init__(self, code, stage, **details):
        super().__init__(code)
        self.code = code
        self.diagnostic = dict(code=code, stage=stage, **details)


def failure(exc, stage):
    if isinstance(exc, ProcessingError):
        return exc.code, dict(exc.diagnostic)
    if isinstance(exc, requests.Timeout):
        code = "MODEL_TIMEOUT"
    elif isinstance(exc, requests.ConnectionError):
        code = "MODEL_UNAVAILABLE"
    elif isinstance(exc, requests.HTTPError):
        return "MODEL_HTTP_ERROR", dict(
            code="MODEL_HTTP_ERROR",
            stage=stage,
            http_status=exc.response.status_code if exc.response is not None else None,
        )
    elif isinstance(exc, requests.RequestException):
        code = "MODEL_UNAVAILABLE"
    elif isinstance(exc, ExtractionError):
        code = "MODEL_INVALID_JSON"
    elif isinstance(exc, SchemaValidationError):
        code = "INVALID_SOURCE_CONTEXT"
    elif hasattr(exc, "code"):
        code = exc.code
    else:
        known = {
            "MODEL_TRUNCATED",
            "MODEL_INVALID_JSON",
            "MODEL_INVALID_RESPONSE",
            "MODEL_EMPTY_RESPONSE",
            "INVALID_EXTRACTION_SCHEMA",
            "INVALID_EXTRACTION_EVIDENCE_OR_SCHEMA",
            "INVALID_EMBEDDING",
            "INVALID_EMBEDDING_RESPONSE",
            "VECTOR_COUNT_MISMATCH",
            "INVALID_EVIDENCE",
        }
        code = str(exc) if str(exc) in known else "INTERNAL_PROCESSING_ERROR"
    return code, dict(code=code, stage=stage, exception_type=type(exc).__name__)
