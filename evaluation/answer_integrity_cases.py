"""Hash-checked synthetic cases frozen before occupation integrity repair."""

import hashlib
import json
from pathlib import Path


def load(split):
    root = Path(__file__).parent
    raw = (root / 'answer_integrity_cases.json').read_bytes()
    declared = json.loads((root / 'answer_integrity_manifest.json').read_text('utf-8'))
    if hashlib.sha256(raw).hexdigest() != declared['sha256']:
        raise ValueError('Frozen answer integrity fixtures differ')
    data = json.loads(raw)['splits'][split]
    return data['documents'], data['cases'], declared
