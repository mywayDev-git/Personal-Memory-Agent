import logging
import sqlite3

import pytest
import requests

from pma.console_trace import ConsoleTrace
from pma.errors import AppError
from pma.service import Service


class OneIteration:
    def __init__(self):
        self.done = False

    def is_set(self):
        return self.done

    def wait(self, seconds):
        self.done = True


def test_busy_worker_is_silent_and_preserves_queue(store, models, settings, caplog, capsys):
    record = store.create('담당자를 정했다.', None)
    service = Service(store, models, settings, diagnostic_sink=ConsoleTrace())
    service.stop_event = OneIteration()
    with service.gate:
        service.loop()
    assert not caplog.records
    assert capsys.readouterr().out == ''
    assert store.claim()['record_id'] == record['record_id']


@pytest.mark.parametrize(('exc', 'code', 'reason'), [
    (sqlite3.OperationalError('PRIVATE SECRET'), 'DB_ERROR', '데이터베이스'),
    (PermissionError('PRIVATE SECRET'), 'FILE_PERMISSION', '권한'),
    (RuntimeError('PRIVATE SECRET'), 'INTERNAL_PROCESSING_ERROR', '확정할 수 없습니다'),
    (AppError('MODEL_BUSY', 'PRIVATE SECRET'), 'INTERNAL_PROCESSING_ERROR', '확정할 수 없습니다'),
])
def test_real_failure_explained_without_private_message(
    store, models, settings, caplog, capsys, monkeypatch, exc, code, reason,
):
    def fail():
        raise exc
    monkeypatch.setattr(store, 'rebuild_facts', fail)
    service = Service(store, models, settings, diagnostic_sink=ConsoleTrace())
    service.stop_event = OneIteration()
    with caplog.at_level(logging.ERROR):
        service.loop()
    output = capsys.readouterr().out
    assert '검색 자료 재구축' in output
    assert code in output and reason in output and '해결 방법:' in output
    assert 'worker_iteration_failed' in caplog.text
    assert 'PRIVATE SECRET' not in output + caplog.text


def test_model_failure_has_remedy(store, models, settings, capsys):
    store.create('담당자를 정했다.', None)
    models.failure = requests.ConnectionError('PRIVATE SECRET')
    service = Service(store, models, settings, diagnostic_sink=ConsoleTrace())
    service.run_one()
    output = capsys.readouterr().out
    assert 'MODEL_UNAVAILABLE' in output
    assert '서버가 실행 중인지' in output
    assert '원문은 보관' in output
    assert 'PRIVATE SECRET' not in output
    assert service.worker_paused
