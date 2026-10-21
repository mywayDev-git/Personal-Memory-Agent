"""Hash-checked synthetic cases frozen before occupation integrity repair."""

import hashlib
import json
from pathlib import Path


def load(split):
    root = Path(__file__).parent
    if split.startswith('v2_'):
        raw = (root / 'identity_cause_v2_cases.json').read_bytes()
        declared = json.loads((root / 'identity_cause_v2_manifest.json').read_text('utf-8'))
        if hashlib.sha256(raw).hexdigest() != declared['sha256']:
            raise ValueError('Frozen identity/cause v2 fixtures differ')
        data = json.loads(raw)['splits'][split.removeprefix('v2_')]
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
