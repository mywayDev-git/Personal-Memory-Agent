"""Hash-checked synthetic cases frozen before occupation integrity repair."""

import hashlib
import json
from pathlib import Path


def load(split):
    root = Path(__file__).parent
    if split.startswith('source_'):
        raw = (root / 'source_completion_cases.json').read_bytes()
        declared = json.loads((root / 'source_completion_manifest.json').read_text('utf-8'))
        if hashlib.sha256(raw).hexdigest() != declared['sha256']:
            raise ValueError('Frozen source completion fixtures differ')
        data = json.loads(raw)['splits'][split.removeprefix('source_')]
        return data['documents'], data['cases'], declared
    if split.startswith(('v2_', 'v3_')):
        version, split_name = split.split('_', 1)
        raw = (root / f'identity_cause_{version}_cases.json').read_bytes()
        declared = json.loads((root / f'identity_cause_{version}_manifest.json').read_text('utf-8'))
        if hashlib.sha256(raw).hexdigest() != declared['sha256']:
            raise ValueError(f'Frozen identity/cause {version} fixtures differ')
        data = json.loads(raw)['splits'][split_name]
        return data['documents'], data['cases'], declared
    if split == 'supplement':
        raw = (root / 'answer_integrity_supplement.json').read_bytes()
        declared = json.loads((root / 'answer_integrity_supplement_manifest.json').read_text('utf-8'))
        if hashlib.sha256(raw).hexdigest() != declared['sha256']:
            raise ValueError('Frozen supplemental fixtures differ')
        data = json.loads(raw)
        return data['documents'], data['cases'], declared
    raw = (root / 'answer_integrity_cases.json').read_bytes()
    declared = json.loads((root / 'answer_integrity_manifest.json').read_text('utf-8'))
    if hashlib.sha256(raw).hexdigest() != declared['sha256']:
        raise ValueError('Frozen answer integrity fixtures differ')
    data = json.loads(raw)['splits'][split]
    return data['documents'], data['cases'], declared
