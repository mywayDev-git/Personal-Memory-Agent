"""Import only completed, hash-checked synthetic conversation anchors.

This does not establish that the target device can prepare the conversation.
It holds the full prior input constant for CPU/GPU response measurements.
"""

import hashlib
import json
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_anchor(results_path, name, case, target, *, documents, hashes,
                  fixture_split, fixture_sha256, keys, score):
    from pma.chat.store import ChatStore
    from pma.store import Store

    document = json.loads(results_path.read_text('utf-8'))
    config = document.get('configuration', {})
    anchor = document.get('anchors', {}).get(name, {})
    if (not document.get('execution_completed') or not document.get('source_unchanged')
            or not document.get('evaluator_unchanged') or not anchor.get('quality', {}).get('passed')
            or config.get('fixture_split') != fixture_split
            or config.get('fixture_manifest_sha256') != fixture_sha256
            or any(document.get('hashes', {}).get(k) != hashes[k] for k in ('generation', 'embedding'))):
        raise ValueError('UNVERIFIED_SYNTHETIC_ANCHOR_PROVENANCE')
    source = results_path.parent / f'{name}-anchor.db'
    if not source.is_file() or digest(source) != anchor.get('sha256'):
        raise ValueError('SYNTHETIC_ANCHOR_HASH_MISMATCH')
    if target.exists():
        raise ValueError('ANCHOR_TARGET_EXISTS')
    shutil.copy2(source, target)
    store = Store(target)
    with store.connect() as db:
        revisions = db.execute('SELECT record_id,text FROM revisions').fetchall()
        if (sorted(row[1] for row in revisions) != sorted(row[1] for row in documents)
                or {row[0] for row in revisions} != set(keys)):
            raise ValueError('ANCHOR_IS_NOT_THE_SYNTHETIC_FIXTURE')
    chat = ChatStore(store)
    sessions = chat.list()['items']
    if len(sessions) != 1:
        raise ValueError('ANCHOR_SESSION_COUNT')
    session = chat.get(sessions[0]['id'])
    messages = session['messages']
    if (len(messages) != 1 or messages[0]['state'] != 'completed' or messages[0].get('error_code')
            or messages[0]['question'] != case['anchor']):
        raise ValueError('INVALID_SHARED_ANCHOR_TURN')
    quality = score(case, messages[0]['response'], messages[0]['evidence'], keys)
    if not quality['passed']:
        raise ValueError('INVALID_SHARED_ANCHOR_QUALITY')
    store.checkpoint()
    return session['id'], {'quality': quality, 'sha256': digest(target),
        'shared_between_variants': True, 'imported_checked_history': True,
        'template_results_sha256': digest(results_path), 'template_anchor_sha256': digest(source),
        'template_placement': config.get('placement'), 'target_device_preparation_verified': False}
