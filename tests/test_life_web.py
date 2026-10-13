from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from pma.life_web import ROOT, LifeDataset
from pma.web import create_app


def test_isolated_seed_and_catalog(settings, models, monkeypatch, tmp_path):
    import pma.life_web as module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    settings = replace(settings, data_dir=tmp_path / '.local/life-web')
    dataset = LifeDataset(ROOT / 'data/life_diagnostics.json')
    app = create_app(settings, models, run_worker=False, test_dataset=dataset)
    with TestClient(app, base_url=settings.origin) as client:
        assert client.get('/api/v1/test-dataset').status_code == 401
        response = client.post('/api/v1/session', json={'token': app.state.bootstrap_token},
                               headers={'Origin': settings.origin})
        assert response.status_code == 200
        data = client.get('/api/v1/test-dataset').json()
        assert len(data['records']) == 300
        assert len(data['questions']) == 600
        assert all(r['status'] == 'queued' for r in data['records'])
        first = dataset.mapping.copy()
        dataset.prepare(app.state.store, settings)
        assert dataset.mapping == first
        with app.state.store.connect() as db:
            assert db.execute('SELECT count(*) FROM records').fetchone()[0] == 300


def test_refuses_personal_database(settings, store):
    dataset = LifeDataset(ROOT / 'data/life_diagnostics.json')
    with pytest.raises(ValueError, match='isolated'):
        dataset.prepare(store, settings)
