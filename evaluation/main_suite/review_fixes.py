"""Versioned authored corrections, not retrospective edits to recorded runs."""

import copy


def correct(cases):
    for case in cases:
        vid = case['variables'][0]
        if vid in {'IN-41', 'RR-33', 'EX-19', 'EV-06'}:
            case.update(expected_answer='PMA는 외부 API를 사용하지 않았다.', required_facts=['사용하지'],
                        accepted_answers=['PMA는 외부 API를 사용하지 않았다.', 'PMA는 외부 API를 사용하지 않았습니다.',
                                          '외부 API를 사용하지 않았고 로컬 모델만 사용했다.'])
        if vid == 'IN-68':
            case.update(expected_answer='PMA 배포는 완료되지 않았다.', required_facts=[],
                        accepted_answers=['PMA 배포는 완료되지 않았다.', 'PMA 배포는 완료되지 않았습니다.'])
            for refs in case.get('gold_groups', {}).values():
                for ref in refs:
                    source = next(r['text'] for r in case['records'] if r['id'] == ref['record_id'])
                    essential = '실제로 배포하지 않았다.'
                    if essential in source:
                        ref.update(start=source.index(essential), end=source.index(essential)+len(essential), quote=essential)
        if vid == 'QU-05':
            case.update(expected_behavior='clarify', gold_groups={}, required_facts=[],
                        expected_answer='어떤 분야의 모델인지 알려주시겠어요?',
                        accepted_answers=['어떤 분야의 모델인지 알려주시겠어요?'])
        if vid == 'LC-21':
            case.update(expected_answer='간결한 답변을 선호한다.', required_facts=['간결'],
                        accepted_answers=['간결한 답변을 선호합니다.', '사용자는 간결한 답변을 선호합니다.'])
        if vid in {'CV-09', 'CV-26'}:
            case['question'] = '아까 PMA 기록으로 돌아가서 어떤 작업을 했는지 다시 설명해줘.'
            case['steps'][-1]['question'] = case['question']
        if vid in {'ST-08', 'CV-16'} and len(case['steps']) > 1:
            case['steps'][0]['expect'] = {'expected_behavior':'clarify', 'required_facts':[], 'forbidden_facts':[]}
        # The first response is part of the public product, even if later recall succeeds.
        if vid == 'LC-08':
            case['steps'][0]['expect'] = {'expected_behavior': 'answer', 'required_facts': ['기억 검색', '사진 분류'],
                                         'forbidden_facts': ['프로젝트 관리 범위', '프로젝트 관리 계획']}
        if vid in {'LC-22', 'IN-06'}:
            case['steps'][0]['expect'] = {'expected_behavior': 'answer', 'required_facts': [],
                                         'forbidden_facts': ['기억해둘게요', '기억해둘게', '저장했습니다']}
    return cases


