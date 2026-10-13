"""Validated chunked extraction using the team's unchanged v4 schemas."""
import copy
import json
from dataclasses import dataclass

import requests

from config.settings import paths, Settings
from .chunking import split_text
from .extractor import extract_memories, sentence_units, grounded_schema
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

ACCURACY_RULES = '''
정확도 점검: 같은 사건의 동행인·장소·대상을 각각 별도 사건으로 반복하지 않는다.
"오늘 유진과 카페에서 보고서를 완성했다." → 기억 1개.
content="유진과 카페에서 보고서를 완성했다", subject=사용자, predicate="완성하다", object=보고서.
유진은 동행인이며 완성한 대상이 아니다. 장소와 동행 정보는 content에 함께 보존한다.
"유진이 나에게 책을 줬다." → subject=유진, predicate="주다", object=책.
"나는 유진에게 책을 줬다." → subject=사용자, predicate="주다", object=책.
"파일을 백업하고 OS를 재설치했다." → 독립 행동 2개. 한 문장당 1개로 제한하지 않는다.
"어제 회의했다. 다음 주 발표할 예정이다." → 사건과 계획 2개, 각각 자기 날짜만 사용한다.
"커피를 마시지 않았다." → 부정 보존. "아마 민수가 올 것 같다." → 불확실성 보존.
최종 점검에서 동일 사건을 참여자/장소만 바꿔 반복한 기억을 통합하되 독립 사건은 유지한다.
'''


@dataclass(frozen=True)
class PipelineOptions:
    context_tokens: int = 32768
    chunk_bytes: int = 6000
    overlap_chars: int = 160
    max_split_depth: int = 3


def align_verbatim_evidence(memory, source_text):
    """Repair only a unique, verbatim content match with all named refs present.

    No fuzzy matching, paraphrase guessing, or ambiguous repeated occurrences.
    """
    content = memory['content'].strip().rstrip('.!?')
    if len(content) < 8 or any(content in e['quote'] for e in memory['evidence']):
        return None
    candidates = [unit for unit in sentence_units(source_text) if content in unit]
    if len(candidates) != 1:
        return None
    quote = candidates[0]
    refs = [memory['subject'], memory['object']]
    if memory['target']:
        refs.extend([memory['target']['subject'], memory['target']['object']])
    if any(ref['kind'] not in ('self', 'unknown') and ref['value'] is not None
           and str(ref['value']) not in quote for ref in refs):
        return None
    previous = [e['quote'] for e in memory['evidence']]
    memory['evidence'] = [{'quote': quote}]
    return {'code': 'evidence_realigned', 'content': memory['content'],
            'original_quotes': previous, 'replacement_quote': quote,
            'message': '기억 내용 전체와 대상이 원문 한 문장에 일치하여 잘못 선택한 근거를 다시 연결했습니다.'}


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
    prompt = paths.prompt.read_text(encoding='utf-8').strip() + TIME_RULES + ACCURACY_RULES
    # Conservative Qwen byte-fallback bound, not an exact tokenizer count.
    # Include schema, metadata and allowance for client instructions/chat framing.
    overhead = len((prompt + json.dumps(output_schema, ensure_ascii=False)
                    + json.dumps(context, ensure_ascii=False)).encode('utf-8')) + 2048
    budget = min(options.chunk_bytes, options.context_tokens - settings.max_tokens - overhead - 1024)
    if budget < 32:
        raise ValueError('Context budget too small for prompt/schema/output; increase server context and context_tokens')
    chunks = split_text(text, budget, options.overlap_chars)
    own_session = session is None
    session = session or requests.Session()
    extract_fn = extract_fn or extract_memories
    calls, provenance, collected, anchors, warnings = [], [], [], [], []

    def process(chunk, depth=0, offset=0):
        start = offset + chunk.start
        end = offset + chunk.end
        context_split = False
        try:
            units = sentence_units(chunk.text)
            request_text = json.dumps([{'sentence_id': f's{i}', 'text': quote}
                                       for i, quote in enumerate(units)], ensure_ascii=False)
            dynamic_schema = grounded_schema(output_schema, units)
            actual_bound = len((prompt + request_text + json.dumps(dynamic_schema, ensure_ascii=False)
                                + json.dumps(context, ensure_ascii=False)).encode('utf-8')) + 3072
            if actual_bound + settings.max_tokens > options.context_tokens:
                context_split = True
                raise ValueError('OUTPUT_TRUNCATED: numbered input exceeds conservative context budget')
            raw, metadata, latency = extract_fn(
                session=session, endpoint=settings.endpoint, model=settings.model,
                prompt=prompt, source_text=chunk.text, source_context=context,
                timeout=settings.timeout, max_tokens=settings.max_tokens,
                temperature=settings.temperature, seed=settings.seed, top_p=settings.top_p)
        except ValueError as exc:
            if 'OUTPUT_TRUNCATED' not in str(exc):
                raise
            calls.append({'start': start, 'end': end,
                          'status': 'context_split' if context_split else 'truncated'})
            size = len(chunk.text.encode('utf-8'))
            if depth >= options.max_split_depth or size < 64:
                raise ValueError(f'Output remains truncated at source[{start}:{end}]') from exc
            for child in split_text(chunk.text, max(32, size // 2), options.overlap_chars):
                process(child, depth + 1, start)
            return
        # Validate structure first, but derive normalized date fields ourselves
        # before checking their cross-field constraints.
        structural_schema = copy.deepcopy(output_schema)
        structural_schema['$defs']['time'].pop('allOf', None)
        for field in ('start', 'end', 'precision', 'certainty'):
            structural_schema['$defs']['time']['properties'][field] = {}
        errors = schema_errors(raw, structural_schema) + evidence_checks(raw, chunk.text)
        if errors:
            raise ValueError(f'Invalid extraction at source[{start}:{end}]: ' + '; '.join(errors))
        calls.append(dict(start=start, end=end, status='ok', latency_seconds=latency, **metadata))
        for original in raw['memories']:
            memory = copy.deepcopy(original)
            alignment = align_verbatim_evidence(memory, chunk.text)
            if alignment:
                warnings.append(dict(alignment, source_start=start, source_end=end))
            raw_time = memory['time']['raw']
            if raw_time and not any(raw_time in item['quote'] for item in memory['evidence']):
                # A date borrowed from another sentence is not evidence. Keep
                # the event, abstain on its time, and retain the rejected value.
                warnings.append({'code': 'unsupported_time_raw', 'source_start': start,
                                 'source_end': end, 'content': memory['content'],
                                 'discarded_raw': raw_time,
                                 'message': '선택한 원문 근거에 없는 시간 표현을 제외하고 미확정으로 유지했습니다.'})
                memory['time']['raw'] = None
            memory['time'] = normalize_time(memory, reference_time)
            errors = schema_errors({'memories': [memory]}, output_schema)
            if errors:
                raise ValueError('Invalid normalized extraction: ' + '; '.join(errors))
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
    return result, {'chunk_count': len(chunks),
                    'request_count': sum(c['status'] != 'context_split' for c in calls),
                    'memory_count': len(collected), 'calls': calls,
                    'warnings': warnings,
                    'validation': report, 'source_spans': [
                        {'local_id': f'm{i+1}', 'start': a, 'end': b}
                        for i, (_, a, b) in enumerate(provenance)]}


def embed_text(memory):
    """One retrieval document per memory."""
    time = memory['time']
    return ' '.join(str(value) for value in (memory['content'], time['raw'], time['start'],
                    time['end']) if value is not None)
