"""Source-review queue and decision report for fixed answer replay. No model calls."""
import argparse
import collections
import html
from pathlib import Path

from evaluation.fixed_answer_replay import read, write, sha, digest, verify_manifest

GOOD={'correct','appropriate_abstention'}
JUDGMENTS=GOOD|{'wrong','excessive_abstention'}


def collect(out, phase='diagnostic'):
    inputs=read(out/'inputs.json')
    mappings=[m for m in read(out/'mappings.json') if phase!='diagnostic' or m['diagnostic']]
    groups,rows={},[]
    fixtures={c['id']:c for c in read('data/memory_validation_cases.json')}
    for m in mappings:
        path=out/'results'/(m['input_id']+'.json')
        if not path.exists():
            continue
        result=read(path)
        for condition,value in result['conditions'].items():
            row=dict(case=m['case'],arm=m['arm'],condition=condition,input_id=m['input_id'],
                     baseline=m['baseline_review'],status=value['status'],groups={})
            for role in ('response','draft','repaired'):
                response=value.get(role)
                if response is None:
                    continue
                nodes={n['id']:n for n in inputs[m['input_id']]['evidence']}
                refs=sorted({cid for item in response['items'] for cid in item['citations']})
                support={cid:dict(quotes=nodes[cid].get('evidence',[]),source_text=nodes[cid].get('source_text')) for cid in refs}
                # Exact same response and citation sources can share a source review,
                # independently of input order, stage, or condition.
                binding=dict(case=m['case'],response=response,support=support)
                key=digest(binding)
                g=groups.setdefault(key,dict(id=key,**binding,usages=[]))
                g['usages'].append(dict(input_id=m['input_id'],condition=condition,arm=m['arm'],role=role))
                row['groups'][role]=key
            rows.append(row)
    return groups,rows,fixtures


def pending(out, category=None):
    groups,_,fixtures=collect(out)
    reviews=read(out/'reviews.json') if (out/'reviews.json').exists() else {}
    for cid in sorted({g['case'] for g in groups.values()}):
        case=fixtures[cid]
        if category and case['category']!=category:
            continue
        values=[]
        for key,g in groups.items():
            if g['case']==cid and key not in reviews:
                values.append(dict(id=key[:12],response=g['response'],
                                   quoted_support={i:[q['quote'] for q in s['quotes']] for i,s in g['support'].items()},
                                   uses=sorted({u['condition']+':'+u['role'] for u in g['usages']})))
        if values:
            print(__import__('json').dumps(dict(case=cid,question=case['questions'][0]['text'],expected=case['expected'],answerability=case['validation']['answerability'],gold=[[q['quote'] for q in group] for group in case['gold']],variants=values),ensure_ascii=False))


def record(out, prefix, judgment, reason):
    assert judgment in JUDGMENTS
    groups,_,_=collect(out,'regression')
    keys=[key for key in groups if key.startswith(prefix)]
    assert len(keys)==1, keys
    key=keys[0]
    reviews=read(out/'reviews.json') if (out/'reviews.json').exists() else {}
    reviews[key]=dict(judgment=judgment,reason=reason,reviewer='Codex source review by fixture author; not independent',
                      binding_hash=digest({k:groups[key][k] for k in ('case','response','support')}))
    write(out/'reviews.json',reviews)


def choose(table):
    base=table['A']
    eligible=[c for c in 'BCD' if table[c]['pending']==0 and table[c]['processing_error']==0
              and table[c]['wrong']<=base['wrong'] and table[c]['excessive_abstention']<=base['excessive_abstention']
              and table[c]['wrong']+table[c]['excessive_abstention']<base['wrong']+base['excessive_abstention']]
    selected=min(eligible,key=lambda c:(table[c]['wrong'],table[c]['excessive_abstention'],table[c]['empty_responses'],table[c]['logical_generation_calls'],c)) if eligible else None
    return dict(eligible=bool(eligible),candidates=eligible,selected=selected)


