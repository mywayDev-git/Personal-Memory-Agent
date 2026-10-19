const reasons={direct_answer:'AI 판단: 질문에 직접 답하는 근거',supporting_context:'AI 판단: 배경 정보',conflicting_evidence:'AI 판단: 전제·실행 여부를 반박하는 근거',irrelevant:'AI 판단: 질문과 관련성 부족',unverified_selection:'관련성 판단의 원문 인용을 확인하지 못함',combined_rank:'통합 순위로 선택',coverage_and_rank:'통합 순위·근거 다양성을 고려해 선택',model_selected:'AI 관련성 검토에서 선택 · 세부 사유 미수집',model_not_selected:'AI 관련성 검토에서 선택되지 않음 · 세부 사유 미수집',event_time_order:'사건 날짜 순으로 선택',evidence_limit:'검색별 근거 개수 제한',global_evidence_limit:'전체 검색 통합 후 근거 개수 제한',facts_pending:'검색 정보 정리 대기',relation_mismatch:'사건 종류 불일치',person_mismatch:'인물 조건 불일치',place_mismatch:'장소 조건 불일치',time_unknown:'사건 날짜 확인 불가',time_mismatch:'기간 조건 불일치',quantity_mismatch:'수량 조건 불일치',status_mismatch:'계획·실행 상태 불일치',requested_object:'대상 조건 불일치',preference_change:'선호 변화와 관련 없는 사건 종류',activity_state:'실행된 활동 조건 불일치',location:'장소 조건 불일치',explicit_named_person:'인물 조건 불일치',unknown_filtered_date:'사건 날짜 확인 불가',date_range:'기간 조건 불일치'};
const methods={keyword:'키워드 검색',semantic:'의미 검색 후보',structure:'조건 검색',expansion:'번역·발음·유사어 보조 검색'};
const conditions={relation:'사건 종류',place:'장소',person:'인물',time:'사건 기간',quantity:'거리(m)',object:'대상',state:'계획·실행 상태',self:'본인'};
const values={self:'본인',observed:'실행 관찰',planned:'계획',negated:'부정',uncertain:'불확실',visit:'방문',run:'달리기',give:'전달',receive:'받음',prefer:'선호',desire:'바람'};
const valueText=value=>Array.isArray(value)?value.map(v=>values[v] || v).join(', '):value&&typeof value==='object'?(value.amount!==undefined?`${value.amount}m ${({eq:'일치',ge:'이상',gt:'초과',le:'이하',lt:'미만'})[value.operator] || ''}`:value.raw || `${value.start || '시작 제한 없음'} ~ ${value.end || '종료 제한 없음'}`):(values[value] || String(value));

const correctionReasons={
  disabled:'원문으로만 검색하도록 선택했습니다.',
  invalid_edits:'보정 제안의 형식을 확인하지 못했습니다.',
  invalid_span:'바꾸려는 부분이 원문과 정확히 일치하지 않았습니다.',
  partial_word:'단어 일부만 바꾸면 뜻이 달라질 수 있어 적용하지 않았습니다.',
  protected_entity:'인물이나 장소 이름이 바뀔 수 있어 적용하지 않았습니다.',
  protected_expression:'숫자나 보호해야 할 표현이 포함되어 적용하지 않았습니다.',
  unverified_word:'확실하게 보정할 수 있는 일반 단어로 확인되지 않았습니다.',
  unverified_spacing:'뜻을 유지하는 띄어쓰기 변경인지 확인하지 못했습니다.',
  invalid_kind:'지원하는 오타 보정 유형이 아니었습니다.',
  changed_constraints:'날짜·대상·사건 등의 검색 조건이 달라질 수 있어 적용하지 않았습니다.',
  embedding_failed:'보정 표현의 검색 처리가 실패해 원문으로 검색했습니다.',
  unsupported_intent:'전체 횟수나 순위 집계는 지원하지 않아 검색을 실행하지 않았습니다.',
};
const expansionReasons={...correctionReasons,embedding_failed:'확장 표현의 검색 처리가 실패해 원문으로 검색했습니다.'};

