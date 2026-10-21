"""Explicit variable → executable behavior contracts (no category-wide fallback).

Every entry names assertions and actual product tests. Model doubles verify the
control/storage/security contract, not the accuracy of a generation/embedding model.
Unsupported product features have executable negative capability checks and remain
UNSUPPORTED, never PASS for the absent feature.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def expand(value):
    for token in value.split():
        if ".." in token:
            first, last = token.split("..")
            category, start = first.split("-")
            for number in range(int(start), int(last) + 1):
                yield f"{category}-{number:02}"
        else:
            yield token


def contracts():
    result = {}
    def bind(ids, module, functions, assertions, *, unsupported=False, scope="product_behavior"):
        tests = [f"tests/{module}.py::test_{name}" for name in functions.split()]
        for vid in expand(ids):
            entry = result.setdefault(vid, {"variable_id": vid, "tests": [], "assertions": [],
                                           "scope": scope, "unsupported": unsupported,
                                           "support_reference": "docs/behavior_test_coverage.md"})
            entry["tests"] = sorted(set(entry["tests"] + tests))
            entry["assertions"].append(assertions)
            if unsupported:
                entry["unsupported"] = True
                entry["scope"] = "unsupported_capability_rejection"

    bind("IN-01..04 IN-45 IN-61 IN-73..85", "test_behavior_operations", "input_roundtrip_and_source_boundaries", "입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다.")
    bind("IN-05 IN-06 IN-17 EX-24 QI-24 MW-01..04 MW-16 MW-23 MW-24", "test_memory_capture", "approval_and_restart modes_reference_and_provenance", "승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다.")
    bind("IN-07 IN-16 ST-02 ST-03 LC-19", "test_memory_capture", "duplicate_correction_delete distinct_facts_are_never_automatic_duplicates", "중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다.")
    bind("IN-08 IN-10..13 LC-18", "test_behavior_operations", "unsupported_file_formats_are_rejected_without_records", "지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다.", unsupported=True)
    bind("IN-14 IN-15 ST-11 ST-12 ST-19 SEC-03 SEC-07 SEC-17 SEC-18 RT-09 RT-15..17 RT-20 RT-24 RT-29 RT-31", "test_behavior_operations", "unsupported_fields_and_permissions_are_rejected", "공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다.", unsupported=True)
    bind("IN-18 ST-25 PF-22 LC-30", "test_memory_complete", "natural_capture_response_retry_is_idempotent", "같은 저장 요청의 재전송이 원문·작업을 중복 생성하지 않는다.")
    bind("IN-19 ST-18", "chat/test_integration", "concurrent_version_updates_and_message_begin generation_cannot_overwrite_concurrent_context_update", "동시 쓰기의 한 요청만 성공하며 오래된 버전은 충돌로 거절하고 최신 문맥을 덮어쓰지 않는다.")
    bind("IN-20 ST-01 ST-04..06 ST-10", "test_behavior_operations", "record_versions_preserve_original_and_invalidate_derived", "신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다.")
    bind("IN-44 SEC-10 SEC-11 MW-13", "test_conversation_policy", "sensitive_sources_require_relevant_explicit_topic memory_refusal_precedes_all_routes", "민감 정보는 명시한 주제에만 사용하며 기록 사용 거부가 모든 검색 경로보다 우선한다.")
    bind("IN-62..65 QU-17 QU-33 CV-13..16 AG-07 AG-08", "test_conversation_uxr", "UXR01_clear_answer_has_no_choice UXR02_actual_ambiguity_uses_source_target_ids", "명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다.")
    bind("IN-66..69 ST-07 ST-23 QI-11 QI-12 QI-16 RR-06 RR-07 EV-09 EV-11 AG-12 MW-07 MW-11", "test_conversation_policy", "explicit_conflict_guard_preserves_dates_projects_and_conditions", "같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다.")
    bind("EX-06 EX-07 RT-07 RT-08", "test_chat_grounding", "generation_time_metadata_is_scoped_to_question", "저장/사건/수정 시각을 구분하며 질문이 요구한 종류의 시각만 답변 근거로 사용한다.")
    bind("EX-06 EX-07 RT-07 RT-08", "test_behavior_operations", "created_modified_and_event_times_are_distinct", "수정 전 원문과 저장일·수정일·실제 사건일이 서로 다른 실제 DB의 값을 대조한다.")
    bind("EX-17 MW-10", "test_memory_capture", "existing_record_correction_and_stale_version index_publication_correction_and_delete", "정정은 기존 원문에 새 버전을 만들며 오래된 승인/색인과 삭제된 기억이 재사용되지 않는다.")
    bind("EX-21 EX-22", "test_conversation_policy", "upload_atomic_idempotent_offsets_and_lifecycle", "직접 원문·파일 청크·대화 메시지의 출처를 보존하고 위치가 원문과 일치하며 원본 삭제를 반영한다.")
    bind("EX-23 SEC-02 SEC-06 LC-10", "chat/test_integration", "owner_isolation_covers_all_access api_security_pagination_and_alias", "내부 owner와 실제 인증/CSRF 경계를 구분하고 타 owner의 조회·수정·삭제·요청 상태를 차단한다.", scope="single_account_auth_and_internal_owner")
    bind("ST-08 RR-23 CV-23", "test_identity_semantics", "current_explicit_role_wins other_person_cannot_supply_profession_even_if_model_approves", "명시한 역할의 동명이인만 사용하며 다른 사람의 직업/사건을 인용하지 않는다.")
    bind("ST-09 RR-16 RR-24 EV-05 AG-13", "test_evaluation_remediation", "scope_namesake_and_preference_are_not_merged optional_background_is_not_a_required_citation", "프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다.")
    bind("ST-13 ST-14 ST-20 ST-21 SEC-04 SEC-05 SEC-13 MW-12 QI-25 AG-25 CV-21", "test_behavior_operations", "deletion_removes_sources_indexes_and_cached_answers", "여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다.")
    bind("ST-16", "test_memory_capture", "atomic_commit_rolls_back_job_failure", "작업 생성 실패 시 저장 트랜잭션 전체를 롤백한다.")
    bind("ST-17 RR-36 PF-12", "test_memory_capture", "failed_index_retry_and_pending_rejection", "색인 실패와 대기를 검색 결과 없음과 구분하고 재시도 후 최신 버전만 게시한다.")
    bind("ST-22", "test_conversation_policy", "upload_atomic_idempotent_offsets_and_lifecycle", "긴 문서를 청크로 나누어 한 번만 저장하고 재전송/취소/삭제의 원문 위치를 보존한다.")
    bind("ST-24", "test_behavior_operations", "indexing_pending_is_distinct_from_empty_corpus", "저장 직후 queued 상태, 실패, ready_empty 상태와 검색 가능한 상태를 실제 API에서 구분한다.")
    bind("QI-10 QI-13 AG-17 AG-21 EV-23 EV-25", "test_behavior_operations", "summary_keeps_all_facts_and_event_order", "서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다.")
    bind("QI-17", "test_search_explain", "current_state_keeps_event_date_order_across_queries", "처음/최신 순서는 저장 시각이 아니라 사건 시각으로 선택한다.")
    bind("QI-18 MW-08 MW-09", "test_memory_capture", "decision_capture_uses_actual_turns_and_preferences_update", "승인한 선호와 규칙만 실제 메시지 출처에서 저장하고 변경된 선호를 다시 읽는다.")
    bind("QI-19 QU-06 QU-18 QU-19 CV-02 CV-03 CV-08 CV-18 CV-19", "test_identity_semantics", "followup_uses_source_backed_immediate_user_role ambiguous_or_unverified_reference_is_not_invented", "직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다.")
    bind("QI-20 QI-23 AG-01 AG-02 CV-25", "test_conversation_policy", "general_turn_never_reads_preferences_or_searches short_social_reply_is_not_empty_when_model_echoes", "일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다.")
    bind("QI-21 AG-04", "test_conversation_uxr", "UXR19_mixed_sources_are_separate", "개인 근거와 일반 제안을 서로 다른 출처 종류로 표시한다.")
    bind("QI-22 AG-05", "test_behavior_operations", "explicit_search_and_conversation_have_distinct_routes", "명시적 검색은 검색 응답을 반환하고 일반 대화와 모드/검색 실행 수가 구분된다.")
    bind("QU-01..05 QU-29 RR-01 RR-02 RT-21", "test_search_explain", "exact_matches_outweigh_normalized_and_summary_is_separate keyword_matching_uses_whole_tokens_and_retains_short_keywords", "정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다.")
    bind("QU-07 QU-21 RR-22 AG-16", "test_compound_execution", "compound_parts_are_literal_independent_questions literal_facets_keep_separate_retrieval_conditions_and_next_search_review", "복합 질문의 각 조건을 원문 그대로 분해하고 질문별 독립 검색과 후속 근거 확인을 수행한다.")
    bind("QU-08..10 QU-13 QU-14 QU-23 RR-18", "test_search_expressions", "aliases_are_symmetric_and_duplicate_terms_do_not_add_scores expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection", "한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다.")
    bind("QU-11 QU-12", "test_query_correction", "bounded_spelling_and_unicode_offsets spacing_and_invalid_spans protected_or_unverified_expressions", "오타와 띄어쓰기만 검증한 범위에서 교정하며 식별자·부정·수치를 변경하지 않는다.")
    bind("QU-15 QU-16 QU-39", "test_search_expressions", "expansion_rejects_constraints_and_ambiguous_or_invalid_edits ambiguous_translation_agrees_with_specific_context", "모호한 동음이의어·주제 밖 확장·부정확한 번역은 실제 원문 문맥 확인 없이 사용하지 않는다.")
    bind("QU-20 RR-33 EV-07", "test_compound_execution", "plan_draft_preserves_future_plan_and_limits_execution_claim model_approval_cannot_make_plan_only_answer_fulfill_execution_question", "계획·부정·실행 미확인을 실제 완료로 바꾸지 않는다.")
    bind("QU-22 RT-02..06 RT-23", "test_behavior_operations", "temporal_and_compound_filters_preserve_constraints", "상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다.")
    bind("QU-31 QU-32 RR-32", "test_compound_execution", "causal_check_does_not_require_a_cause_for_independent_profession_fact dependent_or_single_question_is_not_split", "독립 사실과 인과 연결을 구분하고 원문에 없는 원인·결과 관계를 요구하거나 만들지 않는다.")
    bind("QU-34", "test_behavior_operations", "quoted_commands_are_data_not_actions", "과거 발언 안의 검색·저장 명령을 현재의 실행 요청으로 수행하지 않는다.")
    bind("QU-38", "test_search_expressions", "symbol_and_fullwidth_spans distinct_identifiers_do_not_match", "정규식 기호·따옴표·경로·전각 표기의 원문 범위를 보존한다.")
    bind("QU-40", "test_behavior_operations", "conflicting_filter_bounds_are_rejected_without_search", "서로 모순되는 날짜 조건은 입력 오류로 거절하며 검색/모델 호출을 하지 않는다.")
    bind("RT-01 RT-12 RT-13 RT-14 RT-18 RT-19 RT-25", "test_behavior_operations", "temporal_and_compound_filters_preserve_constraints", "전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다.")
    bind("RT-10 RT-11", "test_search_explain", "current_state_keeps_event_date_order_across_queries", "여러 검색어에서 최신/최초 사건 순서를 전역으로 보존한다.")
    bind("RT-22 RR-03 RR-04 RR-05 RR-31", "test_search_explain", "service_propagates_model_assessment direct_and_counter_evidence_outrank_background", "실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다.")
    bind("RT-26 RT-27 RR-25 RR-30 AG-10", "test_conversation_uxr", "UXR08_empty_search_has_retry_and_no_fake_facts UXR07_partial_answer_keeps_uncertainty", "없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다.")
    bind("RT-28 RR-26", "test_search_accuracy", "original_top_eight_remain_in_24_candidate_review_pool", "원래 상위 근거를 검토 풀에서 잃지 않고 최종 Top-K를 전역 적용한다.")
    bind("RT-30 RR-28 EV-26", "test_conversation_uxr", "UXR04_same_fact_keeps_all_provenance_without_counting_independent_confirmation", "동일 사실의 여러 출처를 보존하되 독립적인 확증으로 중복 계산하지 않는다.")
    bind("RT-32 AG-26", "chat/test_integration", "store_idempotency_context_restart_and_pagination", "현재 대화는 장기 원문으로 자동 저장하지 않으면서 요약·페이지·재시작 문맥을 보존한다.")
    bind("RR-08 EV-20 EV-22 EV-28 MW-15 MW-21 AG-34 AG-35", "test_memory_capture", "ai_extraction_cannot_become_personal_fact expiry_version_and_ai_type", "사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다.")
    bind("RR-09..14 RR-15", "test_behavior_operations", "chunk_hierarchy_preserves_exact_source_and_bounds", "긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다.")
    bind("RR-17", "test_query_correction", "constraint_changing_edit_is_rejected search_batch_provenance_and_same_filter_scope", "질문 재작성 뒤에도 원래 날짜·부정·식별자 조건과 검색 출처를 보존한다.")
    bind("RR-19 RR-20", "test_search_expressions", "expansion_limits_weights_duplicates_and_context expansion_embedding_failure_and_empty_candidates_keep_original", "확장을 한 번에 결합하고 중복 기여를 제한하며 확장 실패 시 원래 검색을 유지한다.")
    bind("RR-21 AG-11", "test_search_explain", "chat_defers_eight_record_limit_until_all_queries_are_combined", "여러 검색 결과를 합치기 전에 일찍 자르지 않고 늦게 찾은 강한 근거도 포함한다.")
    bind("RR-27 PF-24 CV-09", "test_behavior_operations", "long_conversation_budget_preserves_sources", "긴 대화에서 과거 문맥을 압축하고 토큰 예산 부족을 오류로 구분하며 근거를 새 사실로 만들지 않는다.")
    bind("RR-29 RR-35 EV-18 SEC-19", "test_database_performance", "cached_search_after_edit_trash_and_model_change", "수정·삭제·임베딩 모델 변경 직후 기존 캐시/벡터를 검색에서 제외한다.")
    bind("RR-34", "test_behavior_operations", "units_and_numbers_are_not_equivalent_by_spelling", "3.5km/3500m는 같은 거리이고 3.5m·소수점 제거·부정은 동등하지 않다.")
    bind("EV-10 EV-14 AG-14", "test_behavior_operations", "multiple_required_evidence_groups_are_independent", "필수 근거 그룹 중 하나가 누락되면 전체 답변 성공으로 판정하지 않는다.")
    bind("EV-12 EV-15..17 EV-29 EV-30 AG-33", "test_chat_grounding", "review_uses_only_original_spans_and_display_cannot_reject_facts source_selection_never_bypasses_semantic_or_identity_checks", "존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다.")
    bind("EV-21", "test_conversation_policy", "general_generation_never_receives_unverified_interpretation no_search_record_absence_claim_is_rejected_even_if_model_approves", "검증하지 않은 해석·일반 지식을 사용자 이력이나 검색 결과로 표시하지 않는다.")
    bind("EV-24", "test_behavior_operations", "comparisons_require_matching_subject_time_and_units", "다른 프로젝트·시점·조건·단위를 무시한 단순 비교를 확정 사실로 채택하지 않는다.")
    bind("CV-01 AG-03 AG-06 CV-24 CV-30", "test_evaluation_remediation", "private_identifiers_override_general_classifier disabled_or_explicit_general_never_reads_the_corpus", "실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다.")
    bind("CV-04", "test_conversation_uxr", "UXR03_selected_followup_preserves_topic_feature", "사용자가 선택한 결과 ID의 주제·속성으로만 후속 질문을 연결한다.")
    bind("CV-05 CV-06 CV-07 CV-12 CV-22 CV-26 CV-27 AG-22", "test_behavior_operations", "context_changes_preserve_only_still_valid_constraints", "주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다.")
    bind("CV-10 CV-11 CV-17", "chat/test_integration", "store_idempotency_context_restart_and_pagination owner_isolation_covers_all_access", "세션·재시작·같은 요청 재전송의 문맥과 접근 범위를 보존한다.")
    bind("CV-20 MW-18", "test_memory_capture", "selection_and_cross_session_sources approval_and_restart", "대화 저장은 실제 선택 메시지와 원문 출처를 검증한 승인 경로로만 세션을 넘어 유지된다.")
    bind("CV-28 AG-36", "test_model_reuse", "reuses_only_same_request_and_returns_isolated_values question_full_revision_preprocessing_model_and_policy_invalidate", "같은 요청의 재생성/캐시만 재사용하고 질문·원문 버전·모델·정책이 바뀌면 다시 처리한다.")
    bind("CV-29", "test_conversation_policy", "memory_refusal_precedes_all_routes refusal_scrubs_all_recalled_sources_and_assistant_claims", "기록을 쓰지 말라는 요청이 검색/선호/이전 AI 주장보다 우선한다.")
    bind("AG-18..20", "test_chat_presentation", "reviewed_kinds metadata_rejection_does_not_remove_answer", "문단·목록·표·상세/간결 표현의 표시 제안도 검증한 주장만 참조하며 표시 실패로 사실 답변을 없애지 않는다.")
    bind("AG-23 AG-24", "test_memory_complete", "review_links_edit_invalidation_and_idempotency snapshot_change_rejects_approval", "저장·수정은 원문 미리보기·승인·버전 확인을 거치며 재전송은 멱등적이다.")
    bind("AG-27 MW-17 MW-22", "test_memory_complete", "extraction_rejects_fabricated_source correction_preserves_ai_origin", "대화 요약/이전 AI 응답만으로 사용자 사실을 만들지 않고 원문과 제안 출처를 추적한다.")
    bind("AG-28", "test_conversation_uxr", "UXR10_recommendation_is_an_optional_suggestion UXR09_resume_action_cannot_invent_curriculum", "추천과 다음 단계는 일반 제안으로 표시하며 과거 기록의 확정 사실로 지어내지 않는다.")
    bind("AG-30", "test_conversation_policy", "general_generation_never_receives_unverified_interpretation", "외부 실시간 검색 기능이 없어 현재 외부 값을 개인 기록으로 확정하지 않는다.")
    bind("AG-31 AG-32", "test_behavior_operations", "http_failures_are_errors_not_empty_answers", "실제 HTTP 경로의 모델 연결 실패·시간 초과·잘못된 응답은 오류와 재시도 상태로 전달한다.")
    bind("MW-06", "test_memory_capture", "decision_capture_uses_actual_turns_and_preferences_update", "프로젝트 목표·결정은 실제 대화 출처의 승인한 기억으로만 활용한다.")
    bind("MW-20 SEC-20", "test_memory_complete", "archival_and_retention archived_record_stays_excluded_after_legacy_restore", "만료/보존 처리와 복원에서 보관 상태를 보존하고 만료된 기억을 활성 검색에 되살리지 않는다.")
    bind("SEC-12", "test_response_latency", "failure_measurement_never_includes_exception_or_request_text transport_usage_is_allowlisted", "로그·성능·오류 진단에는 원문/모델 응답/비밀 오류 문자열을 저장하지 않는다.")
    bind("SEC-14 UI-01..25", "test_behavior_operations", "ui_contracts", "실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다.", scope="browser_dom_and_presentation")
    bind("UI-22", "test_behavior_operations", "unsupported_fields_and_permissions_are_rejected", "검색 결과 offset 페이지 API는 현재 지원하지 않으므로 거절을 검사한다. 대화 목록 페이지와 혼동하지 않는다.", unsupported=True)
    bind("IN-14 IN-15 ST-19 SEC-07 SEC-17 SEC-18", "test_behavior_operations", "unsupported_capability_routes_are_absent", "인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다.", unsupported=True)
    bind("SEC-15 SEC-16", "test_conversation_policy", "upload_invalid_content", "경로 순회·NUL·허용하지 않는 파일·크기 초과를 실제 가져오기 검증에서 거절한다.")
    for number, count in enumerate((0, 1, 100, 1000, 10000, 100000), 1):
        bind(f"PF-{number:02}", "test_behavior_operations", f"corpus_scale_and_bounded_vectors[{count}]", f"{count}건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다.", scope="synthetic_database_scale_not_model_latency")
    bind("PF-07", "test_behavior_operations", "chunk_hierarchy_preserves_exact_source_and_bounds", "허용하는 긴 원문의 청크 경계·위치·원문 복원을 검사한다.")
    bind("PF-08", "test_memory_capture", "distinct_facts_are_never_automatic_duplicates duplicate_correction_delete", "반복 원문은 중복 후보로 식별하되 유사한 다른 사실은 자동 삭제/병합하지 않는다.")
    bind("PF-09..11 PF-21 PF-25", "test_behavior_operations", "concurrent_store_search_and_restart_are_consistent", "동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다.")
    bind("PF-13 PF-26", "test_behavior_operations", "corrupt_database_and_vectors_fail_explicitly", "손상된 DB/벡터는 명확한 오류로 보고하며 성공·빈 결과로 위장하지 않는다.")
    bind("PF-14 PF-15", "test_performance", "extraction_read_timeout_is_not_repeated embedding_retry_reuses_extraction", "모델 시간 초과는 무제한 재시도하지 않고 임베딩 실패 복구 시 성공한 추출을 재사용한다.")
    bind("PF-16", "test_performance", "wait_cancellation_removes_foreground_priority foreground_deadline_does_not_leak_waiter_or_release_owners_lock", "취소/시간 초과는 대기 우선순위와 잠금을 안전하게 해제한다.")
    bind("PF-17", "test_response_latency", "model_comparison_reuses_source_ids_and_only_rebuilds_vectors embedding_profile_separates_index_and_only_prefixes_queries", "임베딩 변경 시 원문 ID와 추출을 고정하고 후보 전용 벡터만 다시 구축한다.")
    bind("PF-18", "test_model_reuse", "reuses_only_same_request_and_returns_isolated_values invalid_quotes_and_model_errors_are_not_cached", "캐시는 같은 요청/검증한 결과만 재사용하며 오류·잘못된 인용은 저장하지 않는다.")
    bind("PF-19", "test_performance_benchmark", "cpu_only_device_messages_cannot_be_labeled_gpu summary_excludes_warmup_and_keeps_failures", "실제 장치와 측정 표본·워밍업·실패를 보존하며 CPU를 GPU 측정으로 표시하지 않는다.")
    bind("PF-20", "test_database_performance", "vector_cache_generation_model_order_subset_and_budget", "캐시 예산을 초과하면 캐시를 해제하고 비정상 벡터를 사용하지 않는다.")
    bind("PF-23", "test_performance", "foreground_runs_before_next_background_call background_wait_outlives_model_http_timeout_and_can_stop", "사용자 요청은 다음 배경 작업보다 우선하며 배경 대기는 취소 가능하다.")
    bind("LC-26", "test_behavior_operations", "year_old_event_is_not_replaced_by_storage_date", "일 년 전 사건의 실제 날짜와 현재 저장일을 구분하고 원문을 보존한다.")
    # Bind precisely to the requested input/capability rather than failing a
    # variable merely because an unrelated field/format changes in the future.
    selected_inputs = {"IN-01":"natural", "IN-02":"keywords", "IN-03":"diary", "IN-04":"multiline", "IN-45":"multiple-events", "IN-61":"identifiers", "IN-73":"unicode", "IN-74":"identifiers", "IN-75":"identifiers", "IN-76":"identifiers", "IN-77":"code", "IN-78":"table", "IN-79":"multiline", "IN-80":"transcript", "IN-81":"transcript", "IN-82":"guess", "IN-83":"possible", "IN-84":"question", "IN-85":"rumor"}
    selected_formats = {"IN-08":["pdf"], "IN-10":["docx"], "IN-11":["csv","json"], "IN-12":["png"], "IN-13":["wav"], "LC-18":["pdf"]}
    selected_fields = {"IN-14":"files", "IN-15":"sync_url", "ST-11":"title", "ST-12":"tags", "ST-19":"acl", "SEC-03":"owner_id", "SEC-07":"acl", "SEC-17":"owner_id", "SEC-18":"owner_id", "RT-09":"date_modified", "RT-15":"source_file", "RT-16":"source_type", "RT-17":"record_type", "RT-20":"importance", "RT-24":"or", "RT-29":"offset", "RT-31":"owner_id", "UI-22":"offset"}
    for table, function in ((selected_inputs,"input_roundtrip_and_source_boundaries"),
                            (selected_formats,"unsupported_file_formats_are_rejected_without_records"),
                            (selected_fields,"unsupported_fields_and_permissions_are_rejected")):
        for vid, parameters in table.items():
            node = "tests/test_behavior_operations.py::test_" + function
            result[vid]["tests"] = sorted([test for test in result[vid]["tests"] if test != node] +
                                          [node + "[" + parameter + "]" for parameter in
                                           (parameters if isinstance(parameters,list) else [parameters])])
    return result


def validate_contracts():
    values = contracts()
    for vid, contract in values.items():
        assert contract["tests"] and contract["assertions"], vid
        for node in contract["tests"]:
            path, name = node.split("::")
            file = (ROOT / path).resolve()
            assert file.is_relative_to((ROOT / "tests").resolve()), node
            tree = ast.parse(file.read_text("utf-8"))
            fn = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name.split("[")[0]), None)
            assert fn is not None and any(isinstance(n, ast.Assert) or isinstance(n, ast.Call) and
                isinstance(n.func, ast.Attribute) and n.func.attr == "raises" for n in ast.walk(fn)), node
    return values
