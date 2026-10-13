"""Small real-model regression suite; reports observations, not general accuracy."""
import json
import argparse
import sys
import time
from pathlib import Path
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from config.settings import Settings
from scripts.memory_agent.pipeline import extract_document, PipelineOptions


def checks(row):
    """Explicit checks for this small fixture only; inspect JSON for other errors."""
    memories = row.get('result', {}).get('memories', [])
    def matching(*words):
        return [m for m in memories if all(word in m['content'] for word in words)]
    def has(items, **fields):
        return any(all(m.get(k) == v for k,v in fields.items()) for m in items)
    if row['status'] != 'ok':
        return {'extraction_succeeded': False}
    if row['name'] == 'single_event':
        return {'one_event': len(memories) == 1,
                'participants_place_object_preserved': bool(matching('민수','도서관','과제')),
                'correct_date': len(memories) == 1 and memories[0]['time']['start'] == '2026-10-13',
                'object_is_assignment': len(memories) == 1 and '과제' in str(memories[0]['object']['value'])}
    if row['name'] == 'roles_negation_plan':
        books, pens, coffee, plans = matching('책'), matching('펜'), matching('커피'), matching('발표')
        return {'four_independent_memories': len(memories) == 4,
                'book_giver_jihyun': any(m['subject']['value'] == '지현' and m['object']['value'] == '책' for m in books),
                'pen_giver_self': any(m['subject']['kind'] == 'self' and m['object']['value'] == '펜' for m in pens),
                'negation_preserved': has(coffee, assertion_polarity='negated'),
                'plan_date': any(m['memory_type'] == 'plan' and m['time']['start'] == '2026-10-16' for m in plans),
                'plan_object_not_companion': bool(plans) and all(m['object']['value'] != '지도교수님' for m in plans),
                'no_date_leak_to_undated_pen': bool(pens) and all(m['time']['start'] is None for m in pens)}
    if row['name'] == 'previous_long':
        return {label: any(m['time']['start'] == day for m in matching(*words))
                for label,words,day in [('beginning_event', ('민수','과제'),'2026-10-09'),
                                        ('middle_event', ('지현','오해'),'2026-10-10'),
                                        ('ending_plan', ('교수','발표'),'2026-10-16')]}
    return {'schema_and_evidence_valid': row['metadata']['validation']['valid']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['single_event', 'roles_negation_plan', 'previous_long', 'long'])
    args = parser.parse_args()
    suffix = '_'+args.case if args.case else ''
    output = ROOT / 'results' / f'local_accuracy_report{suffix}.json'
    cases = [
        ('single_event', '오늘 민수와 도서관에서 과제를 마쳤다.', '2026-10-13T18:18:00+09:00', 6000),
        ('roles_negation_plan', '어제 지현이 나에게 책을 줬다. 나는 민수에게 펜을 줬다. 커피를 마시지 않았다. 다음 주 금요일에 지도교수님과 발표할 예정이다.', '2026-10-10T12:00:00+09:00', 6000),
    ]
    previous = ROOT / 'results' / 'local_long_input.txt'
    if previous.exists():
        cases.append(('previous_long', previous.read_text(encoding='utf-8'), '2026-10-10T12:00:00+09:00', 6000))
    else:
        cases.append(('long', '\n'.join(f'2026년 10월 {i}일 민수와 도서관에서 과제 {i}번을 마쳤다.' for i in range(1,9)), '2026-10-10T12:00:00+09:00', 500))
    if args.case:
        cases = [case for case in cases if case[0] == args.case]
        if not cases:
            parser.error('선택한 사례의 로컬 입력 파일을 찾을 수 없습니다.')
    report = []
    for name, text, reference, size in cases:
        started = time.time()
        row = dict(name=name, source=text, reference_time=reference, input_bytes=len(text.encode()), status='running')
        report.append(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'START {name}', flush=True)
        class Recorder(requests.Session):
            def post(self, *args, **kwargs):
                response = super().post(*args, **kwargs)
                row.setdefault('responses', []).append(response.json())
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                return response
        try:
            with Recorder() as session:
                session.trust_env = False
                result, metadata = extract_document(text, source_id='accuracy-'+name,
                    reference_time=reference, settings=replace(Settings.from_env(), timeout=1800),
                    options=PipelineOptions(chunk_bytes=size), session=session)
            row.update(status='ok', result=result, metadata=metadata)
        except Exception as exc:
            row.update(status='error', error=str(exc))
        row['seconds'] = round(time.time()-started, 2)
        row['checks'] = checks(row)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"END {name}: {row['status']} {row['seconds']}s", flush=True)


if __name__ == '__main__':
    main()