export function correctionView(node, correction, {originalQuery='', evidence=[], retry=null}={}) {
  if(!correction)return null; // Older answers have no correction history.
  const applied=correction.status==='applied', disabled=correction.reason==='disabled';
  const edits=correction.edits || [];
  const label=applied?edits.map(e=>`${e.before} → ${e.after}`).join(' · ') || '보정 표현 확인':
    disabled?'원문으로만 검색':correction.status==='rejected'?'보정 미적용':'보정 없음';
  const panel=node('details',undefined,'query-correction');
  panel.append(node('summary',`오타 보조 검색 · ${label}`));
  panel.append(node('p',`검색 원문: ${correction.original_query || originalQuery || correction.query}`,'correction-query'));
  if(applied){
    panel.append(node('p',`보정 표현: ${correction.query}`,'correction-query'));
    const list=node('ul');
    for(const edit of edits)list.append(node('li',`${edit.before} → ${edit.after} · ${edit.kind==='spacing'?'띄어쓰기':'철자'} 보정`));
    panel.append(list);
    panel.append(node('p',correction.searched===false?
      correction.reason==='unsupported_intent'?correctionReasons.unsupported_intent:
      '검색 조건에 맞는 기록이 없어 보정 표현으로 검색하지 않았습니다.':
      correction.searched===true?'원문과 보정 표현으로 의미·키워드 검색을 함께 했습니다.':
      '보정 표현을 준비했습니다. 이전 검색의 실행 여부는 기록되어 있지 않습니다.'));
    const matching=evidence.filter(r=>r.search_explanation?.corrected_retrieval?.query===correction.query);
    if(correction.searched===true && matching.length){
      const count=matching.filter(r=>r.search_explanation.corrected_retrieval.contributed).length;
      panel.append(node('p',count?`표시된 근거 중 ${count}건의 검색 순위에 보정 표현이 반영됐습니다.`:
        '표시된 근거의 검색 순위는 원문 검색 결과를 유지했습니다.','muted'));
    }else if(correction.searched===true){
      panel.append(node('p','보조 검색을 실행했지만 최종 근거에서의 반영 내역은 없습니다.','muted'));
    }
    panel.append(node('p','원문과 같은 날짜·인물 등의 조건을 적용하고, 같은 기록이 두 번 발견돼도 점수를 중복해서 더하지 않습니다.','muted'));
    if(retry)panel.append(retry);
  }else{
    panel.append(node('p',correctionReasons[correction.reason] ||
      (correction.status==='rejected'?'보정의 안전성을 확인하지 못해 원문 검색을 유지했습니다.':'자동으로 보정할 오타가 확인되지 않아 원문을 사용했습니다.')));
  }
  panel.append(node('small','입력한 질문과 저장된 기록은 수정하지 않습니다.','muted'));
  return panel;
}

export function highlight(node, text, matches=[], className='keyword-highlight') {
  const target=node('span'), chars=Array.from(text), ranges=[];
  for(const match of matches) {
    if(!Number.isInteger(match.start)||!Number.isInteger(match.end)||match.start<0||match.end<=match.start||match.end>chars.length||chars.slice(match.start,match.end).join('')!==match.quote)continue;
    ranges.push([match.start,match.end]);
  }
  ranges.sort((a,b)=>a[0]-b[0]);
  const merged=[];
  for(const range of ranges){const last=merged.at(-1);if(last&&range[0]<=last[1])last[1]=Math.max(last[1],range[1]);else merged.push([...range]);}
  let cursor=0;
  for(const [start,end] of merged){target.append(document.createTextNode(chars.slice(cursor,start).join('')),node('mark',chars.slice(start,end).join(''),className));cursor=end;}
  target.append(document.createTextNode(chars.slice(cursor).join('')));return target;
}

