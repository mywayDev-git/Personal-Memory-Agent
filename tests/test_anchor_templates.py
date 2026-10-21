import json

import pytest

from evaluation.anchor_templates import digest, import_anchor
from pma.chat.store import ChatStore
from pma.store import Store


def setup_anchor(tmp_path):
    source = tmp_path / 'example-anchor.db'
    store = Store(source)
    record = store.create('동아리 친구 민수는 교사다.', '2026-10-19T09:00:00+09:00')
    chat = ChatStore(store)
    sid = chat.create_empty()['id']
    mid, _ = chat.begin(sid, 'anchor', '동아리 친구 민수는 누구야?')
    with store.connect(True) as db:
        db.execute("UPDATE chat_messages SET state='completed',response=? WHERE id=?",
                   (json.dumps({'status': 'answered', 'items': []}), mid))
    store.checkpoint()
    raw = tmp_path / 'results.json'
    document = {'execution_completed': True, 'source_unchanged': True, 'evaluator_unchanged': True,
        'configuration': {'fixture_split': 'development', 'fixture_manifest_sha256': 'fixed', 'placement': 'gpu'},
        'hashes': {'generation': 'qwen', 'embedding': 'bge'},
        'anchors': {'example': {'quality': {'passed': True}, 'sha256': digest(source)}}}
    raw.write_text(json.dumps(document), encoding='utf-8')
    kwargs = dict(documents=[('club', '동아리 친구 민수는 교사다.')],
        hashes={'generation': 'qwen', 'embedding': 'bge'}, fixture_split='development',
        fixture_sha256='fixed', keys={record['record_id']: 'club'}, score=lambda *a: {'passed': True})
    return raw, document, kwargs, sid


def test_import_preserves_checked_source_without_model_calls_or_modifying_template(tmp_path):
    raw, _, kwargs, sid = setup_anchor(tmp_path)
    source = tmp_path / 'example-anchor.db'
    before = source.read_bytes()
    actual, metadata = import_anchor(raw, 'example', {'anchor': '동아리 친구 민수는 누구야?'},
                                     tmp_path / 'copy.db', **kwargs)
    assert actual == sid
    assert metadata['template_placement'] == 'gpu'
    assert metadata['target_device_preparation_verified'] is False
    assert metadata['template_anchor_sha256'] == digest(source)
    assert source.read_bytes() == before


@pytest.mark.parametrize('change', ['hash', 'model', 'fixture', 'incomplete', 'wrong_turn', 'source', 'quality'])
def test_mismatched_unchecked_or_different_inputs_cannot_be_imported(tmp_path, change):
    raw, document, kwargs, _ = setup_anchor(tmp_path)
    case = {'anchor': '동아리 친구 민수는 누구야?'}
    if change == 'hash': document['anchors']['example']['sha256'] = 'wrong'
    if change == 'model': kwargs['hashes']['embedding'] = 'another'
    if change == 'fixture': kwargs['fixture_sha256'] = 'another'
    if change == 'incomplete': document['execution_completed'] = False
    if change == 'wrong_turn': case['anchor'] = '회사 동료 민수는 누구야?'
    if change == 'source': kwargs['documents'] = [('club', 'unrelated source')]
    if change == 'quality': kwargs['score'] = lambda *a: {'passed': False}
    raw.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(ValueError):
        import_anchor(raw, 'example', case, tmp_path / 'copy.db', **kwargs)
