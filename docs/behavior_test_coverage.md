# 추가 365개 변수의 실제 동작 검사

이 문서는 답변 예시만 연결되어 있던 365개 변수의 실행 가능한 동작 검사 목록입니다.
기존 질문·원문·정답은 보존하고, 정상·경계 동작을 검사하는 별도 사례를 카탈로그에 추가했습니다.

## 검사와 판정

- 실제 SQLite 저장소, 실제 HTTP 인증·CSRF·오류 처리, 실제 검색/대화 코드와 브라우저 화면을 검사합니다.
- 기능 검사에서 생성·임베딩 모델은 대체 구현입니다. 해당 결과는 모델 정확도·후보 순위의 표본으로 세지 않습니다.
- 같은 동작을 여러 변수가 공유하면 해당 검사의 정상·경계 파라미터를 공유하며, 서로 다른 모델 표본으로 중복 계산하지 않습니다.
- 각 변수에는 명시한 검사 함수/파라미터만 연결합니다. 범주 이름만으로 관련 없는 검사에 자동 연결하는 기본값은 없습니다.
- 검사 누락, 실패, 건너뜀은 통과가 아닙니다. 임의 테스트 경로를 외부 입력으로 실행할 수 없습니다.
- 기능 검사 하위 프로세스는 합성 DB 경로만 허용하고 Python의 실제 네트워크 연결과 모델 HTTP 호출을 차단합니다.
- 100~100000건 데이터와 동시 작업 검사는 확장 프로필에 둡니다. 핵심/최종 후보 검증에 대량 부하를 자동 추가하지 않습니다.
- 기능 검사의 고정 공개 합성 예제는 모델의 70:30 개발/최종 검증 데이터 및 모델 반복 측정과 구분합니다.

## 지원 범위 밖인 항목

지원 밖 기능을 구현된 것으로 표시하지 않습니다. 아래 항목은 실제 API/스키마/가져오기 거절을 검사한 뒤 공식 실행 결과를 UNSUPPORTED로 남깁니다. 미지원 판정은 제품 범위를 명시한 음성·파일 형식·공유/계정/동기화·미지원 필터/검색 페이지 기능에 한정합니다.

| 변수 | 기능 |
|---|---|
| IN-08 | PDF 업로드 · 텍스트 추출 및 페이지 위치 |
| IN-10 | DOCX/문서 업로드 · 제목, 표, 문단 구조 |
| IN-11 | CSV/JSON 업로드 · 구조화 필드 |
| IN-12 | 이미지 또는 스크린샷 입력 · OCR·시각 정보 추출 가능 여부 |
| IN-13 | 음성 입력·전사 텍스트 · 음성 인식 오류 |
| LC-18 | 긴 PDF 저장 → 특정 단락 질문 · 해당 단락과 페이지 인용 |
| IN-14 | 여러 파일 동시 입력 · 파일별 출처 유지 |
| IN-15 | 외부 서비스에서 가져오기 · 출처·권한·동기화 |
| ST-11 | 제목 수정 · 본문·색인 일관성 |
| ST-12 | 태그 추가·제거 · 필터 반영 |
| ST-19 | 공유 기록 접근권 변경 · 검색 권한 즉시 반영 |
| SEC-03 | 검색 전 권한 필터 · 비허용 자료 검색 결과 제외 |
| SEC-07 | 공유 기록 접근권 변경 · 변경 사항 적용 |
| SEC-17 | 데이터 내보내기 · 본인에게 허용된 기록만 포함 |
| SEC-18 | 사용자 세션 만료 · 권한 없이 검색 지속 금지 |
| RT-09 | 수정일 기준 · 마지막 수정 날짜 |
| RT-15 | 특정 파일 · PDF 한 개만 검색 |
| RT-16 | 특정 출처 · 직접 입력한 메모만 |
| RT-17 | 특정 기록 유형 · 일정·회의·오류·결정 |
| RT-20 | 중요도 · 중요한 기록 우선 |
| RT-24 | 여러 필터의 OR · 프로젝트 A 또는 B |
| RT-29 | 페이징 · 다음 결과 불러오기 |
| RT-31 | 접근 가능한 기록만 · 권한 필터 |
| UI-22 | 검색 결과가 매우 많음 · 페이징·가상 스크롤 |

내부 owner 세션 검사와 단일 로컬 계정의 인증 검사는 실제 다중 사용자 로그인·공유 ACL 지원을 의미하지 않습니다.

## HTTP 응답 대기 수정

기존 7개 검사는 요청이 앱에 도착하기 전에 Windows Python의 비동기 이벤트 루프가 내부 TCP socketpair를 만들며 멈췄습니다.
`tests/http_client.py`는 테스트 전용 루프에 짧은 타이머 깨우기를 사용합니다. 실제 ASGI 전송·앱 수명·미들웨어·인증·CSRF·요청 본문·응답 처리는 그대로 검사합니다.
제품 서버의 루프, 일반 모델 서버, 운영 네트워크 설정은 변경하지 않았습니다. 대기를 피하기 위해 검사를 삭제하거나 HTTP 핸들러를 가짜 응답으로 교체하지 않았습니다.

## 변수별 기대 동작과 실제 검사