export function expansionView(node, expansion) {
  if(!expansion)return null;
  const kinds={translation:'번역',transliteration:'발음 표기',similar:'유사어'};
  const panel=node('details',undefined,'query-expansion');
  panel.append(node('summary',`번역·발음·유사어 검색 · ${expansion.searched?'실행':expansion.status==='rejected'?'미적용':expansion.edits?.length?'미실행':'추가 확장 없음'}`));
  for(const edit of expansion.edits || [])panel.append(node('p',`${edit.before} → ${edit.after} · ${kinds[edit.kind] || edit.kind}`));
  for(const item of expansion.rejected || [])panel.append(node('p',`${item.before} · ${correctionReasons[item.reason] || (item.reason==='ambiguous_expression'?'여러 의미로 해석될 수 있어 확장하지 않았습니다.':item.reason==='query_limit'?'보조 검색 개수 제한으로 적용하지 않았습니다.':item.reason==='language_mismatch'?'한영 대응 표현으로 확인되지 않아 적용하지 않았습니다.':'검색 표현을 확인하지 못해 적용하지 않았습니다.')}`,'muted'));
  if(expansion.reason)panel.append(node('p',expansionReasons[expansion.reason] || '확장 표현을 확인하지 못해 원문 검색을 유지했습니다.','muted'));
  if(expansion.edits?.length && !expansion.searched && !expansion.reason)panel.append(node('p','검색 조건에 맞는 후보가 없어 확장 검색을 실행하지 않았습니다.','muted'));
  panel.append(node('small','검색 표현은 사실 근거가 아닙니다. 답변은 원문 질문과 기록으로 확인합니다.','muted'));
  return panel;
}

export function explanation(node,row) {
  const info=row.search_explanation;
  if(!info)return null;
  const section=node('section',undefined,'search-explanation');
  const tags=node('div',undefined,'search-tags');
  for(const method of info.methods || [])tags.append(node('span',methods[method] || method,'search-tag'));
  section.append(tags);
  const expansion=info.query_expansion;
  if(expansion){
    const kinds={translation:'번역',transliteration:'발음 표기',similar:'유사어'};
    for(const edit of expansion.edits || [])section.append(node('p',`${edit.before} → ${edit.after} · ${kinds[edit.kind] || edit.kind} · ${expansion.searched?'보조 검색 실행':'미실행'}`,'muted'));
    if(expansion.status==='rejected')section.append(node('p',`확장 미적용 · ${expansionReasons[expansion.reason] || '검색 표현을 확인하지 못해 원문 검색을 유지했습니다.'}`,'muted'));
    for(const run of expansion.retrieval || []){
      section.append(node('p',`${kinds[run.kind]} 검색: ${run.query} · 가중치 ${run.weight} · ${run.contributed?'통합 순위에 반영':'기존 순위 유지'}`,'muted'));
      for(const field of ['source_text','content']){
        const spans=(run.keyword_matches || []).filter(m=>m.field===field);
        if(spans.length && typeof row[field]==='string'){const line=node('p');line.append(node('small',`${kinds[run.kind]} 표현 일치 · `),highlight(node,row[field],spans));section.append(line);}
      }
    }
  }
  const corrected=info.corrected_retrieval;
  if(corrected?.query){
    section.append(node('p',`보조 검색: ${corrected.query} · 의미 순위 ${corrected.semantic_rank ?? '없음'} · 키워드 순위 ${corrected.keyword_rank ?? '없음'} · 가중치 0.8 · ${corrected.contributed?'결합 순위에 반영':'원문 순위 유지'}`,'muted'));
    const matches=corrected.keyword_matches || [];
    for(const field of ['source_text','content']){
      const spans=matches.filter(m=>m.field===field);
      if(spans.length && typeof row[field]==='string'){const line=node('p');line.append(node('small','보정 표현 일치 · '),highlight(node,row[field],spans));section.append(line);}
    }
  }
  for(const condition of info.conditions || [])section.append(node('p',`${conditions[condition.condition] || condition.condition}: ${valueText(condition.value)} · ${condition.status==='matched'?'조건 통과':'원문 확인 필요'}`,'muted'));
  if(!info.conditions?.length)section.append(node('p','별도 조건 통과 정보 없음','muted'));
  const selected=info.final_selection || info.selection;
  if(selected)section.append(node('p',reasons[selected.reason] || '선택 사유 미수집'));
  if(info.selection?.reason==='model_selected' && selected?.reason!=='model_selected')section.append(node('small',reasons.model_selected,'muted'));
  if(info.model_assessment){section.append(node('p',reasons[info.model_assessment.category] || 'AI 관련성 판단'));if(info.model_assessment.quote)section.append(node('blockquote',info.model_assessment.quote));}
  const matches=info.keyword_matches || [];
  if(matches.length){
    const details=node('details');details.append(node('summary','검색어가 일치한 부분 · 노란색'));
    const terms=[...new Set(matches.map(m=>`${m.term} (${m.match_type==='alias'?'등록 별칭':m.kind==='exact'?'글자 일치':'표현 정규화'})`))];
    details.append(node('p',terms.join(' · ')));
    for(const field of ['source_text','content']){
      const spans=matches.filter(m=>m.field===field);if(!spans.length||typeof row[field]!=='string')continue;
      details.append(node('small',field==='source_text'?'원문':'정리된 기억에서 일치','muted'));
      const text=node('p');text.append(highlight(node,row[field],spans));details.append(text);
    }
    section.append(details);
  }
  const ranks=info.ranks || {};
  section.append(node('small',Object.entries(ranks).filter(([,rank])=>rank!=null).map(([key,rank])=>`${({keyword:'키워드',semantic:'의미',combined:'통합'})[key]} ${rank}위`).join(' · '),'muted'));
  return section;
}

