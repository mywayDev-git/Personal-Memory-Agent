import pytest

from pma.errors import AppError
from pma.service import Service


def test_api_record_workflow(client):
    r = client.post("/api/v1/records", json={"text": "담당자를 정했다."})
    assert r.status_code == 202
    rid = r.json()["record_id"]
    client.app.state.service.run_one()
    assert client.get("/api/v1/records/" + rid).json()["status"] == "ready"
    answer = client.post("/api/v1/answers", json={"question": "어떻게 했지?"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "answered"
    assert answer.json()["items"][0]["citations"][0] == answer.json()["results"][0]["id"]
    assert client.delete("/api/v1/records/" + rid).status_code == 204
    assert (
        client.post("/api/v1/answers", json={"question": "어떻게 했지?"}).json()["status"]
        == "insufficient_evidence"
    )
    assert client.post("/api/v1/records/" + rid + "/restore", json={}).status_code == 202


def test_auth_csrf_origin_and_host(client):
    assert client.get("/api/v1/health", headers={"Host": "evil.test"}).status_code == 403
    assert client.get("/api/v1/health", headers={"Origin": "https://evil.test"}).status_code == 403
    assert (
        client.post("/api/v1/records", json={"text": "x"}, headers={"X-CSRF-Token": ""}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/session", json={"token": client.app.state.bootstrap_token}).status_code
        == 401
    )
    client.cookies.clear()
    assert client.get("/api/v1/session").status_code == 401
    assert client.get("/api/v1/records").status_code == 401


@pytest.mark.parametrize(
    "data",
    [
        {"text": ""},
        {"text": " "},
        {"text": "x" * 4001},
        {"text": "x", "reference_time": "2026-01-01"},
        {"text": "x", "unexpected": "value"},
    ],
)
def test_invalid_input_never_saved(client, data):
    assert client.post("/api/v1/records", json=data).status_code == 422
    assert client.get("/api/v1/records").json()["items"] == []


def test_no_model_error_body_leaks(client, models):
    models.understand = lambda *a: (_ for _ in ()).throw(ValueError("PRIVATE SECRET"))
    response = client.post("/api/v1/answers", json={"question": "PRIVATE QUESTION"})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert "PRIVATE SECRET" not in response.text


def test_source_deleted_during_answer_rejected(store, models, settings):
    service = Service(store, models, settings)
    rid = store.create("담당자를 정했다.", None)["record_id"]
    service.run_one()
    models.after_answer = lambda: store.trash(rid)
    with pytest.raises(AppError) as exc:
        service.answer("질문")
    assert exc.value.code == "SOURCE_CHANGED"


def test_forged_citation_rejected(store, models, settings):
    service = Service(store, models, settings)
    store.create("담당자를 정했다.", None)
    service.run_one()
    models.invalid_citation = True
    with pytest.raises(ValueError, match="INVALID_CITATION"):
        service.answer("질문")


def test_unknown_time_excluded_and_aggregate_unsupported(store, models, settings):
    service = Service(store, models, settings)
    store.create("담당자를 정했다.", None)
    service.run_one()
    assert service.search("질문", {"date_from": "2026-01-01", "date_to": None})["results"] == []
    models.intent = "aggregate"
    assert service.answer("몇 번?")["status"] == "unsupported_intent"


def test_other_embedding_model_not_mixed(store, models, settings):
    service = Service(store, models, settings)
    store.create("담당자를 정했다.", None)
    service.run_one()
    assert store.snapshot("other-model")[1] == []


def test_html_security_headers_and_body_limit(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"
    r = client.post(
        "/api/v1/records", content="x" * 65537, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422

def test_processing_progress_current_revisions_and_auth(client):
    store = client.app.state.store
    rid = store.create('진행 상태 확인용 기록', None)['record_id']
    response = client.get('/api/v1/processing').json()
    assert response['remaining'] == response['queued'] == 1
    job = store.claim()
    response = client.get('/api/v1/processing').json()
    assert response['processing'] == 1
    assert response['remaining'] == 1
    assert response['recent'][0]['status'] == 'running'
    assert 'token' not in response['recent'][0]
    store.fail(job, 'MODEL_TIMEOUT')
    response = client.get('/api/v1/processing').json()
    assert response['remaining'] == 0
    assert response['failed'] == 1
    store.trash(rid)
    response = client.get('/api/v1/processing').json()
    assert response['total'] == 0
    assert response['recent'] == []
    client.cookies.clear()
    assert client.get('/api/v1/processing').status_code == 401


def test_processing_phase_cleared_after_job(client, monkeypatch):
    service = client.app.state.service
    observed = []
    original = service.models.extract
    def extract(*args):
        observed.append(service.processing_status['phase'])
        return original(*args)
    monkeypatch.setattr(service.models, 'extract', extract)
    service.store.create('담당자를 정했다.', None)
    service.run_one()
    assert observed == ['extract']
    assert service.processing_status is None
    result = client.get('/api/v1/processing').json()
    assert result['completed'] == 1
    assert result['remaining'] == 0


def test_failed_list_bulk_retry_and_stale_requests(client):
    store = client.app.state.store
    records = [store.create(text, None)['record_id'] for text in ('통신 실패 기록', '다른 실패 기록')]
    for _ in records:
        store.fail(store.claim(), 'MODEL_UNAVAILABLE')
    items = client.get('/api/v1/failures').json()['items']
    assert len(items) == 2
    assert all(set(i) == {'job_id', 'record_id', 'version', 'text', 'error_code', 'updated_at', 'diagnostic', 'history'} for i in items)
    ids = [i['job_id'] for i in items]
    assert client.post('/api/v1/failures/retry', json={'job_ids':ids}, headers={'X-CSRF-Token':''}).status_code == 403
    first = client.post('/api/v1/failures/retry', json={'job_ids':ids + ids}).json()
    assert first == {'queued':2, 'skipped':0}
    assert client.get('/api/v1/failures').json()['items'] == []
    assert client.post('/api/v1/failures/retry', json={'job_ids':ids}).json() == {'queued':0, 'skipped':2}
    for _ in records:
        store.fail(store.claim(), 'EXTRACTION_INVALID')
    # An old snapshot cannot retry a newly failed attempt, even on the same revision.
    assert client.post('/api/v1/failures/retry', json={'job_ids':ids}).json() == {'queued':0, 'skipped':2}
    new_items = client.get('/api/v1/failures').json()['items']
    store.trash(new_items[0]['record_id'])
    result = client.post('/api/v1/failures/retry', json={'job_ids':[i['job_id'] for i in new_items]}).json()
    assert result == {'queued':1, 'skipped':1}
    client.cookies.clear()
    assert client.get('/api/v1/failures').status_code == 401
