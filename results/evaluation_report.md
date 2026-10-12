# Evaluation Report

## 1. 실행 정보

- 데이터셋: `datasets/test.jsonl`
- 모델: `Qwen3-8B-Q4_K_M`
- 요청 샘플 수: 120
- 실제 결과 수: 120

## 2. 전체 평가 결과

| 지표 | 결과 |
|---|---:|
| 최종 유효률 | 100.00% |
| 최종 PASS | 120 / 120 |
| 최종 FAIL | 0 |
| 최종 스키마 유효률 | 100.00% |
| 최종 스키마 유효 개수 | 120 |
| Evidence 유효률 | 100.00% |
| Evidence 유효 개수 | 120 |
| 평균 지연 시간 | 7.12s |

## 3. 종료 사유

| 종료 사유 | 개수 |
|---|---:|
| stop | 120 |

## 4. 오류 유형

| 오류 유형 | 개수 |
|---|---:|
| 기록된 오류 없음 | 0 |

## 5. 개별 테스트 결과

| 테스트 ID | 분류 | 최종 결과 | 스키마 | Evidence | 지연 시간 | 메모리 수 | Source ID | 오류 단계 |
|---|---|---|---|---|---:|---:|---|---|
| BASIC-001 | basic_facts_preferences | PASS | PASS | PASS | 5.96s | 1 | src-basic-001 | - |
| BASIC-002 | basic_facts_preferences | PASS | PASS | PASS | 5.49s | 1 | src-basic-002 | - |
| BASIC-003 | basic_facts_preferences | PASS | PASS | PASS | 5.57s | 1 | src-basic-003 | - |
| BASIC-004 | basic_facts_preferences | PASS | PASS | PASS | 6.50s | 1 | src-basic-004 | - |
| BASIC-005 | basic_facts_preferences | PASS | PASS | PASS | 5.85s | 1 | src-basic-005 | - |
| BASIC-006 | basic_facts_preferences | PASS | PASS | PASS | 5.80s | 1 | src-basic-006 | - |
| BASIC-007 | basic_facts_preferences | PASS | PASS | PASS | 5.70s | 1 | src-basic-007 | - |
| BASIC-008 | basic_facts_preferences | PASS | PASS | PASS | 5.66s | 1 | src-basic-008 | - |
| BASIC-009 | basic_facts_preferences | PASS | PASS | PASS | 5.85s | 1 | src-basic-009 | - |
| BASIC-010 | basic_facts_preferences | PASS | PASS | PASS | 5.67s | 1 | src-basic-010 | - |
| BASIC-011 | basic_facts_preferences | PASS | PASS | PASS | 6.05s | 1 | src-basic-011 | - |
| BASIC-012 | basic_facts_preferences | PASS | PASS | PASS | 5.92s | 1 | src-basic-012 | - |
| BASIC-013 | basic_facts_preferences | PASS | PASS | PASS | 5.84s | 1 | src-basic-013 | - |
| BASIC-014 | basic_facts_preferences | PASS | PASS | PASS | 5.89s | 1 | src-basic-014 | - |
| BASIC-015 | basic_facts_preferences | PASS | PASS | PASS | 6.17s | 1 | src-basic-015 | - |
| BASIC-016 | basic_facts_preferences | PASS | PASS | PASS | 5.98s | 1 | src-basic-016 | - |
| BASIC-017 | basic_facts_preferences | PASS | PASS | PASS | 5.85s | 1 | src-basic-017 | - |
| BASIC-018 | basic_facts_preferences | PASS | PASS | PASS | 6.48s | 1 | src-basic-018 | - |
| BASIC-019 | basic_facts_preferences | PASS | PASS | PASS | 6.46s | 1 | src-basic-019 | - |
| BASIC-020 | basic_facts_preferences | PASS | PASS | PASS | 6.19s | 1 | src-basic-020 | - |
| SPLIT-001 | multi_event_segmentation | PASS | PASS | PASS | 7.12s | 1 | src-split-001 | - |
| SPLIT-002 | multi_event_segmentation | PASS | PASS | PASS | 11.99s | 2 | src-split-002 | - |
| SPLIT-003 | multi_event_segmentation | PASS | PASS | PASS | 13.66s | 2 | src-split-003 | - |
| SPLIT-004 | multi_event_segmentation | PASS | PASS | PASS | 13.83s | 2 | src-split-004 | - |
| SPLIT-005 | multi_event_segmentation | PASS | PASS | PASS | 7.24s | 1 | src-split-005 | - |
| SPLIT-006 | multi_event_segmentation | PASS | PASS | PASS | 12.26s | 2 | src-split-006 | - |
| SPLIT-007 | multi_event_segmentation | PASS | PASS | PASS | 7.08s | 1 | src-split-007 | - |
| SPLIT-008 | multi_event_segmentation | PASS | PASS | PASS | 12.23s | 2 | src-split-008 | - |
| SPLIT-009 | multi_event_segmentation | PASS | PASS | PASS | 6.75s | 1 | src-split-009 | - |
| SPLIT-010 | multi_event_segmentation | PASS | PASS | PASS | 11.65s | 2 | src-split-010 | - |
| SPLIT-011 | multi_event_segmentation | PASS | PASS | PASS | 6.59s | 1 | src-split-011 | - |
| SPLIT-012 | multi_event_segmentation | PASS | PASS | PASS | 6.43s | 1 | src-split-012 | - |
| SPLIT-013 | multi_event_segmentation | PASS | PASS | PASS | 6.23s | 1 | src-split-013 | - |
| SPLIT-014 | multi_event_segmentation | PASS | PASS | PASS | 8.51s | 1 | src-split-014 | - |
| SPLIT-015 | multi_event_segmentation | PASS | PASS | PASS | 7.17s | 1 | src-split-015 | - |
| SPLIT-016 | multi_event_segmentation | PASS | PASS | PASS | 6.77s | 1 | src-split-016 | - |
| SPLIT-017 | multi_event_segmentation | PASS | PASS | PASS | 6.39s | 1 | src-split-017 | - |
| SPLIT-018 | multi_event_segmentation | PASS | PASS | PASS | 8.78s | 1 | src-split-018 | - |
| SPLIT-019 | multi_event_segmentation | PASS | PASS | PASS | 8.09s | 1 | src-split-019 | - |
| SPLIT-020 | multi_event_segmentation | PASS | PASS | PASS | 12.42s | 2 | src-split-020 | - |
| ENTITY-001 | entity_resolution | PASS | PASS | PASS | 11.65s | 2 | src-entity-001 | - |
| ENTITY-002 | entity_resolution | PASS | PASS | PASS | 11.86s | 2 | src-entity-002 | - |
| ENTITY-003 | entity_resolution | PASS | PASS | PASS | 8.04s | 1 | src-entity-003 | - |
| ENTITY-004 | entity_resolution | PASS | PASS | PASS | 11.46s | 2 | src-entity-004 | - |
| ENTITY-005 | entity_resolution | PASS | PASS | PASS | 5.86s | 1 | src-entity-005 | - |
| ENTITY-006 | entity_resolution | PASS | PASS | PASS | 6.36s | 1 | src-entity-006 | - |
| ENTITY-007 | entity_resolution | PASS | PASS | PASS | 6.34s | 1 | src-entity-007 | - |
| ENTITY-008 | entity_resolution | PASS | PASS | PASS | 6.41s | 1 | src-entity-008 | - |
| ENTITY-009 | entity_resolution | PASS | PASS | PASS | 11.33s | 2 | src-entity-009 | - |
| ENTITY-010 | entity_resolution | PASS | PASS | PASS | 5.92s | 1 | src-entity-010 | - |
| ENTITY-011 | entity_resolution | PASS | PASS | PASS | 8.47s | 1 | src-entity-011 | - |
| ENTITY-012 | entity_resolution | PASS | PASS | PASS | 6.46s | 1 | src-entity-012 | - |
| ENTITY-013 | entity_resolution | PASS | PASS | PASS | 8.38s | 1 | src-entity-013 | - |
| ENTITY-014 | entity_resolution | PASS | PASS | PASS | 5.95s | 1 | src-entity-014 | - |
| ENTITY-015 | entity_resolution | PASS | PASS | PASS | 11.40s | 2 | src-entity-015 | - |
| ENTITY-016 | entity_resolution | PASS | PASS | PASS | 6.14s | 1 | src-entity-016 | - |
| ENTITY-017 | entity_resolution | PASS | PASS | PASS | 6.26s | 1 | src-entity-017 | - |
| ENTITY-018 | entity_resolution | PASS | PASS | PASS | 12.61s | 2 | src-entity-018 | - |
| ENTITY-019 | entity_resolution | PASS | PASS | PASS | 6.28s | 1 | src-entity-019 | - |
| ENTITY-020 | entity_resolution | PASS | PASS | PASS | 11.88s | 2 | src-entity-020 | - |
| TIME-001 | time_negation_uncertainty | PASS | PASS | PASS | 5.96s | 1 | src-time-001 | - |
| TIME-002 | time_negation_uncertainty | PASS | PASS | PASS | 5.98s | 1 | src-time-002 | - |
| TIME-003 | time_negation_uncertainty | PASS | PASS | PASS | 5.75s | 1 | src-time-003 | - |
| TIME-004 | time_negation_uncertainty | PASS | PASS | PASS | 11.72s | 2 | src-time-004 | - |
| TIME-005 | time_negation_uncertainty | PASS | PASS | PASS | 6.60s | 1 | src-time-005 | - |
| TIME-006 | time_negation_uncertainty | PASS | PASS | PASS | 5.87s | 1 | src-time-006 | - |
| TIME-007 | time_negation_uncertainty | PASS | PASS | PASS | 6.39s | 1 | src-time-007 | - |
| TIME-008 | time_negation_uncertainty | PASS | PASS | PASS | 6.25s | 1 | src-time-008 | - |
| TIME-009 | time_negation_uncertainty | PASS | PASS | PASS | 6.07s | 1 | src-time-009 | - |
| TIME-010 | time_negation_uncertainty | PASS | PASS | PASS | 5.87s | 1 | src-time-010 | - |
| TIME-011 | time_negation_uncertainty | PASS | PASS | PASS | 5.71s | 1 | src-time-011 | - |
| TIME-012 | time_negation_uncertainty | PASS | PASS | PASS | 6.11s | 1 | src-time-012 | - |
| TIME-013 | time_negation_uncertainty | PASS | PASS | PASS | 5.91s | 1 | src-time-013 | - |
| TIME-014 | time_negation_uncertainty | PASS | PASS | PASS | 5.89s | 1 | src-time-014 | - |
| TIME-015 | time_negation_uncertainty | PASS | PASS | PASS | 6.00s | 1 | src-time-015 | - |
| TIME-016 | time_negation_uncertainty | PASS | PASS | PASS | 5.95s | 1 | src-time-016 | - |
| TIME-017 | time_negation_uncertainty | PASS | PASS | PASS | 6.49s | 1 | src-time-017 | - |
| TIME-018 | time_negation_uncertainty | PASS | PASS | PASS | 5.89s | 1 | src-time-018 | - |
| TIME-019 | time_negation_uncertainty | PASS | PASS | PASS | 6.03s | 1 | src-time-019 | - |
| TIME-020 | time_negation_uncertainty | PASS | PASS | PASS | 5.92s | 1 | src-time-020 | - |
| REL-001 | relations_and_updates | PASS | PASS | PASS | 8.37s | 1 | src-rel-001 | - |
| REL-002 | relations_and_updates | PASS | PASS | PASS | 5.98s | 1 | src-rel-002 | - |
| REL-003 | relations_and_updates | PASS | PASS | PASS | 7.81s | 1 | src-rel-003 | - |
| REL-004 | relations_and_updates | PASS | PASS | PASS | 6.34s | 1 | src-rel-004 | - |
| REL-005 | relations_and_updates | PASS | PASS | PASS | 6.21s | 1 | src-rel-005 | - |
| REL-006 | relations_and_updates | PASS | PASS | PASS | 6.47s | 1 | src-rel-006 | - |
| REL-007 | relations_and_updates | PASS | PASS | PASS | 6.03s | 1 | src-rel-007 | - |
| REL-008 | relations_and_updates | PASS | PASS | PASS | 6.27s | 1 | src-rel-008 | - |
| REL-009 | relations_and_updates | PASS | PASS | PASS | 6.09s | 1 | src-rel-009 | - |
| REL-010 | relations_and_updates | PASS | PASS | PASS | 12.46s | 2 | src-rel-010 | - |
| REL-011 | relations_and_updates | PASS | PASS | PASS | 11.29s | 2 | src-rel-011 | - |
| REL-012 | relations_and_updates | PASS | PASS | PASS | 11.54s | 2 | src-rel-012 | - |
| REL-013 | relations_and_updates | PASS | PASS | PASS | 6.06s | 1 | src-rel-013 | - |
| REL-014 | relations_and_updates | PASS | PASS | PASS | 6.46s | 1 | src-rel-014 | - |
| REL-015 | relations_and_updates | PASS | PASS | PASS | 7.18s | 1 | src-rel-015 | - |
| REL-016 | relations_and_updates | PASS | PASS | PASS | 11.49s | 2 | src-rel-016 | - |
| REL-017 | relations_and_updates | PASS | PASS | PASS | 0.21s | 0 | src-rel-017 | - |
| REL-018 | relations_and_updates | PASS | PASS | PASS | 5.96s | 1 | src-rel-018 | - |
| REL-019 | relations_and_updates | PASS | PASS | PASS | 6.18s | 1 | src-rel-019 | - |
| REL-020 | relations_and_updates | PASS | PASS | PASS | 6.28s | 1 | src-rel-020 | - |
| NOISE-001 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.78s | 1 | src-noise-001 | - |
| NOISE-002 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.77s | 1 | src-noise-002 | - |
| NOISE-003 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.83s | 1 | src-noise-003 | - |
| NOISE-004 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.79s | 1 | src-noise-004 | - |
| NOISE-005 | noise_duplicates_ambiguity | PASS | PASS | PASS | 0.30s | 0 | src-noise-005 | - |
| NOISE-006 | noise_duplicates_ambiguity | PASS | PASS | PASS | 0.22s | 0 | src-noise-006 | - |
| NOISE-007 | noise_duplicates_ambiguity | PASS | PASS | PASS | 6.03s | 1 | src-noise-007 | - |
| NOISE-008 | noise_duplicates_ambiguity | PASS | PASS | PASS | 0.21s | 0 | src-noise-008 | - |
| NOISE-009 | noise_duplicates_ambiguity | PASS | PASS | PASS | 6.11s | 1 | src-noise-009 | - |
| NOISE-010 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.99s | 1 | src-noise-010 | - |
| NOISE-011 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.65s | 1 | src-noise-011 | - |
| NOISE-012 | noise_duplicates_ambiguity | PASS | PASS | PASS | 6.29s | 1 | src-noise-012 | - |
| NOISE-013 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.91s | 1 | src-noise-013 | - |
| NOISE-014 | noise_duplicates_ambiguity | PASS | PASS | PASS | 6.52s | 1 | src-noise-014 | - |
| NOISE-015 | noise_duplicates_ambiguity | PASS | PASS | PASS | 11.49s | 2 | src-noise-015 | - |
| NOISE-016 | noise_duplicates_ambiguity | PASS | PASS | PASS | 6.17s | 1 | src-noise-016 | - |
| NOISE-017 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.86s | 1 | src-noise-017 | - |
| NOISE-018 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.98s | 1 | src-noise-018 | - |
| NOISE-019 | noise_duplicates_ambiguity | PASS | PASS | PASS | 12.15s | 2 | src-noise-019 | - |
| NOISE-020 | noise_duplicates_ambiguity | PASS | PASS | PASS | 5.91s | 1 | src-noise-020 | - |
