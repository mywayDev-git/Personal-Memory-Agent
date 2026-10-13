"""Isolated, explicitly launched synthetic web playground."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


class LifeDataset:
    def __init__(self, path, cache_dir=None):
        raw = Path(path).read_bytes()
        self.data = json.loads(raw)
        if self.data.get('synthetic') is not True:
            raise ValueError('Only synthetic datasets are allowed')
        self.mapping = {}
        self.cache = {}
        self.revision = None
        if cache_dir:
            directory = Path(cache_dir)
            manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
            if manifest['dataset_sha256'] != hashlib.sha256(raw).hexdigest():
                raise ValueError('Evaluation cache does not match this dataset')
            self.revision = manifest['embedding_revision']
            self.cache = json.loads((directory / 'extractions.json').read_text(encoding='utf-8'))

    def prepare(self, store, settings):
        # The launcher fixes this directory; never seed the personal database.
        if settings.data_dir.resolve() != (ROOT / '.local/life-web').resolve():
            raise ValueError('Synthetic playground requires its isolated data directory')
        if self.cache and settings.embedding_revision != self.revision:
            raise ValueError('Embedding model differs from the evaluation cache')
        original_clock = store.clock
        try:
            # Publish cached real extractions before queueing the remaining sources.
            sources = sorted(self.data['records'], key=lambda r: not bool(self.cache.get(r['id'])))
            for source in sources:
                with store.connect() as db:
                    existing = db.execute(
                        'SELECT record_id FROM revisions WHERE version=1 AND text=? AND reference_time=?',
                        (source['text'], source['reference_time']),
                    ).fetchone()
                if existing:
                    self.mapping[source['id']] = existing['record_id']
                    continue
                store.clock = lambda s=source: s['recorded_at']
                result = store.create(source['text'], source['reference_time'])
                self.mapping[source['id']] = result['record_id']
                cached = self.cache.get(source['id'])
                if cached:
                    job = store.claim()
                    if job['record_id'] != result['record_id']:
                        raise RuntimeError('Unexpected pending job during cache import')
                    if cached['status'] in ('ready', 'ready_empty'):
                        store.publish(job, cached['memories'], np.asarray(cached['vectors']),
                                      settings.embedding_key, {'synthetic_replay': True})
                    else:
                        store.fail(job, cached.get('error_code') or 'EXTRACTION_INVALID')
        finally:
            store.clock = original_clock

    def view(self, store):
        with store.connect() as db:
            statuses = {r['id']: r['status'] for r in db.execute('SELECT id,status FROM records')}
        records = [dict(r, record_id=self.mapping[r['id']],
                        status=statuses.get(self.mapping[r['id']], 'deleted'))
                   for r in self.data['records']]
        return dict(enabled=True, today=self.data['today'], records=records,
                    questions=self.data['questions'])
