import json

from evaluation.openvino_server import error_location


def test_gateway_failure_location_never_includes_prompt_or_exception_contents():
    try:
        raise TypeError("private source or model output")
    except TypeError as exc:
        value = error_location(exc)
    assert value["error"] == "TypeError"
    assert value["file"] == "test_openvino_gateway_diagnostics.py"
    assert isinstance(value["line"], int) and value["line"] > 0
    assert "private source" not in json.dumps(value)
