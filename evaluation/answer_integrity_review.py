"""Real fresh reviews of frozen valid/altered synthetic answers, opt-in only."""

import json
import time
from pathlib import Path

from pma.answer_review import accepted
from pma.chat.evidence import review_spans_supported
from scripts.memory_agent.llm_client import request_budget
from .answer_integrity_cases import load


def evaluate(models, artifact_path=None, *, before_call=None, split='development'):
    documents, _, manifest = load(split)
    filename = 'identity_cause_v2_cases.json' if split.startswith('v2_') else 'answer_integrity_cases.json'
    pairs = json.loads(Path(__file__).with_name(filename).read_text('utf-8'))['splits'][split.removeprefix('v2_')]['review_pairs']
    evidence = [{'id': row[0], 'source_text': row[1]} for row in documents]
    rows, artifacts = [], []
    for pair in pairs:
        for expected, key in ((True, 'valid'), (False, 'invalid')):
            if before_call:
                before_call()
            response = {'status': 'answered', 'items': pair.get(key + '_items', [pair[key]])}
            row = {'pair': pair['id'], 'expected_approval': expected}
            started = time.perf_counter()
            checked = None
            with request_budget(300) as budget:
                try:
                    checked = models.review(pair['question'], evidence, response)
                    row['approved'] = bool(accepted(checked, response) and review_spans_supported(response, checked, evidence))
                except ValueError as exc:
                    row.update(approved=False, error_code=type(exc).__name__, error_reason=str(exc))
            row.update(seconds=time.perf_counter()-started, model_calls=sum(
                call['operation'] == '/v1/chat/completions' for call in budget.calls), transport_calls=budget.calls)
            row['passed'] = row['approved'] == expected and 'error_code' not in row
            rows.append(row)
            artifacts.append({'question': pair['question'], 'source_records': evidence,
                              'proposed_answer': response, 'review': checked, **row})
            if artifact_path:
                path = Path(artifact_path)
                pending = path.with_suffix('.partial')
                pending.write_text(json.dumps(artifacts, ensure_ascii=False, indent=2), encoding='utf-8')
                pending.replace(path)
    return {'fixture_sha256': manifest['sha256'], 'split': split, 'rows': rows,
            'false_approvals': sum(row['approved'] and not row['expected_approval'] for row in rows),
            'false_rejections': sum(not row['approved'] and row['expected_approval'] for row in rows),
            'passed': all(row['passed'] for row in rows)}