| 변수 | 검증할 동작 | 실행 검사 |
|---|---|---|
| IN-01 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[natural]` |
| IN-02 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[keywords]` |
| IN-03 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[diary]` |
| IN-04 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[multiline]` |
| IN-45 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[multiple-events]` |
| IN-61 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[identifiers]` |
| IN-73 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[unicode]` |
| IN-74 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[identifiers]` |
| IN-75 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[identifiers]` |
| IN-76 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[identifiers]` |
| IN-77 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[code]` |
| IN-78 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[table]` |
| IN-79 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[multiline]` |
| IN-80 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[transcript]` |
| IN-81 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[transcript]` |
| IN-82 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[guess]` |
| IN-83 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[possible]` |
| IN-84 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[question]` |
| IN-85 | 입력별 원문·줄바꿈·식별자·불확실성을 보존하고 서로 다른 사건의 근거 위치를 섞지 않는다. | `tests/test_behavior_operations.py::test_input_roundtrip_and_source_boundaries[rumor]` |
| IN-05 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| IN-06 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| IN-17 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| EX-24 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| QI-24 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-01 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-02 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-03 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-04 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-16 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-23 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| MW-24 | 승인 전에는 기록이 생성되지 않고 비저장/비활성 정책을 지키며 승인 후 재시작에도 유지한다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_modes_reference_and_provenance` |
| IN-07 | 중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| IN-16 | 중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| ST-02 | 중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| ST-03 | 중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| LC-19 | 중복 후보는 비교하되 다른 사실을 자동 합치지 않고 출처와 정정 이력을 보존한다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| IN-08 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[pdf]` |
| IN-10 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[docx]` |
| IN-11 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[csv]`<br>`tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[json]` |
| IN-12 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[png]` |
| IN-13 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[wav]` |
| LC-18 | 지원하지 않는 PDF/DOCX/CSV/JSON/이미지/오디오를 실제 가져오기 경로가 거절하고 파일·페이지 추출 성공을 표시하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_file_formats_are_rejected_without_records[pdf]` |
| IN-14 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[files]` |
| IN-15 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[sync_url]` |
| ST-11 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[title]` |
| ST-12 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[tags]` |
| ST-19 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[acl]` |
| SEC-03 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[owner_id]` |
| SEC-07 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[acl]` |
| SEC-17 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[owner_id]` |
| SEC-18 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. / 인증한 실제 HTTP 요청으로 다중 파일·외부 동기화·공유 ACL·계정 삭제 경로가 지원 밖임을 확인한다. | `tests/test_behavior_operations.py::test_unsupported_capability_routes_are_absent`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[owner_id]` |
| RT-09 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[date_modified]` |
| RT-15 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[source_file]` |
| RT-16 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[source_type]` |
| RT-17 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[record_type]` |
| RT-20 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[importance]` |
| RT-24 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[or]` |
| RT-29 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[offset]` |
| RT-31 | 공유 ACL·태그·제목·외부 동기화·다중 파일·미지원 필터 요청을 실제 API/입력 스키마로 거절하며 지원으로 오인하지 않는다. | `tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[owner_id]` |
| IN-18 | 같은 저장 요청의 재전송이 원문·작업을 중복 생성하지 않는다. | `tests/test_memory_complete.py::test_natural_capture_response_retry_is_idempotent` |
| ST-25 | 같은 저장 요청의 재전송이 원문·작업을 중복 생성하지 않는다. | `tests/test_memory_complete.py::test_natural_capture_response_retry_is_idempotent` |
| PF-22 | 같은 저장 요청의 재전송이 원문·작업을 중복 생성하지 않는다. | `tests/test_memory_complete.py::test_natural_capture_response_retry_is_idempotent` |
| LC-30 | 같은 저장 요청의 재전송이 원문·작업을 중복 생성하지 않는다. | `tests/test_memory_complete.py::test_natural_capture_response_retry_is_idempotent` |
| IN-19 | 동시 쓰기의 한 요청만 성공하며 오래된 버전은 충돌로 거절하고 최신 문맥을 덮어쓰지 않는다. | `tests/chat/test_integration.py::test_concurrent_version_updates_and_message_begin`<br>`tests/chat/test_integration.py::test_generation_cannot_overwrite_concurrent_context_update` |
| ST-18 | 동시 쓰기의 한 요청만 성공하며 오래된 버전은 충돌로 거절하고 최신 문맥을 덮어쓰지 않는다. | `tests/chat/test_integration.py::test_concurrent_version_updates_and_message_begin`<br>`tests/chat/test_integration.py::test_generation_cannot_overwrite_concurrent_context_update` |
| IN-20 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| ST-01 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| ST-04 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| ST-05 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| ST-06 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| ST-10 | 신규 ID, 추가 정보, 두 번의 정정, 원문 이력과 파생 기억/벡터 무효화를 실제 저장소에서 확인한다. | `tests/test_behavior_operations.py::test_record_versions_preserve_original_and_invalidate_derived` |
| IN-44 | 민감 정보는 명시한 주제에만 사용하며 기록 사용 거부가 모든 검색 경로보다 우선한다. | `tests/test_conversation_policy.py::test_memory_refusal_precedes_all_routes`<br>`tests/test_conversation_policy.py::test_sensitive_sources_require_relevant_explicit_topic` |
| SEC-10 | 민감 정보는 명시한 주제에만 사용하며 기록 사용 거부가 모든 검색 경로보다 우선한다. | `tests/test_conversation_policy.py::test_memory_refusal_precedes_all_routes`<br>`tests/test_conversation_policy.py::test_sensitive_sources_require_relevant_explicit_topic` |
| SEC-11 | 민감 정보는 명시한 주제에만 사용하며 기록 사용 거부가 모든 검색 경로보다 우선한다. | `tests/test_conversation_policy.py::test_memory_refusal_precedes_all_routes`<br>`tests/test_conversation_policy.py::test_sensitive_sources_require_relevant_explicit_topic` |
| MW-13 | 민감 정보는 명시한 주제에만 사용하며 기록 사용 거부가 모든 검색 경로보다 우선한다. | `tests/test_conversation_policy.py::test_memory_refusal_precedes_all_routes`<br>`tests/test_conversation_policy.py::test_sensitive_sources_require_relevant_explicit_topic` |
| IN-62 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| IN-63 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| IN-64 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| IN-65 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| QU-17 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| QU-33 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| CV-13 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| CV-14 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| CV-15 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| CV-16 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| AG-07 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| AG-08 | 명확한 단일 근거는 바로 답하고 실제 복수 해석만 원문 대상 ID와 함께 되묻는다. | `tests/test_conversation_uxr.py::test_UXR01_clear_answer_has_no_choice`<br>`tests/test_conversation_uxr.py::test_UXR02_actual_ambiguity_uses_source_target_ids` |
| IN-66 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| IN-67 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| IN-68 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| IN-69 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| ST-07 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| ST-23 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| QI-11 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| QI-12 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| QI-16 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| RR-06 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| RR-07 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| EV-09 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| EV-11 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| AG-12 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| MW-07 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| MW-11 | 같은 시점·프로젝트의 충돌만 비교하며 계획·조건·다른 날짜를 현재 사실로 합치지 않는다. | `tests/test_conversation_policy.py::test_explicit_conflict_guard_preserves_dates_projects_and_conditions` |
| EX-06 | 저장/사건/수정 시각을 구분하며 질문이 요구한 종류의 시각만 답변 근거로 사용한다. / 수정 전 원문과 저장일·수정일·실제 사건일이 서로 다른 실제 DB의 값을 대조한다. | `tests/test_behavior_operations.py::test_created_modified_and_event_times_are_distinct`<br>`tests/test_chat_grounding.py::test_generation_time_metadata_is_scoped_to_question` |
| EX-07 | 저장/사건/수정 시각을 구분하며 질문이 요구한 종류의 시각만 답변 근거로 사용한다. / 수정 전 원문과 저장일·수정일·실제 사건일이 서로 다른 실제 DB의 값을 대조한다. | `tests/test_behavior_operations.py::test_created_modified_and_event_times_are_distinct`<br>`tests/test_chat_grounding.py::test_generation_time_metadata_is_scoped_to_question` |
| RT-07 | 저장/사건/수정 시각을 구분하며 질문이 요구한 종류의 시각만 답변 근거로 사용한다. / 수정 전 원문과 저장일·수정일·실제 사건일이 서로 다른 실제 DB의 값을 대조한다. | `tests/test_behavior_operations.py::test_created_modified_and_event_times_are_distinct`<br>`tests/test_chat_grounding.py::test_generation_time_metadata_is_scoped_to_question` |
| RT-08 | 저장/사건/수정 시각을 구분하며 질문이 요구한 종류의 시각만 답변 근거로 사용한다. / 수정 전 원문과 저장일·수정일·실제 사건일이 서로 다른 실제 DB의 값을 대조한다. | `tests/test_behavior_operations.py::test_created_modified_and_event_times_are_distinct`<br>`tests/test_chat_grounding.py::test_generation_time_metadata_is_scoped_to_question` |
| EX-17 | 정정은 기존 원문에 새 버전을 만들며 오래된 승인/색인과 삭제된 기억이 재사용되지 않는다. | `tests/test_memory_capture.py::test_existing_record_correction_and_stale_version`<br>`tests/test_memory_capture.py::test_index_publication_correction_and_delete` |
| MW-10 | 정정은 기존 원문에 새 버전을 만들며 오래된 승인/색인과 삭제된 기억이 재사용되지 않는다. | `tests/test_memory_capture.py::test_existing_record_correction_and_stale_version`<br>`tests/test_memory_capture.py::test_index_publication_correction_and_delete` |
| EX-21 | 직접 원문·파일 청크·대화 메시지의 출처를 보존하고 위치가 원문과 일치하며 원본 삭제를 반영한다. | `tests/test_conversation_policy.py::test_upload_atomic_idempotent_offsets_and_lifecycle` |
| EX-22 | 직접 원문·파일 청크·대화 메시지의 출처를 보존하고 위치가 원문과 일치하며 원본 삭제를 반영한다. | `tests/test_conversation_policy.py::test_upload_atomic_idempotent_offsets_and_lifecycle` |
| EX-23 | 내부 owner와 실제 인증/CSRF 경계를 구분하고 타 owner의 조회·수정·삭제·요청 상태를 차단한다. | `tests/chat/test_integration.py::test_api_security_pagination_and_alias`<br>`tests/chat/test_integration.py::test_owner_isolation_covers_all_access` |
| SEC-02 | 내부 owner와 실제 인증/CSRF 경계를 구분하고 타 owner의 조회·수정·삭제·요청 상태를 차단한다. | `tests/chat/test_integration.py::test_api_security_pagination_and_alias`<br>`tests/chat/test_integration.py::test_owner_isolation_covers_all_access` |
| SEC-06 | 내부 owner와 실제 인증/CSRF 경계를 구분하고 타 owner의 조회·수정·삭제·요청 상태를 차단한다. | `tests/chat/test_integration.py::test_api_security_pagination_and_alias`<br>`tests/chat/test_integration.py::test_owner_isolation_covers_all_access` |
| LC-10 | 내부 owner와 실제 인증/CSRF 경계를 구분하고 타 owner의 조회·수정·삭제·요청 상태를 차단한다. | `tests/chat/test_integration.py::test_api_security_pagination_and_alias`<br>`tests/chat/test_integration.py::test_owner_isolation_covers_all_access` |
| ST-08 | 명시한 역할의 동명이인만 사용하며 다른 사람의 직업/사건을 인용하지 않는다. | `tests/test_identity_semantics.py::test_current_explicit_role_wins`<br>`tests/test_identity_semantics.py::test_other_person_cannot_supply_profession_even_if_model_approves` |
| RR-23 | 명시한 역할의 동명이인만 사용하며 다른 사람의 직업/사건을 인용하지 않는다. | `tests/test_identity_semantics.py::test_current_explicit_role_wins`<br>`tests/test_identity_semantics.py::test_other_person_cannot_supply_profession_even_if_model_approves` |
| CV-23 | 명시한 역할의 동명이인만 사용하며 다른 사람의 직업/사건을 인용하지 않는다. | `tests/test_identity_semantics.py::test_current_explicit_role_wins`<br>`tests/test_identity_semantics.py::test_other_person_cannot_supply_profession_even_if_model_approves` |
| ST-09 | 프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다. | `tests/test_evaluation_remediation.py::test_optional_background_is_not_a_required_citation`<br>`tests/test_evaluation_remediation.py::test_scope_namesake_and_preference_are_not_merged` |
| RR-16 | 프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다. | `tests/test_evaluation_remediation.py::test_optional_background_is_not_a_required_citation`<br>`tests/test_evaluation_remediation.py::test_scope_namesake_and_preference_are_not_merged` |
| RR-24 | 프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다. | `tests/test_evaluation_remediation.py::test_optional_background_is_not_a_required_citation`<br>`tests/test_evaluation_remediation.py::test_scope_namesake_and_preference_are_not_merged` |
| EV-05 | 프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다. | `tests/test_evaluation_remediation.py::test_optional_background_is_not_a_required_citation`<br>`tests/test_evaluation_remediation.py::test_scope_namesake_and_preference_are_not_merged` |
| AG-13 | 프로젝트와 인물 범위를 보존하고 배경 프로젝트의 원문을 필수 인용으로 강제하지 않는다. | `tests/test_evaluation_remediation.py::test_optional_background_is_not_a_required_citation`<br>`tests/test_evaluation_remediation.py::test_scope_namesake_and_preference_are_not_merged` |
| ST-13 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| ST-14 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| ST-20 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| ST-21 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| SEC-04 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| SEC-05 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| SEC-13 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| MW-12 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| QI-25 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| AG-25 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| CV-21 | 여러 원문과 세션 원문 삭제 시 파생 기억·벡터·저장 검색/대화 근거가 함께 무효화된다. | `tests/test_behavior_operations.py::test_deletion_removes_sources_indexes_and_cached_answers` |
| ST-16 | 작업 생성 실패 시 저장 트랜잭션 전체를 롤백한다. | `tests/test_memory_capture.py::test_atomic_commit_rolls_back_job_failure` |
| ST-17 | 색인 실패와 대기를 검색 결과 없음과 구분하고 재시도 후 최신 버전만 게시한다. | `tests/test_memory_capture.py::test_failed_index_retry_and_pending_rejection` |
| RR-36 | 색인 실패와 대기를 검색 결과 없음과 구분하고 재시도 후 최신 버전만 게시한다. | `tests/test_memory_capture.py::test_failed_index_retry_and_pending_rejection` |
| PF-12 | 색인 실패와 대기를 검색 결과 없음과 구분하고 재시도 후 최신 버전만 게시한다. | `tests/test_memory_capture.py::test_failed_index_retry_and_pending_rejection` |
| ST-22 | 긴 문서를 청크로 나누어 한 번만 저장하고 재전송/취소/삭제의 원문 위치를 보존한다. | `tests/test_conversation_policy.py::test_upload_atomic_idempotent_offsets_and_lifecycle` |
| ST-24 | 저장 직후 queued 상태, 실패, ready_empty 상태와 검색 가능한 상태를 실제 API에서 구분한다. | `tests/test_behavior_operations.py::test_indexing_pending_is_distinct_from_empty_corpus` |
| QI-10 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| QI-13 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| AG-17 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| AG-21 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| EV-23 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| EV-25 | 서로 다른 사건·날짜·완료/미완료와 반례를 포함한 복수 근거를 요약 계획/정렬에서 누락하지 않는다. | `tests/test_behavior_operations.py::test_summary_keeps_all_facts_and_event_order` |
| QI-17 | 처음/최신 순서는 저장 시각이 아니라 사건 시각으로 선택한다. | `tests/test_search_explain.py::test_current_state_keeps_event_date_order_across_queries` |
| QI-18 | 승인한 선호와 규칙만 실제 메시지 출처에서 저장하고 변경된 선호를 다시 읽는다. | `tests/test_memory_capture.py::test_decision_capture_uses_actual_turns_and_preferences_update` |
| MW-08 | 승인한 선호와 규칙만 실제 메시지 출처에서 저장하고 변경된 선호를 다시 읽는다. | `tests/test_memory_capture.py::test_decision_capture_uses_actual_turns_and_preferences_update` |
| MW-09 | 승인한 선호와 규칙만 실제 메시지 출처에서 저장하고 변경된 선호를 다시 읽는다. | `tests/test_memory_capture.py::test_decision_capture_uses_actual_turns_and_preferences_update` |
| QI-19 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| QU-06 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| QU-18 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| QU-19 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| CV-02 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| CV-03 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| CV-08 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| CV-18 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| CV-19 | 직전 사용자 발화와 검증한 원문으로 후속 대상을 연결하고 AI 문장만으로 지시어를 지어내지 않는다. | `tests/test_identity_semantics.py::test_ambiguous_or_unverified_reference_is_not_invented`<br>`tests/test_identity_semantics.py::test_followup_uses_source_backed_immediate_user_role` |
| QI-20 | 일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다. | `tests/test_conversation_policy.py::test_general_turn_never_reads_preferences_or_searches`<br>`tests/test_conversation_policy.py::test_short_social_reply_is_not_empty_when_model_echoes` |
| QI-23 | 일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다. | `tests/test_conversation_policy.py::test_general_turn_never_reads_preferences_or_searches`<br>`tests/test_conversation_policy.py::test_short_social_reply_is_not_empty_when_model_echoes` |
| AG-01 | 일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다. | `tests/test_conversation_policy.py::test_general_turn_never_reads_preferences_or_searches`<br>`tests/test_conversation_policy.py::test_short_social_reply_is_not_empty_when_model_echoes` |
| AG-02 | 일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다. | `tests/test_conversation_policy.py::test_general_turn_never_reads_preferences_or_searches`<br>`tests/test_conversation_policy.py::test_short_social_reply_is_not_empty_when_model_echoes` |
| CV-25 | 일반 상식/인사/감정 발화는 검색·저장된 선호 읽기 없이 답한다. | `tests/test_conversation_policy.py::test_general_turn_never_reads_preferences_or_searches`<br>`tests/test_conversation_policy.py::test_short_social_reply_is_not_empty_when_model_echoes` |
| QI-21 | 개인 근거와 일반 제안을 서로 다른 출처 종류로 표시한다. | `tests/test_conversation_uxr.py::test_UXR19_mixed_sources_are_separate` |
| AG-04 | 개인 근거와 일반 제안을 서로 다른 출처 종류로 표시한다. | `tests/test_conversation_uxr.py::test_UXR19_mixed_sources_are_separate` |
| QI-22 | 명시적 검색은 검색 응답을 반환하고 일반 대화와 모드/검색 실행 수가 구분된다. | `tests/test_behavior_operations.py::test_explicit_search_and_conversation_have_distinct_routes` |
| AG-05 | 명시적 검색은 검색 응답을 반환하고 일반 대화와 모드/검색 실행 수가 구분된다. | `tests/test_behavior_operations.py::test_explicit_search_and_conversation_have_distinct_routes` |
| QU-01 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-02 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-03 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-04 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-05 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-29 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| RR-01 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| RR-02 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| RT-21 | 정확한 키워드·제목·짧은 단어·부분 문장으로 원문 위치를 보존하며 유사 문자열을 혼동하지 않는다. | `tests/test_search_explain.py::test_exact_matches_outweigh_normalized_and_summary_is_separate`<br>`tests/test_search_explain.py::test_keyword_matching_uses_whole_tokens_and_retains_short_keywords` |
| QU-07 | 복합 질문의 각 조건을 원문 그대로 분해하고 질문별 독립 검색과 후속 근거 확인을 수행한다. | `tests/test_compound_execution.py::test_compound_parts_are_literal_independent_questions`<br>`tests/test_compound_execution.py::test_literal_facets_keep_separate_retrieval_conditions_and_next_search_review` |
| QU-21 | 복합 질문의 각 조건을 원문 그대로 분해하고 질문별 독립 검색과 후속 근거 확인을 수행한다. | `tests/test_compound_execution.py::test_compound_parts_are_literal_independent_questions`<br>`tests/test_compound_execution.py::test_literal_facets_keep_separate_retrieval_conditions_and_next_search_review` |
| RR-22 | 복합 질문의 각 조건을 원문 그대로 분해하고 질문별 독립 검색과 후속 근거 확인을 수행한다. | `tests/test_compound_execution.py::test_compound_parts_are_literal_independent_questions`<br>`tests/test_compound_execution.py::test_literal_facets_keep_separate_retrieval_conditions_and_next_search_review` |
| AG-16 | 복합 질문의 각 조건을 원문 그대로 분해하고 질문별 독립 검색과 후속 근거 확인을 수행한다. | `tests/test_compound_execution.py::test_compound_parts_are_literal_independent_questions`<br>`tests/test_compound_execution.py::test_literal_facets_keep_separate_retrieval_conditions_and_next_search_review` |
| QU-08 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-09 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-10 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-13 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-14 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-23 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| RR-18 | 한영 별칭·약어·발음·유사어는 승인한 사전과 문맥만 사용하고 중복 점수/조건 변경을 방지한다. | `tests/test_search_expressions.py::test_aliases_are_symmetric_and_duplicate_terms_do_not_add_scores`<br>`tests/test_search_expressions.py::test_expansion_runs_in_one_batch_and_keeps_original_conditions_and_selection` |
| QU-11 | 오타와 띄어쓰기만 검증한 범위에서 교정하며 식별자·부정·수치를 변경하지 않는다. | `tests/test_query_correction.py::test_bounded_spelling_and_unicode_offsets`<br>`tests/test_query_correction.py::test_protected_or_unverified_expressions`<br>`tests/test_query_correction.py::test_spacing_and_invalid_spans` |
| QU-12 | 오타와 띄어쓰기만 검증한 범위에서 교정하며 식별자·부정·수치를 변경하지 않는다. | `tests/test_query_correction.py::test_bounded_spelling_and_unicode_offsets`<br>`tests/test_query_correction.py::test_protected_or_unverified_expressions`<br>`tests/test_query_correction.py::test_spacing_and_invalid_spans` |
| QU-15 | 모호한 동음이의어·주제 밖 확장·부정확한 번역은 실제 원문 문맥 확인 없이 사용하지 않는다. | `tests/test_search_expressions.py::test_ambiguous_translation_agrees_with_specific_context`<br>`tests/test_search_expressions.py::test_expansion_rejects_constraints_and_ambiguous_or_invalid_edits` |
| QU-16 | 모호한 동음이의어·주제 밖 확장·부정확한 번역은 실제 원문 문맥 확인 없이 사용하지 않는다. | `tests/test_search_expressions.py::test_ambiguous_translation_agrees_with_specific_context`<br>`tests/test_search_expressions.py::test_expansion_rejects_constraints_and_ambiguous_or_invalid_edits` |
| QU-39 | 모호한 동음이의어·주제 밖 확장·부정확한 번역은 실제 원문 문맥 확인 없이 사용하지 않는다. | `tests/test_search_expressions.py::test_ambiguous_translation_agrees_with_specific_context`<br>`tests/test_search_expressions.py::test_expansion_rejects_constraints_and_ambiguous_or_invalid_edits` |
| QU-20 | 계획·부정·실행 미확인을 실제 완료로 바꾸지 않는다. | `tests/test_compound_execution.py::test_model_approval_cannot_make_plan_only_answer_fulfill_execution_question`<br>`tests/test_compound_execution.py::test_plan_draft_preserves_future_plan_and_limits_execution_claim` |
| RR-33 | 계획·부정·실행 미확인을 실제 완료로 바꾸지 않는다. | `tests/test_compound_execution.py::test_model_approval_cannot_make_plan_only_answer_fulfill_execution_question`<br>`tests/test_compound_execution.py::test_plan_draft_preserves_future_plan_and_limits_execution_claim` |
| EV-07 | 계획·부정·실행 미확인을 실제 완료로 바꾸지 않는다. | `tests/test_compound_execution.py::test_model_approval_cannot_make_plan_only_answer_fulfill_execution_question`<br>`tests/test_compound_execution.py::test_plan_draft_preserves_future_plan_and_limits_execution_claim` |
| QU-22 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-02 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-03 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-04 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-05 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-06 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-23 | 상대/절대 날짜·범위·프로젝트 조건과 제외 대상을 동시에 보존하고 범위 밖 근거를 제외한다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| QU-31 | 독립 사실과 인과 연결을 구분하고 원문에 없는 원인·결과 관계를 요구하거나 만들지 않는다. | `tests/test_compound_execution.py::test_causal_check_does_not_require_a_cause_for_independent_profession_fact`<br>`tests/test_compound_execution.py::test_dependent_or_single_question_is_not_split` |
| QU-32 | 독립 사실과 인과 연결을 구분하고 원문에 없는 원인·결과 관계를 요구하거나 만들지 않는다. | `tests/test_compound_execution.py::test_causal_check_does_not_require_a_cause_for_independent_profession_fact`<br>`tests/test_compound_execution.py::test_dependent_or_single_question_is_not_split` |
| RR-32 | 독립 사실과 인과 연결을 구분하고 원문에 없는 원인·결과 관계를 요구하거나 만들지 않는다. | `tests/test_compound_execution.py::test_causal_check_does_not_require_a_cause_for_independent_profession_fact`<br>`tests/test_compound_execution.py::test_dependent_or_single_question_is_not_split` |
| QU-34 | 과거 발언 안의 검색·저장 명령을 현재의 실행 요청으로 수행하지 않는다. | `tests/test_behavior_operations.py::test_quoted_commands_are_data_not_actions` |
| QU-38 | 정규식 기호·따옴표·경로·전각 표기의 원문 범위를 보존한다. | `tests/test_search_expressions.py::test_distinct_identifiers_do_not_match`<br>`tests/test_search_expressions.py::test_symbol_and_fullwidth_spans` |
| QU-40 | 서로 모순되는 날짜 조건은 입력 오류로 거절하며 검색/모델 호출을 하지 않는다. | `tests/test_behavior_operations.py::test_conflicting_filter_bounds_are_rejected_without_search` |
| RT-01 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-12 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-13 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-14 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-18 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-19 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-25 | 전체/프로젝트/인물/완료/부정 조건은 다른 대상의 유사 기록과 섞이지 않는다. | `tests/test_behavior_operations.py::test_temporal_and_compound_filters_preserve_constraints` |
| RT-10 | 여러 검색어에서 최신/최초 사건 순서를 전역으로 보존한다. | `tests/test_search_explain.py::test_current_state_keeps_event_date_order_across_queries` |
| RT-11 | 여러 검색어에서 최신/최초 사건 순서를 전역으로 보존한다. | `tests/test_search_explain.py::test_current_state_keeps_event_date_order_across_queries` |
| RT-22 | 실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다. | `tests/test_search_explain.py::test_direct_and_counter_evidence_outrank_background`<br>`tests/test_search_explain.py::test_service_propagates_model_assessment` |
| RR-03 | 실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다. | `tests/test_search_explain.py::test_direct_and_counter_evidence_outrank_background`<br>`tests/test_search_explain.py::test_service_propagates_model_assessment` |
| RR-04 | 실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다. | `tests/test_search_explain.py::test_direct_and_counter_evidence_outrank_background`<br>`tests/test_search_explain.py::test_service_propagates_model_assessment` |
| RR-05 | 실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다. | `tests/test_search_explain.py::test_direct_and_counter_evidence_outrank_background`<br>`tests/test_search_explain.py::test_service_propagates_model_assessment` |
| RR-31 | 실제 검색 코어에서 어휘/벡터 후보를 결합하고 원문으로 확인한 직접·반박 근거를 배경보다 우선한다. | `tests/test_search_explain.py::test_direct_and_counter_evidence_outrank_background`<br>`tests/test_search_explain.py::test_service_propagates_model_assessment` |
| RT-26 | 없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다. | `tests/test_conversation_uxr.py::test_UXR07_partial_answer_keeps_uncertainty`<br>`tests/test_conversation_uxr.py::test_UXR08_empty_search_has_retry_and_no_fake_facts` |
| RT-27 | 없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다. | `tests/test_conversation_uxr.py::test_UXR07_partial_answer_keeps_uncertainty`<br>`tests/test_conversation_uxr.py::test_UXR08_empty_search_has_retry_and_no_fake_facts` |
| RR-25 | 없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다. | `tests/test_conversation_uxr.py::test_UXR07_partial_answer_keeps_uncertainty`<br>`tests/test_conversation_uxr.py::test_UXR08_empty_search_has_retry_and_no_fake_facts` |
| RR-30 | 없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다. | `tests/test_conversation_uxr.py::test_UXR07_partial_answer_keeps_uncertainty`<br>`tests/test_conversation_uxr.py::test_UXR08_empty_search_has_retry_and_no_fake_facts` |
| AG-10 | 없는 결과를 오류와 구분하고 근거 없는 사실 대신 범위 조정/재시도를 제안한다. | `tests/test_conversation_uxr.py::test_UXR07_partial_answer_keeps_uncertainty`<br>`tests/test_conversation_uxr.py::test_UXR08_empty_search_has_retry_and_no_fake_facts` |
| RT-28 | 원래 상위 근거를 검토 풀에서 잃지 않고 최종 Top-K를 전역 적용한다. | `tests/test_search_accuracy.py::test_original_top_eight_remain_in_24_candidate_review_pool` |
| RR-26 | 원래 상위 근거를 검토 풀에서 잃지 않고 최종 Top-K를 전역 적용한다. | `tests/test_search_accuracy.py::test_original_top_eight_remain_in_24_candidate_review_pool` |
| RT-30 | 동일 사실의 여러 출처를 보존하되 독립적인 확증으로 중복 계산하지 않는다. | `tests/test_conversation_uxr.py::test_UXR04_same_fact_keeps_all_provenance_without_counting_independent_confirmation` |
| RR-28 | 동일 사실의 여러 출처를 보존하되 독립적인 확증으로 중복 계산하지 않는다. | `tests/test_conversation_uxr.py::test_UXR04_same_fact_keeps_all_provenance_without_counting_independent_confirmation` |
| EV-26 | 동일 사실의 여러 출처를 보존하되 독립적인 확증으로 중복 계산하지 않는다. | `tests/test_conversation_uxr.py::test_UXR04_same_fact_keeps_all_provenance_without_counting_independent_confirmation` |
| RT-32 | 현재 대화는 장기 원문으로 자동 저장하지 않으면서 요약·페이지·재시작 문맥을 보존한다. | `tests/chat/test_integration.py::test_store_idempotency_context_restart_and_pagination` |
| AG-26 | 현재 대화는 장기 원문으로 자동 저장하지 않으면서 요약·페이지·재시작 문맥을 보존한다. | `tests/chat/test_integration.py::test_store_idempotency_context_restart_and_pagination` |
| RR-08 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| EV-20 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| EV-22 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| EV-28 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| MW-15 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| MW-21 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| AG-34 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| AG-35 | 사용자 주장·AI 제안·추론의 사실 상태와 출처를 보존하며 사용자 확정 사실로 승격하지 않는다. | `tests/test_memory_capture.py::test_ai_extraction_cannot_become_personal_fact`<br>`tests/test_memory_capture.py::test_expiry_version_and_ai_type` |
| RR-09 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-10 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-11 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-12 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-13 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-14 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-15 | 긴 문서/짧은 문서의 분할·문장·청크·원문 연결과 필터의 원문 범위를 실제 파이프라인에서 확인한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| RR-17 | 질문 재작성 뒤에도 원래 날짜·부정·식별자 조건과 검색 출처를 보존한다. | `tests/test_query_correction.py::test_constraint_changing_edit_is_rejected`<br>`tests/test_query_correction.py::test_search_batch_provenance_and_same_filter_scope` |
| RR-19 | 확장을 한 번에 결합하고 중복 기여를 제한하며 확장 실패 시 원래 검색을 유지한다. | `tests/test_search_expressions.py::test_expansion_embedding_failure_and_empty_candidates_keep_original`<br>`tests/test_search_expressions.py::test_expansion_limits_weights_duplicates_and_context` |
| RR-20 | 확장을 한 번에 결합하고 중복 기여를 제한하며 확장 실패 시 원래 검색을 유지한다. | `tests/test_search_expressions.py::test_expansion_embedding_failure_and_empty_candidates_keep_original`<br>`tests/test_search_expressions.py::test_expansion_limits_weights_duplicates_and_context` |
| RR-21 | 여러 검색 결과를 합치기 전에 일찍 자르지 않고 늦게 찾은 강한 근거도 포함한다. | `tests/test_search_explain.py::test_chat_defers_eight_record_limit_until_all_queries_are_combined` |
| AG-11 | 여러 검색 결과를 합치기 전에 일찍 자르지 않고 늦게 찾은 강한 근거도 포함한다. | `tests/test_search_explain.py::test_chat_defers_eight_record_limit_until_all_queries_are_combined` |
| RR-27 | 긴 대화에서 과거 문맥을 압축하고 토큰 예산 부족을 오류로 구분하며 근거를 새 사실로 만들지 않는다. | `tests/test_behavior_operations.py::test_long_conversation_budget_preserves_sources` |
| PF-24 | 긴 대화에서 과거 문맥을 압축하고 토큰 예산 부족을 오류로 구분하며 근거를 새 사실로 만들지 않는다. | `tests/test_behavior_operations.py::test_long_conversation_budget_preserves_sources` |
| CV-09 | 긴 대화에서 과거 문맥을 압축하고 토큰 예산 부족을 오류로 구분하며 근거를 새 사실로 만들지 않는다. | `tests/test_behavior_operations.py::test_long_conversation_budget_preserves_sources` |
| RR-29 | 수정·삭제·임베딩 모델 변경 직후 기존 캐시/벡터를 검색에서 제외한다. | `tests/test_database_performance.py::test_cached_search_after_edit_trash_and_model_change` |
| RR-35 | 수정·삭제·임베딩 모델 변경 직후 기존 캐시/벡터를 검색에서 제외한다. | `tests/test_database_performance.py::test_cached_search_after_edit_trash_and_model_change` |
| EV-18 | 수정·삭제·임베딩 모델 변경 직후 기존 캐시/벡터를 검색에서 제외한다. | `tests/test_database_performance.py::test_cached_search_after_edit_trash_and_model_change` |
| SEC-19 | 수정·삭제·임베딩 모델 변경 직후 기존 캐시/벡터를 검색에서 제외한다. | `tests/test_database_performance.py::test_cached_search_after_edit_trash_and_model_change` |
| RR-34 | 3.5km/3500m는 같은 거리이고 3.5m·소수점 제거·부정은 동등하지 않다. | `tests/test_behavior_operations.py::test_units_and_numbers_are_not_equivalent_by_spelling` |
| EV-10 | 필수 근거 그룹 중 하나가 누락되면 전체 답변 성공으로 판정하지 않는다. | `tests/test_behavior_operations.py::test_multiple_required_evidence_groups_are_independent` |
| EV-14 | 필수 근거 그룹 중 하나가 누락되면 전체 답변 성공으로 판정하지 않는다. | `tests/test_behavior_operations.py::test_multiple_required_evidence_groups_are_independent` |
| AG-14 | 필수 근거 그룹 중 하나가 누락되면 전체 답변 성공으로 판정하지 않는다. | `tests/test_behavior_operations.py::test_multiple_required_evidence_groups_are_independent` |
| EV-12 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-15 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-16 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-17 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-29 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-30 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| AG-33 | 존재하는 원문 ID·버전·연속 인용만 허용하며 잘못된 원문·부정 반전·다른 인물 인용은 검증 승인이 있어도 거절한다. | `tests/test_chat_grounding.py::test_review_uses_only_original_spans_and_display_cannot_reject_facts`<br>`tests/test_chat_grounding.py::test_source_selection_never_bypasses_semantic_or_identity_checks` |
| EV-21 | 검증하지 않은 해석·일반 지식을 사용자 이력이나 검색 결과로 표시하지 않는다. | `tests/test_conversation_policy.py::test_general_generation_never_receives_unverified_interpretation`<br>`tests/test_conversation_policy.py::test_no_search_record_absence_claim_is_rejected_even_if_model_approves` |
| EV-24 | 다른 프로젝트·시점·조건·단위를 무시한 단순 비교를 확정 사실로 채택하지 않는다. | `tests/test_behavior_operations.py::test_comparisons_require_matching_subject_time_and_units` |
| CV-01 | 실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다. | `tests/test_evaluation_remediation.py::test_disabled_or_explicit_general_never_reads_the_corpus`<br>`tests/test_evaluation_remediation.py::test_private_identifiers_override_general_classifier` |
| AG-03 | 실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다. | `tests/test_evaluation_remediation.py::test_disabled_or_explicit_general_never_reads_the_corpus`<br>`tests/test_evaluation_remediation.py::test_private_identifiers_override_general_classifier` |
| AG-06 | 실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다. | `tests/test_evaluation_remediation.py::test_disabled_or_explicit_general_never_reads_the_corpus`<br>`tests/test_evaluation_remediation.py::test_private_identifiers_override_general_classifier` |
| CV-24 | 실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다. | `tests/test_evaluation_remediation.py::test_disabled_or_explicit_general_never_reads_the_corpus`<br>`tests/test_evaluation_remediation.py::test_private_identifiers_override_general_classifier` |
| CV-30 | 실제 원문의 식별자 질문은 검색하고 일반 모드·개인 기록 거부는 검색하지 않는다. | `tests/test_evaluation_remediation.py::test_disabled_or_explicit_general_never_reads_the_corpus`<br>`tests/test_evaluation_remediation.py::test_private_identifiers_override_general_classifier` |
| CV-04 | 사용자가 선택한 결과 ID의 주제·속성으로만 후속 질문을 연결한다. | `tests/test_conversation_uxr.py::test_UXR03_selected_followup_preserves_topic_feature` |
| CV-05 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-06 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-07 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-12 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-22 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-26 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-27 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| AG-22 | 주제/날짜 정정은 해당 조건만 갱신하며 다른 프로젝트의 이전 인물·날짜 조건을 끌고 오지 않는다. | `tests/test_behavior_operations.py::test_context_changes_preserve_only_still_valid_constraints` |
| CV-10 | 세션·재시작·같은 요청 재전송의 문맥과 접근 범위를 보존한다. | `tests/chat/test_integration.py::test_owner_isolation_covers_all_access`<br>`tests/chat/test_integration.py::test_store_idempotency_context_restart_and_pagination` |
| CV-11 | 세션·재시작·같은 요청 재전송의 문맥과 접근 범위를 보존한다. | `tests/chat/test_integration.py::test_owner_isolation_covers_all_access`<br>`tests/chat/test_integration.py::test_store_idempotency_context_restart_and_pagination` |
| CV-17 | 세션·재시작·같은 요청 재전송의 문맥과 접근 범위를 보존한다. | `tests/chat/test_integration.py::test_owner_isolation_covers_all_access`<br>`tests/chat/test_integration.py::test_store_idempotency_context_restart_and_pagination` |
| CV-20 | 대화 저장은 실제 선택 메시지와 원문 출처를 검증한 승인 경로로만 세션을 넘어 유지된다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_selection_and_cross_session_sources` |
| MW-18 | 대화 저장은 실제 선택 메시지와 원문 출처를 검증한 승인 경로로만 세션을 넘어 유지된다. | `tests/test_memory_capture.py::test_approval_and_restart`<br>`tests/test_memory_capture.py::test_selection_and_cross_session_sources` |
| CV-28 | 같은 요청의 재생성/캐시만 재사용하고 질문·원문 버전·모델·정책이 바뀌면 다시 처리한다. | `tests/test_model_reuse.py::test_question_full_revision_preprocessing_model_and_policy_invalidate`<br>`tests/test_model_reuse.py::test_reuses_only_same_request_and_returns_isolated_values` |
| AG-36 | 같은 요청의 재생성/캐시만 재사용하고 질문·원문 버전·모델·정책이 바뀌면 다시 처리한다. | `tests/test_model_reuse.py::test_question_full_revision_preprocessing_model_and_policy_invalidate`<br>`tests/test_model_reuse.py::test_reuses_only_same_request_and_returns_isolated_values` |
| CV-29 | 기록을 쓰지 말라는 요청이 검색/선호/이전 AI 주장보다 우선한다. | `tests/test_conversation_policy.py::test_memory_refusal_precedes_all_routes`<br>`tests/test_conversation_policy.py::test_refusal_scrubs_all_recalled_sources_and_assistant_claims` |
| AG-18 | 문단·목록·표·상세/간결 표현의 표시 제안도 검증한 주장만 참조하며 표시 실패로 사실 답변을 없애지 않는다. | `tests/test_chat_presentation.py::test_metadata_rejection_does_not_remove_answer`<br>`tests/test_chat_presentation.py::test_reviewed_kinds` |
| AG-19 | 문단·목록·표·상세/간결 표현의 표시 제안도 검증한 주장만 참조하며 표시 실패로 사실 답변을 없애지 않는다. | `tests/test_chat_presentation.py::test_metadata_rejection_does_not_remove_answer`<br>`tests/test_chat_presentation.py::test_reviewed_kinds` |
| AG-20 | 문단·목록·표·상세/간결 표현의 표시 제안도 검증한 주장만 참조하며 표시 실패로 사실 답변을 없애지 않는다. | `tests/test_chat_presentation.py::test_metadata_rejection_does_not_remove_answer`<br>`tests/test_chat_presentation.py::test_reviewed_kinds` |
| AG-23 | 저장·수정은 원문 미리보기·승인·버전 확인을 거치며 재전송은 멱등적이다. | `tests/test_memory_complete.py::test_review_links_edit_invalidation_and_idempotency`<br>`tests/test_memory_complete.py::test_snapshot_change_rejects_approval` |
| AG-24 | 저장·수정은 원문 미리보기·승인·버전 확인을 거치며 재전송은 멱등적이다. | `tests/test_memory_complete.py::test_review_links_edit_invalidation_and_idempotency`<br>`tests/test_memory_complete.py::test_snapshot_change_rejects_approval` |
| AG-27 | 대화 요약/이전 AI 응답만으로 사용자 사실을 만들지 않고 원문과 제안 출처를 추적한다. | `tests/test_memory_complete.py::test_correction_preserves_ai_origin`<br>`tests/test_memory_complete.py::test_extraction_rejects_fabricated_source` |
| MW-17 | 대화 요약/이전 AI 응답만으로 사용자 사실을 만들지 않고 원문과 제안 출처를 추적한다. | `tests/test_memory_complete.py::test_correction_preserves_ai_origin`<br>`tests/test_memory_complete.py::test_extraction_rejects_fabricated_source` |
| MW-22 | 대화 요약/이전 AI 응답만으로 사용자 사실을 만들지 않고 원문과 제안 출처를 추적한다. | `tests/test_memory_complete.py::test_correction_preserves_ai_origin`<br>`tests/test_memory_complete.py::test_extraction_rejects_fabricated_source` |
| AG-28 | 추천과 다음 단계는 일반 제안으로 표시하며 과거 기록의 확정 사실로 지어내지 않는다. | `tests/test_conversation_uxr.py::test_UXR09_resume_action_cannot_invent_curriculum`<br>`tests/test_conversation_uxr.py::test_UXR10_recommendation_is_an_optional_suggestion` |
| AG-30 | 외부 실시간 검색 기능이 없어 현재 외부 값을 개인 기록으로 확정하지 않는다. | `tests/test_conversation_policy.py::test_general_generation_never_receives_unverified_interpretation` |
| AG-31 | 실제 HTTP 경로의 모델 연결 실패·시간 초과·잘못된 응답은 오류와 재시도 상태로 전달한다. | `tests/test_behavior_operations.py::test_http_failures_are_errors_not_empty_answers` |
| AG-32 | 실제 HTTP 경로의 모델 연결 실패·시간 초과·잘못된 응답은 오류와 재시도 상태로 전달한다. | `tests/test_behavior_operations.py::test_http_failures_are_errors_not_empty_answers` |
| MW-06 | 프로젝트 목표·결정은 실제 대화 출처의 승인한 기억으로만 활용한다. | `tests/test_memory_capture.py::test_decision_capture_uses_actual_turns_and_preferences_update` |
| MW-20 | 만료/보존 처리와 복원에서 보관 상태를 보존하고 만료된 기억을 활성 검색에 되살리지 않는다. | `tests/test_memory_complete.py::test_archival_and_retention`<br>`tests/test_memory_complete.py::test_archived_record_stays_excluded_after_legacy_restore` |
| SEC-20 | 만료/보존 처리와 복원에서 보관 상태를 보존하고 만료된 기억을 활성 검색에 되살리지 않는다. | `tests/test_memory_complete.py::test_archival_and_retention`<br>`tests/test_memory_complete.py::test_archived_record_stays_excluded_after_legacy_restore` |
| SEC-12 | 로그·성능·오류 진단에는 원문/모델 응답/비밀 오류 문자열을 저장하지 않는다. | `tests/test_response_latency.py::test_failure_measurement_never_includes_exception_or_request_text`<br>`tests/test_response_latency.py::test_transport_usage_is_allowlisted` |
| SEC-14 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-01 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-02 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-03 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-04 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-05 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-06 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-07 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-08 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-09 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-10 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-11 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-12 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-13 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-14 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-15 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-16 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-17 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-18 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-19 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-20 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-21 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-22 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. / 검색 결과 offset 페이지 API는 현재 지원하지 않으므로 거절을 검사한다. 대화 목록 페이지와 혼동하지 않는다. | `tests/test_behavior_operations.py::test_ui_contracts`<br>`tests/test_behavior_operations.py::test_unsupported_fields_and_permissions_are_rejected[offset]` |
| UI-23 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-24 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| UI-25 | 실제 제품 화면 모듈의 탐색·출처·에러·취소·초기화·원문·보안·접근성 동작을 실행하여 검사한다. | `tests/test_behavior_operations.py::test_ui_contracts` |
| SEC-15 | 경로 순회·NUL·허용하지 않는 파일·크기 초과를 실제 가져오기 검증에서 거절한다. | `tests/test_conversation_policy.py::test_upload_invalid_content` |
| SEC-16 | 경로 순회·NUL·허용하지 않는 파일·크기 초과를 실제 가져오기 검증에서 거절한다. | `tests/test_conversation_policy.py::test_upload_invalid_content` |
| PF-01 | 0건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[0]` |
| PF-02 | 1건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[1]` |
| PF-03 | 100건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[100]` |
| PF-04 | 1000건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[1000]` |
| PF-05 | 10000건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[10000]` |
| PF-06 | 100000건 합성 DB의 검색 스냅샷·벡터 수와 제한된 캐시를 실제로 검사한다. | `tests/test_behavior_operations.py::test_corpus_scale_and_bounded_vectors[100000]` |
| PF-07 | 허용하는 긴 원문의 청크 경계·위치·원문 복원을 검사한다. | `tests/test_behavior_operations.py::test_chunk_hierarchy_preserves_exact_source_and_bounds` |
| PF-08 | 반복 원문은 중복 후보로 식별하되 유사한 다른 사실은 자동 삭제/병합하지 않는다. | `tests/test_memory_capture.py::test_distinct_facts_are_never_automatic_duplicates`<br>`tests/test_memory_capture.py::test_duplicate_correction_delete` |
| PF-09 | 동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다. | `tests/test_behavior_operations.py::test_concurrent_store_search_and_restart_are_consistent` |
| PF-10 | 동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다. | `tests/test_behavior_operations.py::test_concurrent_store_search_and_restart_are_consistent` |
| PF-11 | 동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다. | `tests/test_behavior_operations.py::test_concurrent_store_search_and_restart_are_consistent` |
| PF-21 | 동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다. | `tests/test_behavior_operations.py::test_concurrent_store_search_and_restart_are_consistent` |
| PF-25 | 동시 읽기/저장/삭제/재시작에서 최신 버전과 활성 원문만 보이고 저장이 지속된다. | `tests/test_behavior_operations.py::test_concurrent_store_search_and_restart_are_consistent` |
| PF-13 | 손상된 DB/벡터는 명확한 오류로 보고하며 성공·빈 결과로 위장하지 않는다. | `tests/test_behavior_operations.py::test_corrupt_database_and_vectors_fail_explicitly` |
| PF-26 | 손상된 DB/벡터는 명확한 오류로 보고하며 성공·빈 결과로 위장하지 않는다. | `tests/test_behavior_operations.py::test_corrupt_database_and_vectors_fail_explicitly` |
| PF-14 | 모델 시간 초과는 무제한 재시도하지 않고 임베딩 실패 복구 시 성공한 추출을 재사용한다. | `tests/test_performance.py::test_embedding_retry_reuses_extraction`<br>`tests/test_performance.py::test_extraction_read_timeout_is_not_repeated` |
| PF-15 | 모델 시간 초과는 무제한 재시도하지 않고 임베딩 실패 복구 시 성공한 추출을 재사용한다. | `tests/test_performance.py::test_embedding_retry_reuses_extraction`<br>`tests/test_performance.py::test_extraction_read_timeout_is_not_repeated` |
| PF-16 | 취소/시간 초과는 대기 우선순위와 잠금을 안전하게 해제한다. | `tests/test_performance.py::test_foreground_deadline_does_not_leak_waiter_or_release_owners_lock`<br>`tests/test_performance.py::test_wait_cancellation_removes_foreground_priority` |
| PF-17 | 임베딩 변경 시 원문 ID와 추출을 고정하고 후보 전용 벡터만 다시 구축한다. | `tests/test_response_latency.py::test_embedding_profile_separates_index_and_only_prefixes_queries`<br>`tests/test_response_latency.py::test_model_comparison_reuses_source_ids_and_only_rebuilds_vectors` |
| PF-18 | 캐시는 같은 요청/검증한 결과만 재사용하며 오류·잘못된 인용은 저장하지 않는다. | `tests/test_model_reuse.py::test_invalid_quotes_and_model_errors_are_not_cached`<br>`tests/test_model_reuse.py::test_reuses_only_same_request_and_returns_isolated_values` |
| PF-19 | 실제 장치와 측정 표본·워밍업·실패를 보존하며 CPU를 GPU 측정으로 표시하지 않는다. | `tests/test_performance_benchmark.py::test_cpu_only_device_messages_cannot_be_labeled_gpu`<br>`tests/test_performance_benchmark.py::test_summary_excludes_warmup_and_keeps_failures` |
| PF-20 | 캐시 예산을 초과하면 캐시를 해제하고 비정상 벡터를 사용하지 않는다. | `tests/test_database_performance.py::test_vector_cache_generation_model_order_subset_and_budget` |
| PF-23 | 사용자 요청은 다음 배경 작업보다 우선하며 배경 대기는 취소 가능하다. | `tests/test_performance.py::test_background_wait_outlives_model_http_timeout_and_can_stop`<br>`tests/test_performance.py::test_foreground_runs_before_next_background_call` |
| LC-26 | 일 년 전 사건의 실제 날짜와 현재 저장일을 구분하고 원문을 보존한다. | `tests/test_behavior_operations.py::test_year_old_event_is_not_replaced_by_storage_date` |