def generalization_cases():
    """Independent synthetic authors/topics; final histories never enter core."""
    result = []
    for author, project, split in [('user-a', '푸른별', 'development'), ('user-b', '모래시계', 'final'),
                                   ('user-c', '은하수', 'final')]:
        source = f'{project} 실험 장비 RAM은 96GB이고 구매 가격은 75만 원이다.'
        noise = f'다른 프로젝트의 장비 RAM은 32GB다. {project} 장비와는 다르다.'
        family = 'GEN-' + author
        for variant, question in [('normal', f'{project} 장비 RAM과 구매 가격은?'),
                                  ('paraphrase', f'{project} 실험용 컴퓨터 메모리 용량과 구입 비용을 알려줘.'),
                                  ('negative', f'{project} 장비 RAM이 32GB이고 가격이 75만 원이 맞아?'),
                                  ('long', f'{project} 장비 RAM과 구매 가격은?')]:
            prefix = ('회의 준비와 검토 절차를 기록했다.\n' * 80) if variant == 'long' else ''
            text = prefix + source
            case = {'id': family + '.' + variant, 'family': family, 'split': split, 'variant': 'normal',
                    'priority': 'P0', 'variables': ['IN-33', 'QU-08', 'RR-16'], 'adapter': 'product',
                    'question': question, 'records': [{'id': 'target', 'owner': author, 'version': 1, 'text': text},
                                                     {'id': 'distractor', 'owner': author, 'version': 1, 'text': noise}],
                    'steps': [{'action': 'chat', 'question': question}], 'expected_behavior': 'answer',
                    'expected_answer': 'RAM은 96GB이고 구매 가격은 75만 원이다.', 'required_facts': ['96GB', '75만'],
                    'accepted_answers': ['RAM은 96GB이고 구매 가격은 75만 원이다.', f'{project} 장비의 RAM은 96GB이고 구매 가격은 75만 원입니다.'],
                    'forbidden_facts': [], 'gold_groups': {'equipment': [{'record_id': 'target', 'version': 1,
                        'start': len(prefix), 'end': len(text), 'quote': source}]}, 'coverage_gaps': [],
                    'model_accuracy_sample': True, 'generalization': {'author_style': author, 'topic': project,
                    'kind': variant, 'scope': 'synthetic_author_style_not_multi_user_auth'}}
            result.append(case)
        # Changing a fact must change the answer, unlike paraphrasing/noise transforms.
        contrast = copy.deepcopy(result[-4])
        contrast.update(id=family+'.changed-value', expected_answer='RAM은 48GB이고 구매 가격은 75만 원이다.',
                        required_facts=['48GB', '75만'], accepted_answers=['RAM은 48GB이고 구매 가격은 75만 원이다.'])
        contrast['records'][0]['text'] = source.replace('96GB', '48GB')
        contrast['gold_groups']['equipment'][0]['quote'] = contrast['records'][0]['text']
        result.append(contrast)
        # Author formatting is deliberately distinct, while original meaning is retained.
        if author == 'user-b':
            for case in result[-5:]:
                case['records'][0]['text'] = '# 장비 도입 회의록\n' + case['records'][0]['text']
                ref = case['gold_groups']['equipment'][0]
                ref['start'] += len('# 장비 도입 회의록\n')
                ref['end'] += len('# 장비 도입 회의록\n')
        if author == 'user-c':
            for case in result[-5:]:
                prefix = '작성자: 연구 담당\n발언: '
                case['records'][0]['text'] = prefix + case['records'][0]['text']
                ref = case['gold_groups']['equipment'][0]
                ref['start'] += len(prefix)
                ref['end'] += len(prefix)
        multilingual = copy.deepcopy(result[-5])
        multilingual.update(id=family+'.english', question=f'What RAM capacity and purchase price did {project} use?')
        multilingual['steps'] = [{'action': 'chat', 'question': multilingual['question']}]
        multilingual['generalization']['kind'] = 'cross_language'
        result.append(multilingual)
        for variation in ('without-noise', 'reordered'):
            transformed = copy.deepcopy(result[-6])
            transformed['id'] = family+'.'+variation
            transformed['records'] = transformed['records'][:1] if variation == 'without-noise' else list(reversed(transformed['records']))
            transformed['generalization']['kind'] = variation
            result.append(transformed)
    for project, owner, split, topic, answer, facts in [
        ('산들농장', 'user-b', 'final', '토마토 관수는 사흘마다 진행하고 담당자는 하린이다.', '사흘마다 관수하고 담당자는 하린이다.', ['사흘', '하린']),
        ('달빛도서관', 'user-c', 'final', '희귀본 열람은 예약이 필요하고 담당자는 도윤이다.', '예약이 필요하고 담당자는 도윤이다.', ['예약', '도윤'])]:
        text = project + ' 운영 기록: ' + topic
        question = project + ' 운영 조건과 담당자는?'
        result.append({'id': 'GEN-topic-'+owner, 'family':'GEN-topic-'+owner, 'split':split, 'variant':'normal', 'priority':'P0',
            'variables':['QU-24','RR-22'], 'adapter':'product', 'question':question,
            'records':[{'id':'target','text':text,'version':1,'owner':owner}],
            'steps':[{'action':'chat','question':question}], 'expected_behavior':'answer','expected_answer':answer,
            'required_facts':facts,'forbidden_facts':[], 'accepted_answers':[answer], 'coverage_gaps':[],
            'gold_groups':{'target':[{'record_id':'target','version':1,'start':0,'end':len(text),'quote':text}]},
            'generalization':{'kind':'unseen_topic', 'author_style':owner}, 'model_accuracy_sample':True})
    for case in result:
        if case.get('gold_groups'):
            required_ids = {r['record_id'] for refs in case['gold_groups'].values() for r in refs}
            case['source_relevance'] = {r['id']: (2 if r['id'] in required_ids else 0) for r in case['records']}
            if case.get('generalization',{}).get('kind') != 'unseen_topic':
                case['extraction_facts'] = [{'record_id':'target','required_strings':[fact]} for fact in case['required_facts']]
    result.extend(regression_cases())
    return result