def report(out):
    manifest=verify_manifest(out)
    groups,rows,fixtures=collect(out)
    reviews=read(out/'reviews.json') if (out/'reviews.json').exists() else {}
    mappings=[m for m in read(out/'mappings.json') if m['diagnostic']]
    assert len(rows)==len(mappings)*3, 'Diagnostic results incomplete'
    table={c:collections.Counter() for c in 'ABCD'}
    categories={}
    for m in mappings:
        table['A'][m['baseline_review']]+=1
        table['A']['empty_responses']+=not bool(m['baseline']['response']['items'])
        categories.setdefault(('A',m['category']),collections.Counter())[m['baseline_review']]+=1
    for row in rows:
        stats=table[row['condition']]
        if row['status']!='complete':
            stats['processing_error']+=1
            continue
        key=row['groups']['response']
        review=reviews.get(key)
        if review:
            assert review['binding_hash']==key
        row['judgment']=review['judgment'] if review else 'pending'
        row['reason']=review['reason'] if review else None
        stats[row['judgment']]+=1
        categories.setdefault((row['condition'],fixtures[row['case']]['category']),collections.Counter())[row['judgment']]+=1
        stats['empty_responses']+=not bool(groups[key]['response']['items'])
        for role in ('draft','repaired'):
            if role in row['groups']:
                r=reviews.get(row['groups'][role])
                row[role+'_judgment']=r['judgment'] if r else 'pending'
        if row.get('draft_judgment') in GOOD and row['judgment']=='excessive_abstention':
            stats['correct_draft_rejected']+=1
        if row.get('draft_judgment') in GOOD and not groups[key]['response']['items']:
            stats['supported_explanation_or_answer_lost']+=1
        if 'repaired_judgment' in row:
            stats['repair_improved']+=row['draft_judgment'] not in GOOD and row['repaired_judgment'] in GOOD
            stats['repair_worsened']+=row['draft_judgment'] in GOOD and row['repaired_judgment'] not in GOOD
        row['change']='improved' if row['baseline'] not in GOOD and row['judgment'] in GOOD else 'worsened' if row['baseline'] in GOOD and row['judgment'] not in GOOD else 'same'
        stats[row['change']]+=1
        row['source_review_id']=key
        row['date_value_missing']=fixtures[row['case']]['category']=='time' and row['judgment']=='wrong' and any('어제' in i['text'] and '말' in i['text'] for i in groups[key]['response']['items'])
    calls=[]
    for key in sorted({m['input_id'] for m in mappings}):
        journal=read(out/'stages'/(key+'.json'))
        for attempt in journal['attempts']:
            calls.extend(dict(input_id=key,**c) for c in attempt['calls'])
        for c,stages in {'B':['draft','legacy_verify'],'C':['draft','review'],'D':['draft','review','repair','repair_review']}.items():
            table[c]['logical_generation_calls']+=sum(call['endpoint']=='completions' for name,value in journal['stages'].items() if name in stages for call in value['calls'])
    unresolved=[k for k in groups if k not in reviews]
    decision=choose(table) if not unresolved else dict(eligible=False,selected=None,status='awaiting_source_review')
    decision.update(table={c:dict(t) for c,t in table.items()},source_review_pending=len(unresolved),
                    review_sha256=sha(out/'reviews.json') if (out/'reviews.json').exists() else None,
                    manifest_sha256=sha(out/'manifest.json'),
                    results={p.name:sha(p) for p in (out/'results').glob('*.json')})
    decision['sensitivity_date_quote_only']={c:dict(count=sum(r.get('date_value_missing',False) for r in rows if r['condition']==c),
        wrong_if_accepted=table[c]['wrong']-sum(r.get('date_value_missing',False) for r in rows if r['condition']==c)) for c in 'BCD'}
    decision['scope']='33-question diagnostic, enriched for previously failed cases; not overall population accuracy. No eligible candidate means no regression expansion or new final evaluation.'
    write(out/'diagnostic-decision.json',decision)
    cost=dict(actual_calls=len(calls),generation_calls=sum(c['endpoint']=='completions' for c in calls),
              recorded_api_seconds=sum(c['seconds'] for c in calls),errors=sum(c['status']!='ok' for c in calls),
              prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
              token_usage_unknown=sum(c.get('prompt_tokens') is None for c in calls),
              note='Recorded usage only; baseline historical cost excluded; shared calls counted once. Logical per-condition counts are counterfactual standalone costs, not additive.')
    write(out/'diagnostic-comparisons.json',rows)
    write(out/'diagnostic-cost.json',cost)
    write(out/'diagnostic-categories.json',[dict(condition=c,category=cat,judgments=dict(counts)) for (c,cat),counts in categories.items()])
    write(out/'diagnostic-deferrals.json',[r for r in rows if r.get('groups',{}).get('response') and not groups[r['groups']['response']]['response']['items']])
    write(out/'diagnostic-stage-errors.json',[dict(input_id=read(p)['input_id'],condition=c,**v) for p in (out/'results').glob('*.json') for c,v in read(p)['conditions'].items() if v['status']!='complete'])
    h=lambda v:html.escape(str(v))
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>고정 근거 답변 검증</title><style>body{font:16px/1.7 system-ui;margin:32px auto;max-width:1200px;padding:0 20px;background:#f5f7fa;color:#192737}table{border-collapse:collapse;background:white;width:100%}td,th{padding:10px;border:1px solid #d4dce5;text-align:left}details{background:white;padding:16px;margin:12px 0}pre{white-space:pre-wrap}h2{margin-top:36px}</style>',
           '<h1>33문항 고정 근거 답변 개선 검증</h1><p>실패 21 + 성공 12문항 · 고유 입력 195 · 조건별 결과 248개. A 기존, B 생성 개선, C 항목별 검증, D 최대 1회 수정.</p>',
           '<p>검색·근거 순서를 고정하고 기존에 선별된 입력만 비교했습니다. 초안과 첫 검증을 공유합니다. 운영 코드·개인 기억은 변경하지 않았습니다. 작성자 원문 검토이며 독립 검토가 아닙니다.</p>',
           '<table><tr><th>조건</th><th>정답</th><th>정당 보류</th><th>오답 승인</th><th>과잉 보류</th><th>처리 오류</th><th>미검토</th><th>개선/악화</th><th>빈 응답</th></tr>']
    for c,t in table.items():
        parts.append('<tr><td>'+c+'</td>'+''.join('<td>'+str(t[k])+'</td>' for k in ('correct','appropriate_abstention','wrong','excessive_abstention','processing_error','pending'))+f'<td>{t["improved"]}/{t["worsened"]}</td><td>{t["empty_responses"]}</td></tr>')
    parts.append('</table><h2>확대 판단</h2><pre>'+h(decision.get('selected') or decision.get('status') or '적격 후보 없음 — 120문항 확대 및 새 최종 검증 중단')+'</pre><p>오답 승인·과잉 보류가 각각 기준선 이하이고 두 실패 합계가 감소해야 합니다. 처리 오류가 남은 후보는 채택하지 않습니다.</p>')
    parts.append('<p>이 33문항은 기존 실패를 집중한 진단 자료이므로 전체 질문 분포의 정확도가 아닙니다. B에는 기존 개선 경로의 생성 프롬프트와 시간 정보 표현 변경이 함께 포함됩니다. 이번 결과로 두 변화의 효과를 따로 분리할 수는 없습니다.</p>')
    if not manifest.get('comparison_source'):
        parts.append('<h2>주요 원인</h2><ul><li>사건일 질문에서 발언일로 답하는 오류가 지속됐습니다. 요청한 날짜 값을 내지 않고 발언만 인용한 응답도 실패로 셉니다.</li><li>의도 부정을 실제 미전달로 바꾸는 오류를 새 항목별 검증도 차단하지 못했습니다.</li><li>정정 유형의 기존 정답이 정정 전 날짜로 바뀐 사례가 발생했습니다.</li><li>이름 미확인·상충 설명과 일부 과잉 보류는 개선됐지만 오답 승인 증가를 상쇄하지 못했습니다.</li><li>한 번의 수정은 일부 빈 답변을 구제했으나 잘못 승인된 답변에는 실행되지 않습니다.</li></ul>')
        parts.append('<p>날짜 질문에서 발언 원문만 인용한 6개 결과를 관대하게 정답 처리해도 오답 승인은 B 88개, C/D 89개로 기준선 82개보다 많습니다. 확대 중단 판단은 이 경계 사례의 채점에 의존하지 않습니다.</p>')
    parts.append('<h2>유형별 판정</h2><table><tr><th>조건</th><th>유형</th><th>정답</th><th>정당 보류</th><th>오답</th><th>과잉 보류</th></tr>')
    for (c,cat),counts in sorted(categories.items()):
        parts.append(f'<tr><td>{c}</td><td>{cat}</td>'+''.join(f'<td>{counts[k]}</td>' for k in ('correct','appropriate_abstention','wrong','excessive_abstention'))+'</tr>')
    parts.append('</table><p>원문과 일치하는 관련 간접 답변은 이전 판정 기준을 유지합니다. 불필요한 사실 나열·반복·명시적 한계 설명 부족은 별도 품질 결함입니다. 정답 초안 보류 집계에는 이러한 관련성 문제를 엄격히 거절한 경우도 포함되므로 전부 검증기 오류라고 해석하지 않습니다.</p>')
    parts.append('<h2>비용·시간</h2><pre>'+h(cost)+'</pre><h2>단계별 결과</h2><pre>'+h({c:dict(t) for c,t in table.items()})+'</pre>')
    for cid in manifest['selection']['cases']:
        case=fixtures[cid]
        parts.append('<details><summary>'+h(cid+' · '+case['questions'][0]['text'])+'</summary><p>기준: '+h(case['expected'])+'</p><p>원문: '+h([[q['quote'] for q in g] for g in case['gold']])+'</p>')
        for key,g in groups.items():
            if g['case']!=cid: continue
            review=reviews.get(key,{})
            parts.append('<p><b>'+h(sorted({u['condition']+':'+u['role'] for u in g['usages']}))+'</b> '+h(review.get('judgment','미검토'))+' — '+h(review.get('reason',''))+'</p><pre>'+h(g['response'])+'</pre>')
        parts.append('<details><summary>입력별 검증 사유·수정 전후 원본</summary>')
        for key in dict.fromkeys(m['input_id'] for m in mappings if m['case']==cid):
            parts.append('<p>'+h(key[:12])+'</p><pre>'+h(read(out/'results'/(key+'.json'))['conditions'])+'</pre>')
        parts.append('</details>')
        parts.append('</details>')
    parts.append('<p>처리 오류는 근거 부족과 구분했습니다. 빈 응답은 설명 누락 지표이며 모든 비어 있지 않은 응답이 충분한 설명·확인 질문을 갖췄다는 뜻은 아닙니다. 새 최종 검증을 수행하지 않았다면 일반화 성능을 주장하지 않습니다.</p></html>')
    (out/'diagnostic-report.html').write_text('\n'.join(parts),encoding='utf-8')
    write(out/'report-provenance.json',{str(p):sha(p) for p in (Path(__file__),out/'manifest.json',out/'reviews.json',out/'diagnostic-comparisons.json',out/'diagnostic-decision.json',out/'diagnostic-report.html')})
    print(__import__('json').dumps({k:v for k,v in decision.items() if k!='results'},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('phase',choices=['pending','record','report'])
    p.add_argument('--output',type=Path,default=Path('output/fixed-answer-replay-v1/run-1'))
    p.add_argument('--category')
    p.add_argument('--id')
    p.add_argument('--judgment',choices=sorted(JUDGMENTS))
    p.add_argument('--reason')
    a=p.parse_args()
    if a.phase=='pending':pending(a.output,a.category)
    elif a.phase=='record':record(a.output,a.id,a.judgment,a.reason)
    else:report(a.output)


if __name__=='__main__':main()
