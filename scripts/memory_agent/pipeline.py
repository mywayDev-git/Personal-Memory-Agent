"""Validated chunked extraction using the team's unchanged v4 schemas."""
import copy
import json
from dataclasses import dataclass

import requests

from config.settings import paths, Settings
from .chunking import split_text
from .extractor import extract_memories
from .postprocess import build_final_result, make_source_context
from .temporal import normalize_time
from .validator import load_schema, schema_errors, evidence_checks, validate_final_result


TIME_RULES = '''
추가 실행 규칙: 입력은 긴 원문의 일부일 수 있으며 인접 구간과 겹칠 수 있다.
제공된 구간만 근거로 추출하고, 잘린 문맥에서 인물이나 날짜를 추측하지 마라.
각 기억의 time.raw는 그 기억에 연결된 시간 표현만 원문 그대로 출력한다.
time.raw를 포함하는 연속 원문 구간을 해당 기억의 evidence.quote에 포함한다.
날짜 계산은 Python이 담당한다. time.start와 time.end는 null로 출력한다.
시간 표현이 있으면 precision은 relative 또는 unknown, certainty는 uncertain으로 둔다.
시간 표현이 없으면 raw도 null로 둔다. 작성일을 사건 날짜로 대신 쓰지 마라.
'''


@dataclass(frozen=True)
class PipelineOptions:
    context_tokens: int = 32768
    chunk_bytes: int = 6000
    overlap_chars: int = 160
    max_split_depth: int = 3


def extract_document(text, *, source_id, reference_time=None, settings=None,
                     options=None, session=None, extract_fn=None):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Source text must not be empty')
    settings = settings or Settings.from_env()
    options = options or PipelineOptions()
    if options.max_split_depth < 0:
        raise ValueError('max_split_depth must be nonnegative')
    if settings.max_tokens <= 0 or settings.timeout <= 0:
        raise ValueError('max_tokens and timeout must be positive')
    context = make_source_context(source_id, reference_time)
    output_schema = load_schema(paths.output_schema)
    final_schema = load_schema(paths.final_schema)
    errors = schema_errors(build_final_result({'memories': []}, context), final_schema)
    if errors:
        raise ValueError('\n'.join(errors))
    prompt = paths.prompt.read_text(encoding='utf-8').strip() + TIME_RULES
    # Conservative Qwen byte-fallback bound, not an exact tokenizer count.
    # Include schema, metadata and allowance for client instructions/chat framing.
    overhead = len((prompt + json.dumps(output_schema, ensure_ascii=False)
                    + json.dumps(context, ensure_ascii=False)).encode('utf-8')) + 2048
    budget = min(options.chunk_bytes, options.context_tokens - settings.max_tokens - overhead)
    if budget < 32:
        raise ValueError('Context budget too small for prompt/schema/output; increase server context and context_tokens')
    chunks = split_text(text, budget, options.overlap_chars)
    own_session = session is None
    session = session or requests.Session()
    extract_fn = extract_fn or extract_memories
    calls, provenance, collected, anchors = [], [], [], []

    def process(chunk, depth=0, offset=0):
        start = offset + chunk.start
        end = offset + chunk.end
        try:
            raw, metadata, latency = extract_fn(
                session=session, endpoint=settings.endpoint, model=settings.model,
                prompt=prompt, source_text=chunk.text, source_context=context,
                timeout=settings.timeout, max_tokens=settings.max_tokens,
                temperature=settings.temperature, seed=settings.seed, top_p=settings.top_p)
        except ValueError as exc:
            if 'OUTPUT_TRUNCATED' not in str(exc):
                raise
            calls.append({'start': start, 'end': end, 'status': 'truncated'})
            size = len(chunk.text.encode('utf-8'))
            if depth >= options.max_split_depth or size < 64:
                raise ValueError(f'Output remains truncated at source[{start}:{end}]') from exc
            for child in split_text(chunk.text, max(32, size // 2), options.overlap_chars):
                process(child, depth + 1, start)
            return
        errors = schema_errors(raw, output_schema) + evidence_checks(raw, chunk.text)
        if errors:
            raise ValueError(f'Invalid extraction at source[{start}:{end}]: ' + '; '.join(errors))
        calls.append(dict(start=start, end=end, status='ok', latency_seconds=latency, **metadata))
        for original in raw['memories']:
            memory = copy.deepcopy(original)
            memory['time'] = normalize_time(memory, reference_time)
            # Exact semantic duplicates only across overlapping source slices.
            key = json.dumps({k: v for k, v in memory.items() if k != 'evidence'},
                             ensure_ascii=False, sort_keys=True)
            locations = set()
            for item in memory['evidence']:
                quote = item['quote']
                pos = chunk.text.find(quote)
                # Ambiguous repeated quotes must not collapse distinct occurrences.
                if chunk.text.find(quote, pos + 1) == -1:
                    locations.add((start + pos, start + pos + len(quote)))
            duplicate = None
            for i, (old_key, old_start, old_end) in enumerate(provenance):
                if key == old_key and locations & anchors[i]:
                    duplicate = i
                    break
            if duplicate is None:
                collected.append(memory)
                provenance.append((key, start, end))
                anchors.append(locations)
            else:
                anchors[duplicate].update(locations)
                _, old_start, old_end = provenance[duplicate]
                provenance[duplicate] = (key, min(start, old_start), max(end, old_end))
                for evidence in memory['evidence']:
                    if evidence not in collected[duplicate]['evidence']:
                        collected[duplicate]['evidence'].append(evidence)

    try:
        for chunk in chunks:
            process(chunk)
    finally:
        if own_session:
            session.close()
    result = build_final_result({'memories': collected}, context)
    report = validate_final_result(result, final_schema, text)
    if not report['valid']:
        raise ValueError(json.dumps(report, ensure_ascii=False))
    return result, {'chunk_count': len(chunks), 'request_count': len(calls),
                    'memory_count': len(collected), 'calls': calls,
                    'validation': report, 'source_spans': [
                        {'local_id': f'm{i+1}', 'start': a, 'end': b}
                        for i, (_, a, b) in enumerate(provenance)]}


def embed_text(memory):
    """One retrieval document per memory."""
    time = memory['time']
    return ' '.join(str(value) for value in (memory['content'], time['raw'], time['start'],
                    time['end']) if value is not None)