const answerReasons={invalid_review_source_quote:'검증 AI가 원문에 없는 문장을 인용함',invalid_review_citation:'검증 AI가 다른 기록의 근거를 연결함',inconsistent_review:'검증 AI의 근거 판정과 오류 판정이 서로 모순됨',cited:'답변에 인용됨',draft_not_cited:'최종 초안에서 인용하지 않음 · 세부 사유가 기록되지 않음',citation_removed:'답변 검증에서 인용 제거',answer_rejected:'답변 전체가 검증을 통과하지 못해 사용되지 않음',details_unavailable:'세부 사유가 기록되지 않음',clarification_required:'질문 확인이 필요하여 답변 생성 미실행',no_relevant_evidence:'답변 전 관련성 검사에서 사용할 근거 없음 · 세부 사유가 기록되지 않음',no_evidence:'답변에 사용할 근거 없음',unsupported_query:'지원하지 않는 질문 유형으로 답변 생성 미실행',attributes_unsupported:'답변의 속성 또는 인과관계를 근거로 확인하지 못함',invalid_review:'검증 결과 형식 또는 인용문 확인 실패',answer_incomplete:'질문에 필요한 답변 내용 부족',excessive_abstention:'근거가 있는데도 답변을 보류함',claim_unsupported:'답변 문장을 뒷받침하는 근거 부족',claim_irrelevant:'답변 문장이 질문과 관련되지 않음',review_issue_person:'답변의 인물 정보 문제',review_issue_time:'답변의 시점 정보 문제',review_issue_negation:'답변의 부정 표현 문제',review_issue_execution:'답변의 계획·실행 구분 문제',review_issue_quotation:'답변의 인용 문제',review_issue_cause:'답변의 인과관계 문제',review_issue_other:'답변 검증의 기타 문제 · 세부 사유가 기록되지 않음'};
const stageStates={passed:'조건 통과',failed:'조건 탈락',needs_review:'원문 확인 필요',selected:'선택됨',excluded:'제외됨',used:'사용됨',unused:'미사용',not_run:'미실행'};
const reasonText=code=>answerReasons[code] || reasons[code] || '세부 사유가 기록되지 않음';

export function answerAuditView(node,audit) {
  if(!audit)return null;
  const section=node('section',undefined,'answer-audit');
  if(audit.status==='rejected')section.append(node('p','답변 전체 검증 실패 · 개별 기록이 틀렸다는 뜻은 아닙니다.'));
  if(audit.reason)section.append(node('p',reasonText(audit.reason)));
  for(const [index,attempt] of (audit.attempts || []).entries()) {
    const label=index===0?'초안 검증':attempt.generation && attempt.generation===audit.attempts[index-1]?.generation?'같은 답변 검증 재시도':'재작성 검증';
    section.append(node('p',`${label}: ${attempt.status==='passed'?'통과':'실패'}${attempt.reasons?.length?' · '+attempt.reasons.map(reasonText).join(' · '):''}`));
  }
  return section;
}

