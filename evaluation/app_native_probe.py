"""Start the real app after a content-free, synthetic C++ dispatch self-test."""

import logging
import os
import sys

from pma.search_explain import (
    _native_matcher,
    keyword_matches_batch,
    keyword_query,
    python_keyword_matches_batch,
)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = [{"text": "합성 제주에 갔다.", "memory": {"content": "합성 제주에 갔다."}}]
    terms, vocabulary = keyword_query("제주", rows)
    native = _native_matcher()
    if native is None:
        raise RuntimeError("Native matcher missing during requested restart verification")
    calls = []
    import pma.search_explain as module

    loader = module._native_matcher

    def invoke(*args):
        calls.append(True)
        return native(*args)

    module._native_matcher = lambda: invoke
    try:
        found = keyword_matches_batch(rows, terms, vocabulary)
    finally:
        module._native_matcher = loader
    assert found == python_keyword_matches_batch(rows, terms, vocabulary) and calls
    logging.info(
        "native_startup_probe pid=%d backend=cpp native_calls=%d equal=true",
        os.getpid(),
        len(calls),
    )
    from pma.__main__ import main as app_main

    return app_main()


if __name__ == "__main__":
    sys.exit(main())
