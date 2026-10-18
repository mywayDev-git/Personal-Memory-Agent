from fastapi.testclient import TestClient

from pma.web import create_app


def test_console_mode_shows_real_pipeline(settings, models, capsys):
    app = create_app(settings, models, run_worker=False, console_test=True)
    with TestClient(app, base_url=settings.origin) as client:
        client.headers['Origin'] = settings.origin
        response = client.post('/api/v1/session', json={'token': app.state.bootstrap_token})
        client.headers['X-CSRF-Token'] = response.json()['csrf']
        assert client.post('/api/v1/records', json={'text': '담당자를 정했다.'}).status_code == 202
        app.state.service.run_one()
        response = client.post('/api/v1/answers', json={'question': '어떻게 했지?'})
        assert response.status_code == 200
        output = capsys.readouterr().out
        for expected in ['원문 저장 완료', '기억 추출·검증 완료', '검색 벡터 저장 완료',
                         '어떻게 했지?', '키워드:', '최종 근거 1개', '담당자를 정했다.']:
            assert expected in output
        assert app.state.bootstrap_token not in output


def test_default_does_not_print_contents(client, capsys):
    client.post('/api/v1/records', json={'text': '담당자를 정했다.'})
    client.app.state.service.run_one()
    client.post('/api/v1/search', json={'question': '어떻게 했지?'})
    assert capsys.readouterr().out == ''


def test_empty_search_is_visible(settings, models, capsys):
    app = create_app(settings, models, run_worker=False, console_test=True)
    with TestClient(app, base_url=settings.origin):
        app.state.service.search('없는 기록')
        assert '최종 근거 0개' in capsys.readouterr().out
