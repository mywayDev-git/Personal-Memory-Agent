from types import SimpleNamespace

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from pma.chat.api import router
from tests.http_client import TestClient


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Query(StrictInput):
    question: str


def test_browser_mode_strings_are_accepted_but_invalid_modes_are_rejected():
    app = FastAPI()
    app.include_router(router(StrictInput, Query))
    app.state.chat = SimpleNamespace(message=lambda *args: {'mode': args[-1]})
    with TestClient(app) as client:
        for mode in ('auto', 'general', 'memory', 'hybrid'):
            response = client.post('/api/v1/chat/sessions/test/messages', json={
                'request_id': 'test', 'question': 'hello', 'mode': mode})
            assert response.status_code == 200, response.text
            assert response.json()['mode'] == mode
        for mode in ('invalid', 1, None, []):
            response = client.post('/api/v1/chat/sessions/test/messages', json={
                'request_id': 'test', 'question': 'hello', 'mode': mode})
            assert response.status_code == 422