def regression_cases():
    def make(key, texts, question, answer, facts, *, behavior='answer', steps=None, required=None):
        records = [{'id': f'r{i}', 'text': text, 'version': 1, 'owner': 'user-a'} for i, text in enumerate(texts)]
        required = range(len(records)) if required is None and behavior == 'answer' else required or []
        return {'id': 'GEN-'+key, 'family': 'GEN-'+key, 'split':'development', 'priority':'P0', 'variant':'normal',
            'adapter':'product', 'variables':['CV-09','CV-16','EV-02'], 'records':records, 'question':question,
            'steps':steps or [{'action':'chat','question':question}], 'expected_behavior':behavior, 'expected_answer':answer,
            'accepted_answers':[answer], 'required_facts':facts, 'forbidden_facts':[], 'coverage_gaps':[],
            'gold_groups':{f'g{i}':[{'record_id':records[i]['id'],'version':1,'start':0,'end':len(records[i]['text']),
                                   'quote':records[i]['text']}] for i in required}, 'model_accuracy_sample':True,
            'generalization':{'kind':'completed_run_regression','author_style':'user-a'}}
    cases = []
    cases.append(make('filter-learning', ['루멘에서 Machine Learning 자료를 공부했다.', '누리는 루멘과 다른 프로젝트이며 담당자는 도윤이다.'],
        '루멘 ML 공부 기록은?', '루멘에서 Machine Learning 자료를 공부했다.', ['자료'], required=[0]))
    cases.append(make('selection-class', ['2026년 10월 10일 BFS 알고리즘을 공부했다.'],
        '전에 공부한 탐색 알고리즘은?', 'BFS 알고리즘을 공부했다.', ['BFS']))
    cases.append(make('pending-person', ['회사 동료 지우는 루멘 개발자다.', '동아리 친구 지우는 누리 교사다.'],
        '그 내용을 다시 설명해줘.', '회사 동료 지우와 동아리 친구 지우 중 누구를 뜻하는지 알려주세요.', [], behavior='clarify',
        steps=[{'action':'chat','question':'지우는 어떤 일을 해?', 'expect':{'expected_behavior':'clarify','required_facts':[],'forbidden_facts':[]}},
               {'action':'chat','question':'그 내용을 다시 설명해줘.'}]))
    cases.append(make('calendar-replacement', ['2026년 10월 15일 루멘 검색 캐시를 개선했다.'], '이번 달로 바꿔',
        '2026년 10월 15일 루멘 검색 캐시를 개선했다.', ['루멘','캐시'],
        steps=[{'action':'chat','question':'지난달 루멘 캐시 개선 기록은?', 'filters':{'date_from':'2026-09-01','date_to':'2026-09-30'},
                'expect':{'expected_behavior':'abstain','required_facts':[],'forbidden_facts':[]}},
               {'action':'chat','question':'이번 달로 바꿔'}]))
    cases.append(make('ambiguous-completion', ["루멘 회의에서 서버 설계와 화면 검수를 논의했다. '그것은 완료했다'라고만 적었다."],
        '루멘에서 무엇을 완료한 거야?', '어떤 작업이 완료되었는지 원문에서 구분되지 않습니다. 완료한 작업을 알려주시겠어요?', [], behavior='clarify'))
    cases.append(make('multiple-evidence', ['2026년 9월 10일 루멘 담당자를 도윤으로 정했다.', '2026년 10월 15일 루멘 담당자를 하린으로 변경했다.'],
        '루멘 담당자의 처음 결정과 최신 변경은?', '처음에는 도윤, 최신 담당자는 하린이다.', ['도윤','하린']))
    cases.append(make('unknown-result', ['루멘에 사전 로딩 개선안을 제안했다. 효과는 측정하지 않았다.'],
        '루멘 사전 로딩으로 50% 빨라졌지?', '효과를 측정하지 않아 50% 개선이라고 확인할 수 없다.', [], behavior='abstain'))
    topic = make('recent-general-topic', ['루멘에서 벡터 검색 캐시를 개선했다.'], '그 내용을 다시 설명해줘.',
        '정렬은 데이터를 정해진 순서로 나열하는 것이다.', ['순서'],
        steps=[{'action':'chat','question':'루멘에서 어떤 작업을 했어?', 'expect':{'expected_behavior':'answer','required_facts':['캐시'],'forbidden_facts':[]}},
               {'action':'chat','question':'정렬을 설명해줘','mode':'general'}, {'action':'chat','question':'그 내용을 다시 설명해줘.'}])
    topic['gold_groups'] = {}
    cases.append(topic)
    history = copy.deepcopy(topic)
    history.update(id='GEN-long-history', family='GEN-long-history', extended_only=True)
    history['steps'][1:1] = [{'action':'chat','question':q,'mode':'general'} for q in
        ['이진 탐색이 뭐야?', '배열을 설명해줘', '리스트를 설명해줘', '사전을 설명해줘', '반복문을 설명해줘', '함수를 설명해줘']]
    cases.append(history)
    return cases
