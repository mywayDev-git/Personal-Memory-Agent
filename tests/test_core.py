import json
import subprocess
import sys

import numpy as np
import pytest
from conftest import memory

from config.settings import Settings, paths
from evaluation.metrics import calculate_metrics
from evaluation.report import calculate_metrics as report_metrics
from evaluation.semantic import check_expected
from pma.models import normalized_vectors
from scripts.memory_agent.llm_client import chat, validate_endpoint
from scripts.memory_agent.pipeline import process_text
from scripts.memory_agent.validator import load_schema


class Session:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status
        self.body = None

    def post(self, url, **kwargs):
        self.body = kwargs

        class Response:
            status_code = self.status

            def json(r):
                return self.payload

        return Response()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/api",
        "http://localhost:80",
        "http://127.0.0.1@evil.com",
        "http://127.0.0.1/a?token=secret",
    ],
)
def test_remote_endpoints_rejected(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)


@pytest.mark.parametrize("message", [None, [], {}, {"content": ""}])
def test_malformed_model_response_safe(message):
    with pytest.raises(ValueError):
        chat(
            Session({"choices": [{"message": message}]}),
            "http://127.0.0.1:8081/v1/chat/completions",
            [],
        )


def test_redirect_and_truncation_not_success():
    import requests

    with pytest.raises(requests.HTTPError):
        chat(Session({}, 302), "http://127.0.0.1:8081/v1/chat/completions", [])
    with pytest.raises(ValueError, match="TRUNCATED"):
        chat(
            Session({"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}]}),
            "http://127.0.0.1:8081/v1/chat/completions",
            [],
        )


def test_pipeline_schema_forwarding_and_clean_stdout(capsys):
    m = memory()
    m.pop("local_id")
    session = Session(
        {
            "choices": [
                {"message": {"content": json.dumps({"memories": [m]})}, "finish_reason": "stop"}
            ]
        }
    )
    schema = load_schema(paths.output_schema)
    result, meta = process_text(
        "담당자를 정했다.",
        {"source_id": "x", "reference_time": None, "language": "ko"},
        prompt="extract",
        output_schema=schema,
        final_schema=load_schema(paths.final_schema),
        session=session,
        settings=Settings(),
    )
    assert session.body["json"]["json_schema"] == schema
    assert session.body["allow_redirects"] is False
    assert result["memories"][0]["local_id"] == "m1"
    assert meta["prompt_hash"]
    assert capsys.readouterr().out == ""


def test_metrics_consistent_and_semantics_separate():
    records = [{"valid": True, "final_schema_valid": True, "evidence_valid": True}]
    assert (
        calculate_metrics(records)["schema_valid_rate"]
        == report_metrics(records, {}, "test")["schema_valid_rate"]
        == 1
    )
    check = check_expected({"min_memory_count": 2}, {"memories": [memory()]})
    assert check["status"] == "fail"
    assert check["human_review_required"] is True


@pytest.mark.parametrize("value", [[[0, 0, 0]], [[1, 2]], [[np.nan, 1, 2]]])
def test_invalid_vectors_rejected(value):
    with pytest.raises(ValueError):
        normalized_vectors(value, 1, 3)


@pytest.mark.parametrize(
    "args",
    [
        ["-m", "scripts.main", "--help"],
        ["scripts/main.py", "--help"],
        ["evaluation/run_eval.py", "--help"],
        ["evaluation/report.py", "--help"],
    ],
)
def test_cli_entrypoints(args):
    r = subprocess.run([sys.executable, "-B", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
