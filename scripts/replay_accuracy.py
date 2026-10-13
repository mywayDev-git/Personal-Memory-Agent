"""Revalidate recorded model responses after deterministic postprocessing changes.

Only use with the same prompt, model request schema, chunk options and source.
This is a replay of real outputs, not a new inference or an accuracy benchmark.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.eval_accuracy import checks
from scripts.memory_agent.extractor import extract_json, restore_evidence, sentence_units, grounded_schema, load_output_schema
from scripts.memory_agent.pipeline import extract_document, PipelineOptions
from scripts.memory_agent.validator import schema_errors


def replay(row):
    responses = iter(row.get('responses', []))
    used = 0
    def recorded(**kwargs):
        nonlocal used
        try:
            response = next(responses)
        except StopIteration:
            raise ValueError('INCOMPLETE_RECORDING: remaining chunks require a real model call')
        used += 1
        choice = response['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ValueError('OUTPUT_TRUNCATED')
        raw = extract_json(choice['message']['content'])
        units = sentence_units(kwargs['source_text'])
        errors = schema_errors(raw, grounded_schema(load_output_schema(), units))
        if errors:
            raise ValueError('; '.join(errors))
        return restore_evidence(raw, units), {'recorded_response_index':used-1}, 0
    output = {k:row[k] for k in ('name','source','reference_time','input_bytes')}
    output['evaluation_type'] = 'recorded_model_output_replay'
    output['responses'] = row.get('responses', [])
    try:
        result, metadata = extract_document(row['source'], source_id='accuracy-'+row['name'],
            reference_time=row['reference_time'], options=PipelineOptions(chunk_bytes=500 if row['name']=='long' else 6000),
            extract_fn=recorded)
        if used != len(row.get('responses', [])):
            raise ValueError('REPLAY_MISMATCH: recorded responses remain; check unchanged chunk settings')
        output.update(status='ok', result=result, metadata=metadata)
    except Exception as exc:
        output.update(status='error', error=str(exc))
    output['recorded_responses_used'] = used
    output['checks'] = checks(output)
    return output


if __name__ == '__main__':
    rows = json.loads((ROOT/'results/local_accuracy_report.json').read_text(encoding='utf-8'))
    output = [replay(row) for row in rows if row['status'] != 'running']
    (ROOT/'results/local_accuracy_replay.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    for row in output:
        print(json.dumps({'name':row['name'],'status':row['status'],'checks':row['checks']},ensure_ascii=False))
