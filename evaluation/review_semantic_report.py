"""Paired diagnostic report against the frozen, unchanged old drafts/reviews."""
import collections
import html
import json
from pathlib import Path

from evaluation.fixed_answer_replay import read, write, sha
from evaluation.fixed_answer_report import report, GOOD
from evaluation.review_semantic_run import OUTPUT


def paired(out=OUTPUT):
    report(out)
    manifest=read(out/'manifest.json')
    source=Path(manifest['comparison_source'])
    old=read(source/'diagnostic-decision.json')
    new=read(out/'diagnostic-decision.json')
    previous={(r['input_id'],r['arm'],r['condition']):r for r in read(source/'diagnostic-comparisons.json')}
    old_results={}
    new_results={}
    changes=[]
    totals=collections.defaultdict(collections.Counter)
    arms=collections.defaultdict(collections.Counter)
    cases={c['id']:c for c in read('data/memory_validation_cases.json')}
    for row in read(out/'diagnostic-comparisons.json'):
        before=previous[(row['input_id'],row['arm'],row['condition'])]
        a,b=before.get('judgment','processing_error'),row.get('judgment','processing_error')
        change=('improved' if a not in GOOD and b in GOOD else
                'worsened' if a in GOOD and b not in GOOD else 'same')
        key=row['input_id']
        if key not in old_results:
            old_results[key]=read(source/'results'/(key+'.json'))['conditions']
            new_results[key]=read(out/'results'/(key+'.json'))['conditions']
        old_value=old_results[key][row['condition']]
        new_value=new_results[key][row['condition']]
        changes.append(dict(**row, previous_judgment=a, current_judgment=b,
                            paired_change=change, judgment_changed=a!=b,
                            previous_review=before.get('reason'),
                            previous_response=old_value.get('response'),
                            current_response=new_value.get('response'),
                            response_changed=old_value.get('response')!=new_value.get('response'),
                            previous_decision=old_value.get('decision'),
                            current_decision=new_value.get('decision')))
        category=cases[row['case']]['category']
        totals[(row['condition'],category)][change]+=1
        totals[(row['condition'],category)]['wrong_before']+=a=='wrong'
        totals[(row['condition'],category)]['wrong_after']+=b=='wrong'
        totals[(row['condition'],category)]['excessive_before']+=a=='excessive_abstention'
        totals[(row['condition'],category)]['excessive_after']+=b=='excessive_abstention'
        totals[(row['condition'],category)]['processing_after']+=b=='processing_error'
        arms[(row['condition'],row['arm'])]['before_'+a]+=1
        arms[(row['condition'],row['arm'])]['after_'+b]+=1
    # Compare every completed input, not only rows which happen to have changed.
    ids=sorted({r['input_id'] for r in changes})
    for key in ids:
        a=read(source/'results'/(key+'.json'))['conditions']
        b=read(out/'results'/(key+'.json'))['conditions']
        assert a['B']==b['B']
        assert all(a[c]['draft']==b[c]['draft'] for c in 'BCD')
    write(out/'verifier-paired-comparisons.json',changes)
    write(out/'verifier-paired-categories.json',[dict(condition=c,category=t,**v) for (c,t),v in totals.items()])
    write(out/'verifier-paired-arms.json',[dict(condition=c,arm=a,**v) for (c,a),v in arms.items()])
    semantic=[]
    stage_costs=collections.defaultdict(collections.Counter)
    for key in ids:
        journal=read(out/'stages'/(key+'.json'))
        for attempt in journal['attempts']:
            cost=stage_costs[attempt['stage']]
            cost['attempts']+=1
            cost['seconds']+=attempt.get('seconds',0)
            cost['errors']+=attempt['status']!='ok'
            cost['generation_calls']+=sum(c['endpoint']=='completions' for c in attempt['calls'])
            cost['api_calls']+=len(attempt['calls'])
            cost['completion_tokens']+=sum(c.get('completion_tokens') or 0 for c in attempt['calls'])
        for name,stage in journal['stages'].items():
            if name not in ('review','repair_review'):continue
            checks=None
            for call in stage['calls']:
                if call['endpoint']!='completions':continue
                try:
                    checks=json.loads(call['raw_response'][0]['message']['content']).get('checks')
                except (KeyError, TypeError, IndexError, json.JSONDecodeError):
                    pass
            semantic.append(dict(input_id=key,stage=name,status=stage['status'],checks=checks,
                                 review=stage.get('value'),error=stage.get('error')))
    write(out/'semantic-checks.json',semantic)
    write(out/'verifier-stage-costs.json',{k:dict(v) for k,v in stage_costs.items()})
    h=lambda x:html.escape(str(x))
    parts=['<section><h2>검증기 수정 전후: 같은 초안의 직접 비교</h2>',
           '<p>앞 표의 A/B는 기존 기준선입니다. 아래 비교는 이전 C/D와 수정된 C/D입니다. '
           '검색·근거·순서·초안·기존 B 검증은 모두 동일하며, 검증 프롬프트와 의미 대조 결과의 승인 연결만 변경했습니다. '
           'D의 수정 생성 함수는 동일하지만 새 검증 피드백을 받으므로 수정 답변은 달라질 수 있습니다.</p>',
           '<table><tr><th>조건</th><th>오답 승인 전→후</th><th>과잉 보류 전→후</th><th>정답 전→후</th><th>처리 오류 전→후</th><th>빈 응답 전→후</th></tr>']
    for c in 'CD':
        a,b=old['table'][c],new['table'][c]
        parts.append('<tr><td>'+c+'</td>'+''.join(f'<td>{a.get(k,0)} → {b.get(k,0)}</td>' for k in ('wrong','excessive_abstention','correct','processing_error','empty_responses'))+'</tr>')
    parts.append('</table><p>248개는 같은 33문항의 검색 조건별 결과이며 독립 문항 248개가 아닙니다. '
                 '기존 실패를 보고 수정한 개발 진단이므로 새 최종 검증 성능으로 해석하지 않습니다. '
                 '오답이 빈 응답이나 처리 오류로 바뀐 것만으로 정답 개선으로 세지 않습니다.</p>')
    parts.append('<table><tr><th>조건/유형</th><th>오답 전→후</th><th>과잉 보류 전→후</th><th>정답 여부 개선/악화/동일</th><th>처리 오류</th></tr>')
    for (c,cat),v in sorted(totals.items()):
        if c=='B':continue
        parts.append(f'<tr><td>{h(c+" / "+cat)}</td><td>{v["wrong_before"]} → {v["wrong_after"]}</td><td>{v["excessive_before"]} → {v["excessive_after"]}</td><td>{v["improved"]}/{v["worsened"]}/{v["same"]}</td><td>{v["processing_after"]}</td></tr>')
    parts.append('</table><h3>검색 조건별 동일 입력 비교</h3><table><tr><th>답변/검색 조건</th><th>오답 전→후</th><th>과잉 보류 전→후</th><th>처리 오류 전→후</th></tr>')
    for (c,arm),v in sorted(arms.items()):
        if c=='B':continue
        parts.append(f'<tr><td>{h(c+" / "+str(arm))}</td>'+''.join(f'<td>{v["before_"+k]} → {v["after_"+k]}</td>' for k in ('wrong','excessive_abstention','processing_error'))+'</tr>')
    parts.append('</table><p>이번 실제 호출 비용은 새 검증·조건부 수정·재검증만 포함합니다. 가져온 기존 초안과 B 검증 호출은 재실행하지 않았습니다. '
                 '아래 logical_generation_calls는 각 조건을 처음부터 독립 실행할 때의 호출 수로, 이번 실지출과 다릅니다. '
                 '원문 검토자는 기존 자료 작성자와 동일하며 독립 검토가 아닙니다.</p></section>')
    parts.append('<h3>이번 실제 단계별 실행 비용</h3><table><tr><th>단계</th><th>생성 호출</th><th>전체 API 호출</th><th>기록 시간(초)</th><th>오류 단계</th></tr>')
    for name,v in stage_costs.items():
        parts.append(f'<tr><td>{h(name)}</td><td>{v["generation_calls"]}</td><td>{v["api_calls"]}</td><td>{v["seconds"]:.1f}</td><td>{v["errors"]}</td></tr>')
    parts.append('</table>')
    path=out/'diagnostic-report.html'
    document=path.read_text(encoding='utf-8')
    document=document.replace('<h2>확대 판단</h2>',''.join(parts)+'<h2>확대 판단</h2>')
    path.write_text(document,encoding='utf-8')
    write(out/'paired-report-provenance.json',{str(p):sha(p) for p in (Path(__file__),Path('evaluation/fixed_answer_report.py'),path,out/'verifier-paired-comparisons.json',out/'verifier-paired-categories.json')})
    # Base report hash changes after the paired section is added.
    provenance=read(out/'report-provenance.json')
    provenance[str(path)]=sha(path)
    write(out/'report-provenance.json',provenance)


if __name__=='__main__':
    paired()