export function auditView({node,action,api}, audit, citedIds=new Set(), evidence=[], answerAudit=null) {
  if(!audit?.candidates?.length)return null;
  const details=node('details',undefined,'search-audit');
  details.append(node('summary',`기록별 선택·제외 이유 ${audit.candidates.length}건`));
  for(const item of audit.candidates){
    const entry=node('div',undefined,'search-audit-row');
    const status=citedIds.has(item.id)?'답변에 인용됨':item.final_status==='excluded'?'통합 선택에서 제외됨':item.status==='selected'?'검토 후보 · 답변 인용 없음':'검색에서 제외됨';
    entry.append(node('p',`${status} · ${reasons[item.final_reason || item.reason] || '사유 미수집'}`));
    if(item.stages) {
      for(const [key,label] of [['conditions','조건 검사'],['selection','근거 선택'],['answer','답변 사용']]) {
        const usage=answerAudit?.usage?.find(row=>row.id===item.id);
        const stage=key==='answer'?(usage || (citedIds.has(item.id)?{status:'used',reason:'cited'}:answerAudit?item.stages.answer:{reason:'details_unavailable'})):item.stages[key];
        if(!stage)continue;
        entry.append(node('p',`${label}: ${stageStates[stage.status] || '상태 미수집'}${stage.reason?' · '+reasonText(stage.reason):''}${key==='selection' && stage.limit?` · 최대 ${stage.limit}개`:''}`,'audit-stage'));
      }
    } else if(!citedIds.has(item.id)) {
      entry.append(node('p','답변 사용: 세부 사유가 기록되지 않음','muted'));
    }
    for(const [index,attempt] of (answerAudit?.attempts || []).entries()) {
      if(!answerAudit.usage?.some(row=>row.id===item.id))continue;
      const cited=attempt.draft_citations.includes(item.id);
      const result=attempt.status==='rejected'?'답변 전체 검증 실패':cited&&!attempt.reviewed_citations.includes(item.id)?'검증에서 인용 제거':'검증 통과';
      entry.append(node('small',`${index===0?'초안':attempt.generation && attempt.generation===answerAudit.attempts[index-1]?.generation?'같은 답변 검증 재시도':'재작성'}: ${cited?'인용함':'인용하지 않음'} · ${result}`,'audit-attempt'));
    }
    const ranks=Object.entries(item.ranks || {}).filter(([,rank])=>rank!=null).map(([key,rank])=>`${({keyword:'키워드',semantic:'의미',combined:'통합'})[key] || key} ${rank}위`);
    if(ranks.length)entry.append(node('small',ranks.join(' · '),'muted'));
    entry.append(action(`기록 ${item.record_id.slice(0,8)} · 버전 ${item.version} 확인`,async()=>{
      try {const record=await api('/records/'+encodeURIComponent(item.record_id));
        if(record.version!==item.version){entry.append(node('p','검색 당시와 다른 버전입니다. 다시 검색하면 현재 기록으로 확인할 수 있습니다.'));return;}
        const text=node('pre',record.text);entry.append(text);
      }catch{entry.append(node('p','현재 이 기록을 열 수 없습니다. 삭제 또는 접근 상태를 확인해 주세요.'));}
    },'link'));
    for(const condition of item.conditions || [])entry.append(node('small',`${conditions[condition.condition] || condition.condition}${condition.expected!==undefined?' · 요청 조건: '+valueText(condition.expected):''} · ${condition.status==='matched'?'조건 통과':condition.status==='failed'?'조건 탈락 · '+reasonText(condition.reason):'원문 확인 필요'} `,'muted'));
    const row=evidence.find(row=>row.id===item.id);if(row){const why=explanation(node,row);if(why)entry.append(why);}
    if(item.methods?.length)entry.append(node('small',item.methods.map(m=>methods[m]).join(' · '),'muted'));
    details.append(entry);
  }
  if(audit.truncated)details.append(node('p',`조건 제외 ${audit.excluded_count}건 중 최대 100건 표시`,'muted'));
  if(audit.candidate_limit_count)details.append(node('p',`통합 후보 24개 제한으로 ${audit.candidate_limit_count}개가 추가 제외됨`,'muted'));
  return details;
}
