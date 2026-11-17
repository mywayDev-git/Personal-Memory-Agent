# 이전 489개 변수와의 초안 대조

자동 연결을 공식 커버리지나 통과로 해석하지 않습니다.

{'NOT_COVERED': 302, 'PARTIAL': 96, 'SEPARATE_FUNCTIONAL_TEST': 91}

| 변수 | 상태 | 연결 사례 | 설명 |
|---|---|---|---|
| IN-01 | NOT_COVERED | — | 직접 문장 입력 · 자유로운 자연어 |
| IN-02 | PARTIAL | MC-24 | 키워드만 입력 · 완전한 문장 아님 |
| IN-03 | NOT_COVERED | — | 장문의 일기 입력 · 여러 사건 포함 |
| IN-04 | PARTIAL | MC-24 | 메모를 여러 줄 붙여넣기 · 줄바꿈 및 목록 구조 |
| IN-05 | NOT_COVERED | — | 대화 중 "기억해줘" 요청 · 명시적 저장 의도 |
| IN-06 | NOT_COVERED | — | 일반 대화에서 개인 정보 언급 · 자동 저장 정책 |
| IN-07 | NOT_COVERED | — | 검색한 기록을 다시 저장 · 중복 및 출처 관리 |
| IN-08 | NOT_COVERED | — | PDF 업로드 · 텍스트 추출 및 페이지 위치 |
| IN-09 | NOT_COVERED | — | TXT/Markdown 업로드 · 원문 구조 보존 |
| IN-10 | NOT_COVERED | — | DOCX/문서 업로드 · 제목, 표, 문단 구조 |
| IN-11 | NOT_COVERED | — | CSV/JSON 업로드 · 구조화 필드 |
| IN-12 | NOT_COVERED | — | 이미지 또는 스크린샷 입력 · OCR·시각 정보 추출 가능 여부 |
| IN-13 | NOT_COVERED | — | 음성 입력·전사 텍스트 · 음성 인식 오류 |
| IN-14 | NOT_COVERED | — | 여러 파일 동시 입력 · 파일별 출처 유지 |
| IN-15 | NOT_COVERED | — | 외부 서비스에서 가져오기 · 출처·권한·동기화 |
| IN-16 | NOT_COVERED | — | 이전 기록 복사해서 입력 · 중복 판별 |
| IN-17 | NOT_COVERED | — | 저장 요청 취소 · 작업 취소 및 부작용 |
| IN-18 | NOT_COVERED | — | 입력 도중 네트워크 끊김 · 재시도 및 중복 생성 방지 |
| IN-19 | NOT_COVERED | — | 다른 기기에서 동시에 입력 · 동시성 및 충돌 |
| IN-20 | NOT_COVERED | — | 일부 정보만 입력 후 추후 보완 · 기존 기록 연결 |
| IN-21 | NOT_COVERED | — | 일정 · "11월 3일 오후 2시 발표" |
| IN-22 | NOT_COVERED | — | 할 일 · "금요일까지 보고서 작성" |
| IN-23 | NOT_COVERED | — | 개인 경험 · "어제 친구와 카페에 갔다" |
| IN-24 | NOT_COVERED | — | 의사결정 · "벡터 검색을 기본으로 사용하기로 했다" |
| IN-25 | NOT_COVERED | — | 의견 · "이 UI는 복잡한 것 같다" |
| IN-26 | NOT_COVERED | — | 선호도 · "나는 간결한 답변을 좋아한다" |
| IN-27 | NOT_COVERED | — | 프로젝트 진행 · "API 설계를 완료했다" |
| IN-28 | NOT_COVERED | — | 문제 및 오류 · "인덱싱 중 타임아웃 발생" |
| IN-29 | NOT_COVERED | — | 문제 해결 과정 · "배치 크기를 줄여 해결" |
| IN-30 | NOT_COVERED | — | 학습 기록 · "오늘 A\* 알고리즘 공부" |
| IN-31 | NOT_COVERED | — | 인물 관계 · "민수는 디자인 담당" |
| IN-32 | NOT_COVERED | — | 장소·방문 · "지난주 부산 출장" |
| IN-33 | PARTIAL | MC-02, MC-08, MC-26 | 구매 기록 · "노트북을 120만 원에 구매" |
| IN-34 | PARTIAL | MC-05 | 수치 데이터 · "정확도가 0.83에서 0.89로 상승" |
| IN-35 | PARTIAL | MC-03 | 가설 · "오류는 캐시 문제인 것 같다" |
| IN-36 | PARTIAL | MC-03 | 확정 사실 · "원인은 캐시 무효화 실패였다" |
| IN-37 | NOT_COVERED | — | 미완료 계획 · "다음 달에 배포할 예정" |
| IN-38 | NOT_COVERED | — | 취소된 계획 · "배포를 취소했다" |
| IN-39 | NOT_COVERED | — | 타인에게 들은 내용 · "동료가 서버가 느리다고 말했다" |
| IN-40 | NOT_COVERED | — | 질문만 있는 기록 · "왜 검색이 느릴까?" |
| IN-41 | NOT_COVERED | — | 부정적 사실 · "그때 API를 사용하지 않았다" |
| IN-42 | PARTIAL | MC-01 | 조건부 사실 · "테스트가 통과하면 배포한다" |
| IN-43 | NOT_COVERED | — | 비교·선택 · "A 대신 B를 사용하기로 했다" |
| IN-44 | NOT_COVERED | — | 비밀·민감정보 · 개인 정보 보호 및 저장 동의 |
| IN-45 | NOT_COVERED | — | 무관한 복수 주제 · 한 입력에서 사건 분리 |
| IN-46 | NOT_COVERED | — | 길이 · 한 글자, 한 문장, 장문, 매우 긴 문서 |
| IN-47 | NOT_COVERED | — | 길이 · 한 글자, 한 문장, 장문, 매우 긴 문서 |
| IN-48 | NOT_COVERED | — | 길이 · 한 글자, 한 문장, 장문, 매우 긴 문서 |
| IN-49 | NOT_COVERED | — | 길이 · 한 글자, 한 문장, 장문, 매우 긴 문서 |
| IN-50 | NOT_COVERED | — | 언어 · 한국어, 영어, 혼합, 번역 표현 |
| IN-51 | NOT_COVERED | — | 언어 · 한국어, 영어, 혼합, 번역 표현 |
| IN-52 | NOT_COVERED | — | 언어 · 한국어, 영어, 혼합, 번역 표현 |
| IN-53 | NOT_COVERED | — | 언어 · 한국어, 영어, 혼합, 번역 표현 |
| IN-54 | PARTIAL | MC-24 | 문장 품질 · 오타, 띄어쓰기 오류, 축약어, 비문 |
| IN-55 | NOT_COVERED | — | 문장 품질 · 오타, 띄어쓰기 오류, 축약어, 비문 |
| IN-56 | NOT_COVERED | — | 문장 품질 · 오타, 띄어쓰기 오류, 축약어, 비문 |
| IN-57 | NOT_COVERED | — | 문장 품질 · 오타, 띄어쓰기 오류, 축약어, 비문 |
| IN-58 | NOT_COVERED | — | 기호 · 이모지, 특수문자, Markdown, 코드 |
| IN-59 | NOT_COVERED | — | 기호 · 이모지, 특수문자, Markdown, 코드 |
| IN-60 | NOT_COVERED | — | 기호 · 이모지, 특수문자, Markdown, 코드 |
| IN-61 | NOT_COVERED | — | 기호 · 이모지, 특수문자, Markdown, 코드 |
| IN-62 | NOT_COVERED | — | 불완전성 · 주어 생략, 목적어 생략, 시간 누락, 지시어 |
| IN-63 | NOT_COVERED | — | 불완전성 · 주어 생략, 목적어 생략, 시간 누락, 지시어 |
| IN-64 | NOT_COVERED | — | 불완전성 · 주어 생략, 목적어 생략, 시간 누락, 지시어 |
| IN-65 | NOT_COVERED | — | 불완전성 · 주어 생략, 목적어 생략, 시간 누락, 지시어 |
| IN-66 | NOT_COVERED | — | 모순 · 같은 문장 내 충돌, 과거 기록과 충돌, 철회, 정정 |
| IN-67 | NOT_COVERED | — | 모순 · 같은 문장 내 충돌, 과거 기록과 충돌, 철회, 정정 |
| IN-68 | NOT_COVERED | — | 모순 · 같은 문장 내 충돌, 과거 기록과 충돌, 철회, 정정 |
| IN-69 | NOT_COVERED | — | 모순 · 같은 문장 내 충돌, 과거 기록과 충돌, 철회, 정정 |
| IN-70 | NOT_COVERED | — | 데이터 이상 · 빈 문자열, 공백뿐인 문자열, 깨진 인코딩, 중복 |
| IN-71 | NOT_COVERED | — | 데이터 이상 · 빈 문자열, 공백뿐인 문자열, 깨진 인코딩, 중복 |
| IN-72 | NOT_COVERED | — | 데이터 이상 · 빈 문자열, 공백뿐인 문자열, 깨진 인코딩, 중복 |
| IN-73 | NOT_COVERED | — | 데이터 이상 · 빈 문자열, 공백뿐인 문자열, 깨진 인코딩, 중복 |
| IN-74 | NOT_COVERED | — | 식별자 · 파일명, 경로, URL, 코드 심볼 |
| IN-75 | NOT_COVERED | — | 식별자 · 파일명, 경로, URL, 코드 심볼 |
| IN-76 | NOT_COVERED | — | 식별자 · 파일명, 경로, URL, 코드 심볼 |
| IN-77 | NOT_COVERED | — | 식별자 · 파일명, 경로, URL, 코드 심볼 |
| IN-78 | PARTIAL | MC-24, MC-34 | 복합 구조 · 표, 목록, 인용문, 대화 전사 |
| IN-79 | NOT_COVERED | — | 복합 구조 · 표, 목록, 인용문, 대화 전사 |
| IN-80 | NOT_COVERED | — | 복합 구조 · 표, 목록, 인용문, 대화 전사 |
| IN-81 | NOT_COVERED | — | 복합 구조 · 표, 목록, 인용문, 대화 전사 |
| IN-82 | NOT_COVERED | — | 불확실성 · 추측, 가능성, 질문, 미확인 소문 |
| IN-83 | NOT_COVERED | — | 불확실성 · 추측, 가능성, 질문, 미확인 소문 |
| IN-84 | NOT_COVERED | — | 불확실성 · 추측, 가능성, 질문, 미확인 소문 |
| IN-85 | NOT_COVERED | — | 불확실성 · 추측, 가능성, 질문, 미확인 소문 |
| EX-01 | NOT_COVERED | — | 핵심 주제 · 기록이 무엇에 관한 것인가 |
| EX-02 | NOT_COVERED | — | 사건 · 무엇이 발생했는가 |
| EX-03 | NOT_COVERED | — | 행위자 · 누가 행동했는가 |
| EX-04 | PARTIAL | MC-02, MC-06 | 대상 · 누구에게 또는 무엇에 대해 |
| EX-05 | PARTIAL | MC-09, MC-19 | 발생 일시 · 실제 사건 날짜 |
| EX-06 | PARTIAL | MC-09, MC-19 | 기록 생성 일시 · 시스템에 저장한 날짜 |
| EX-07 | NOT_COVERED | — | 수정 일시 · 정정·갱신 날짜 |
| EX-08 | PARTIAL | MC-04 | 기간 · 시작·종료·진행 중 |
| EX-09 | PARTIAL | MC-08, MC-26 | 장소 · 어디에서 발생했는가 |
| EX-10 | NOT_COVERED | — | 프로젝트 · 어떤 작업과 연결되는가 |
| EX-11 | PARTIAL | MC-01, MC-04, MC-07, MC-12, MC-25 | 상태 · 예정·진행·완료·취소·실패 |
| EX-12 | NOT_COVERED | — | 사실 여부 · 사실·추정·의견·질문 |
| EX-13 | NOT_COVERED | — | 확실성 · 명시된 확실성 수준 |
| EX-14 | PARTIAL | MC-03 | 원인·결과 · A 때문에 B가 발생 |
| EX-15 | NOT_COVERED | — | 선후관계 · A 후 B 수행 |
| EX-16 | PARTIAL | MC-07, MC-29 | 인물 간 관계 · 담당자·동료·친구 |
| EX-17 | PARTIAL | MC-01, MC-10, MC-25 | 기록 간 관계 · 기존 기록의 업데이트 |
| EX-18 | NOT_COVERED | — | 동의어·별칭 · ML = 머신러닝 |
| EX-19 | PARTIAL | MC-02 | 부정 표현 · 하지 않음·아님 |
| EX-20 | NOT_COVERED | — | 조건 표현 · \~한다면 |
| EX-21 | NOT_COVERED | — | 원문 출처 · 파일·대화·직접 입력 |
| EX-22 | NOT_COVERED | — | 원문 위치 · 페이지·문단·메시지 ID |
| EX-23 | NOT_COVERED | — | 접근 권한 · 개인·공유·비공개 |
| EX-24 | NOT_COVERED | — | 저장 허용 여부 · 동의 및 정책 적용 |
| EX-25 | PARTIAL | MC-06, MC-29, MC-32 | 사용자와 타인 구별 · 타인의 의견을 사용자 선호로 저장하지 않음 |
| ST-01 | SEPARATE_FUNCTIONAL_TEST | — | 새로운 기록 저장 · 신규 ID 생성 |
| ST-02 | SEPARATE_FUNCTIONAL_TEST | — | 완전히 동일한 기록 재저장 · 중복 정책 적용 |
| ST-03 | SEPARATE_FUNCTIONAL_TEST | — | 표현만 다른 중복 · 의미적 중복 후보 판별 |
| ST-04 | SEPARATE_FUNCTIONAL_TEST | — | 같은 사건의 추가 정보 · 기존 사건과 연결 |
| ST-05 | PARTIAL | MC-10 | 기존 사실 정정 · 현재 유효 사실 갱신 |
| ST-06 | PARTIAL | MC-15, MC-27 | 정정한 내용을 다시 정정 · 변경 이력 보존 |
| ST-07 | PARTIAL | MC-15 | 과거 결정을 번복 · 최신 상태와 과거 상태 구분 |
| ST-08 | SEPARATE_FUNCTIONAL_TEST | — | 서로 다른 사람의 동명 기록 · 개체 혼합 방지 |
| ST-09 | SEPARATE_FUNCTIONAL_TEST | — | 유사한 두 프로젝트 기록 · 프로젝트별 분리 |
| ST-10 | SEPARATE_FUNCTIONAL_TEST | — | 일부 문장만 수정 · 원본 및 파생 인덱스 동기화 |
| ST-11 | SEPARATE_FUNCTIONAL_TEST | — | 제목 수정 · 본문·색인 일관성 |
| ST-12 | SEPARATE_FUNCTIONAL_TEST | — | 태그 추가·제거 · 필터 반영 |
| ST-13 | SEPARATE_FUNCTIONAL_TEST | — | 기록 삭제 · 검색 결과에서 제외 |
| ST-14 | SEPARATE_FUNCTIONAL_TEST | — | 여러 기록 일괄 삭제 · 관련 색인·캐시 처리 |
| ST-15 | SEPARATE_FUNCTIONAL_TEST | — | 기록 복원 · 복원 정책에 따른 재색인 |
| ST-16 | SEPARATE_FUNCTIONAL_TEST | — | 저장 중 오류 · 부분 저장 및 불일치 방지 |
| ST-17 | SEPARATE_FUNCTIONAL_TEST | — | 인덱싱 실패 · 상태 표시·재시도 |
| ST-18 | SEPARATE_FUNCTIONAL_TEST | — | 동시 수정 · 버전 충돌 처리 |
| ST-19 | SEPARATE_FUNCTIONAL_TEST | — | 공유 기록 접근권 변경 · 검색 권한 즉시 반영 |
| ST-20 | SEPARATE_FUNCTIONAL_TEST | — | 기록의 원본 출처 삭제 · 파생 정보 처리 정책 검증 |
| ST-21 | SEPARATE_FUNCTIONAL_TEST | — | 대화 기억 삭제 · 장기 기억·캐시·검색 인덱스 반영 |
| ST-22 | SEPARATE_FUNCTIONAL_TEST | — | 대용량 문서 재업로드 · 버전 및 중복 관리 |
| ST-23 | SEPARATE_FUNCTIONAL_TEST | — | 기존 기록과 반대 내용 저장 · 충돌 보존 및 최신 사실 판별 |
| ST-24 | SEPARATE_FUNCTIONAL_TEST | — | 기록 저장 직후 검색 · 읽기 일관성·인덱싱 대기 상태 |
| ST-25 | SEPARATE_FUNCTIONAL_TEST | — | 실패한 요청 재시도 · 멱등성으로 중복 방지 |
| QI-01 | NOT_COVERED | — | 명시적 검색 · "검색해줘" |
| QI-02 | NOT_COVERED | — | 과거 회상 · "내가 전에 뭐 했었지?" |
| QI-03 | NOT_COVERED | — | 사실 확인 · "그때 어떤 모델 사용했어?" |
| QI-04 | NOT_COVERED | — | 시간 확인 · "언제 결정했지?" |
| QI-05 | NOT_COVERED | — | 인물 확인 · "누구랑 작업했더라?" |
| QI-06 | PARTIAL | MC-20 | 이유 확인 · "왜 그 방법을 선택했지?" |
| QI-07 | NOT_COVERED | — | 방법 확인 · "그 오류 어떻게 고쳤더라?" |
| QI-08 | NOT_COVERED | — | 기록 위치 찾기 · "그 내용이 어디에 있어?" |
| QI-09 | NOT_COVERED | — | 특정 기록 재현 · "지난번 회의 내용 보여줘" |
| QI-10 | NOT_COVERED | — | 내용 요약 · "이번 달 작업 요약해줘" |
| QI-11 | PARTIAL | MC-27 | 기록 비교 · "이전 방법과 지금 방법 비교해줘" |
| QI-12 | PARTIAL | MC-27 | 변화 추적 · "계획이 어떻게 바뀌었지?" |
| QI-13 | PARTIAL | MC-13, MC-30, MC-35 | 활동 나열 · "지난주에 한 일 전부 알려줘" |
| QI-14 | PARTIAL | MC-13, MC-17, MC-28, MC-30 | 수량 집계 · "몇 번 수정했어?" |
| QI-15 | NOT_COVERED | — | 누락 확인 · "아직 안 한 작업은?" |
| QI-16 | PARTIAL | MC-15 | 최신 정보 · "마지막으로 결정한 내용은?" |
| QI-17 | PARTIAL | MC-15 | 최초 정보 · "처음 이 문제를 발견한 때는?" |
| QI-18 | NOT_COVERED | — | 개인화 · "내가 좋아하는 방식으로 설명해줘" |
| QI-19 | NOT_COVERED | — | 대화 내 암묵적 검색 · "그때 해결한 방법 적용하자" |
| QI-20 | NOT_COVERED | — | 일반 상식 질문 · "벡터 검색이 뭐야?" |
| QI-21 | NOT_COVERED | — | 일반 질문과 개인 질문 혼합 · "벡터 검색의 장점이랑 우리 프로젝트 적용 결과 알려줘" |
| QI-22 | NOT_COVERED | — | 검색 버튼 사용 · 검색 UI를 명시적으로 실행 |
| QI-23 | NOT_COVERED | — | 기록 없는 일반 대화 · "오늘 좀 피곤하다" |
| QI-24 | NOT_COVERED | — | 저장 요청 · "이 결정 기록해줘" |
| QI-25 | NOT_COVERED | — | 삭제 요청 · "그 내용 기억에서 지워줘" |
| QU-01 | NOT_COVERED | — | 정확한 제목 · "Personal Memory Agent" |
| QU-02 | NOT_COVERED | — | 정확한 키워드 · "벡터 인덱스" |
| QU-03 | NOT_COVERED | — | 불완전한 키워드 · "인덱스" |
| QU-04 | NOT_COVERED | — | 자연어 질문 · "왜 검색이 느려졌어?" |
| QU-05 | NOT_COVERED | — | 한 단어 · "모델" |
| QU-06 | NOT_COVERED | — | 아주 짧은 문장 · "그때 뭐였지?" |
| QU-07 | NOT_COVERED | — | 장문 질문 · 복수 조건을 포함한 질문 |
| QU-08 | PARTIAL | MC-18 | 한국어·영어 혼합 · "retrieval 성능 테스트" |
| QU-09 | PARTIAL | MC-18, MC-34 | 한영 별칭 · "machine learning" ↔ "머신러닝" |
| QU-10 | PARTIAL | MC-18 | 약어 · "PMA", "LLM" |
| QU-11 | PARTIAL | MC-18 | 오타 · "머신러닝 검섹" |
| QU-12 | PARTIAL | MC-18, MC-24 | 띄어쓰기 오류 · "검색정확도개선" |
| QU-13 | NOT_COVERED | — | 발음 기반 표기 · "욜로 모델" |
| QU-14 | NOT_COVERED | — | 유사어 · "버그", "오류", "에러" |
| QU-15 | NOT_COVERED | — | 주제와 무관한 유사어 · 의미가 다른 확장 차단 |
| QU-16 | NOT_COVERED | — | 동음이의어 · "파이썬"의 문맥 |
| QU-17 | NOT_COVERED | — | 복수 의미 · "모델" = AI 모델 또는 설계 모델 |
| QU-18 | NOT_COVERED | — | 지시어 · "그거", "저번 거" |
| QU-19 | NOT_COVERED | — | 생략된 주어 · "언제 끝났어?" |
| QU-20 | NOT_COVERED | — | 부정 · "완료하지 않은 작업" |
| QU-21 | NOT_COVERED | — | 비교 · "A보다 B가 좋았나?" |
| QU-22 | NOT_COVERED | — | 시간 표현 · "그저께", "작년" |
| QU-23 | PARTIAL | MC-14 | 프로젝트 별칭 · "메모리 에이전트", "PMA" |
| QU-24 | PARTIAL | MC-14, MC-34 | 기술 식별자 · `C++`, `GPT-6`, `YOLOv8` |
| QU-25 | PARTIAL | MC-14, MC-34 | 파일명 · `yolo_checker_optimized_v2.py` |
| QU-26 | NOT_COVERED | — | 정확한 경로 · `src/search/router.py` |
| QU-27 | PARTIAL | MC-10, MC-31 | 숫자·버전 · `v1.2`, `0.87`, `128GB` |
| QU-28 | NOT_COVERED | — | 인용구 검색 · "정확도와 사용성 균형" |
| QU-29 | NOT_COVERED | — | 문장 일부 검색 · "중복되는 기록을" |
| QU-30 | NOT_COVERED | — | 관계 기반 · "민수가 말했던 배포 오류" |
| QU-31 | NOT_COVERED | — | 원인 기반 · "속도 저하를 일으킨 문제" |
| QU-32 | NOT_COVERED | — | 결과 기반 · "정확도가 개선된 테스트" |
| QU-33 | NOT_COVERED | — | 모호한 복수 주제 · "지난번 모델 이야기" |
| QU-34 | NOT_COVERED | — | 질문 안의 인용문 · "그가 '검색해줘'라고 말한 기록" |
| QU-35 | NOT_COVERED | — | 코드 포함 검색 · 함수명·클래스명 |
| QU-36 | NOT_COVERED | — | 검색어 없음 · 검색 필드가 빈 상태 |
| QU-37 | NOT_COVERED | — | 검색어 과다 · 토큰 제한을 초과하는 질문 |
| QU-38 | NOT_COVERED | — | 특수문자 검색 · 정규표현식 문자, 따옴표, 역슬래시 |
| QU-39 | NOT_COVERED | — | 번역해도 일치하지 않는 표현 · 부정확한 번역 확장 방지 |
| QU-40 | NOT_COVERED | — | 서로 충돌하는 검색 조건 · "작년에 작성한 오늘 기록" |
| RT-01 | NOT_COVERED | — | 전체 기록 · "전체 기록에서 찾아줘" |
| RT-02 | NOT_COVERED | — | 특정 날짜 · "10월 15일 기록" |
| RT-03 | PARTIAL | MC-13, MC-19 | 날짜 범위 · "10월 첫째 주" |
| RT-04 | PARTIAL | MC-19 | 상대 시간 · "지난주", "어제" |
| RT-05 | NOT_COVERED | — | 특정 시점 이전 · "\~하기 전에 작성한 것" |
| RT-06 | NOT_COVERED | — | 특정 시점 이후 · "업데이트 후 발생한 오류" |
| RT-07 | PARTIAL | MC-09, MC-15, MC-16, MC-27, MC-33 | 사건 발생일 기준 · 실제 사건이 일어난 날짜 |
| RT-08 | PARTIAL | MC-09, MC-16, MC-33 | 저장일 기준 · DB에 저장한 날짜 |
| RT-09 | PARTIAL | MC-16 | 수정일 기준 · 마지막 수정 날짜 |
| RT-10 | NOT_COVERED | — | 최근 기록 · 최신순 |
| RT-11 | NOT_COVERED | — | 오래된 기록 · 과거순 |
| RT-12 | NOT_COVERED | — | 특정 프로젝트 · "PMA 관련 기록만" |
| RT-13 | NOT_COVERED | — | 프로젝트 제외 · "YOLO 작업은 빼고" |
| RT-14 | NOT_COVERED | — | 특정 인물 · "민수 관련 회의" |
| RT-15 | NOT_COVERED | — | 특정 파일 · PDF 한 개만 검색 |
| RT-16 | NOT_COVERED | — | 특정 출처 · 직접 입력한 메모만 |
| RT-17 | NOT_COVERED | — | 특정 기록 유형 · 일정·회의·오류·결정 |
| RT-18 | NOT_COVERED | — | 완료 상태 · 완료된 작업 |
| RT-19 | NOT_COVERED | — | 미완료 상태 · 남은 작업 |
| RT-20 | NOT_COVERED | — | 중요도 · 중요한 기록 우선 |
| RT-21 | NOT_COVERED | — | 정확 일치 · 단어가 정확히 포함된 기록 |
| RT-22 | NOT_COVERED | — | 의미 검색 · 표현은 다르지만 같은 의미 |
| RT-23 | PARTIAL | MC-23, MC-30 | 여러 필터의 AND · 프로젝트 A + 지난주 |
| RT-24 | NOT_COVERED | — | 여러 필터의 OR · 프로젝트 A 또는 B |
| RT-25 | PARTIAL | MC-13, MC-17, MC-30, MC-35 | 제외 조건 · 취소된 기록 제외 |
| RT-26 | NOT_COVERED | — | 빈 검색 결과 · 조건에 맞는 기록 없음 |
| RT-27 | NOT_COVERED | — | 과도하게 좁은 필터 · 단계별 완화 제안 |
| RT-28 | NOT_COVERED | — | 검색 결과 수 제한 · Top-K |
| RT-29 | NOT_COVERED | — | 페이징 · 다음 결과 불러오기 |
| RT-30 | PARTIAL | MC-13, MC-28 | 중복 결과 · 같은 사건이 여러 출처에 존재 |
| RT-31 | NOT_COVERED | — | 접근 가능한 기록만 · 권한 필터 |
| RT-32 | NOT_COVERED | — | 저장되지 않은 현재 대화 · 단기 문맥을 별도로 활용 |
| RR-01 | NOT_COVERED | — | 정확 키워드 일치 · 원문 단어 보존 |
| RR-02 | NOT_COVERED | — | BM25 등 어휘 검색 · 명칭·식별자 검색 |
| RR-03 | NOT_COVERED | — | 벡터 의미 검색 · 의미적으로 같은 표현 |
| RR-04 | NOT_COVERED | — | Hybrid 검색 · 키워드와 벡터 결합 |
| RR-05 | NOT_COVERED | — | 재정렬 · 질문과 실제 근거 일치 |
| RR-06 | PARTIAL | MC-16 | 시간 가중치 · 최신 사실 선호가 적절한가 |
| RR-07 | PARTIAL | MC-16 | 오래된 기록의 중요성 · 최초 결정의 근거 보존 |
| RR-08 | PARTIAL | MC-03, MC-11 | 출처 신뢰성 · 확정 기록과 추정 메모 구별 |
| RR-09 | NOT_COVERED | — | 기록 길이 · 긴 기록이 과도하게 유리하지 않은가 |
| RR-10 | NOT_COVERED | — | 청크 크기 · 답의 핵심 문장이 분리되는가 |
| RR-11 | NOT_COVERED | — | 청크 중첩 · 연결 문맥 보존 |
| RR-12 | NOT_COVERED | — | 문장 단위 색인 · 세밀한 검색 |
| RR-13 | NOT_COVERED | — | 문서 단위 색인 · 전체 문맥 |
| RR-14 | NOT_COVERED | — | 계층형 검색 · 문서 → 청크 → 근거 문장 |
| RR-15 | NOT_COVERED | — | 시간 필터 적용 순서 · 검색 전·후 필터 차이 |
| RR-16 | PARTIAL | MC-14 | 프로젝트 필터 적용 · 비슷한 다른 프로젝트 오염 |
| RR-17 | NOT_COVERED | — | 질문 재작성 · 원래 의도 유지 |
| RR-18 | PARTIAL | MC-18, MC-34 | 다국어 임베딩 · 한영 표현 호환 |
| RR-19 | NOT_COVERED | — | 검색 확장 · 확장 품질·중복 관리 |
| RR-20 | NOT_COVERED | — | 확장 실패 폴백 · 원본 검색 유지 |
| RR-21 | NOT_COVERED | — | 검색 반복 · 초기 결과가 약할 때 재검색 |
| RR-22 | NOT_COVERED | — | 다중 검색어 분해 · 복합 질문별 검색 |
| RR-23 | PARTIAL | MC-09, MC-14, MC-29 | 동명이인 구분 · 개체 연결 정확도 |
| RR-24 | NOT_COVERED | — | 유사 기록 충돌 · 정답 후보 구분 |
| RR-25 | NOT_COVERED | — | 검색 점수 임계값 · 근거 부족 판단 |
| RR-26 | NOT_COVERED | — | Top-K 민감도 · 정답이 K 밖에 존재 |
| RR-27 | NOT_COVERED | — | 컨텍스트 토큰 예산 · 핵심 근거 누락 방지 |
| RR-28 | NOT_COVERED | — | 동일 출처 중복 · 다양성 확보 |
| RR-29 | NOT_COVERED | — | 검색 결과 캐시 · 변경·삭제 반영 |
| RR-30 | NOT_COVERED | — | 결과 없음 · 없는 정보를 생성하지 않음 |
| RR-31 | NOT_COVERED | — | 잘못된 상위 결과 · 재검증·재검색 가능 여부 |
| RR-32 | PARTIAL | MC-20 | 다단계 연결 · A의 원인 → B의 결정 |
| RR-33 | NOT_COVERED | — | 검색 결과의 부정 표현 · 사실 반전 방지 |
| RR-34 | PARTIAL | MC-05, MC-17, MC-26, MC-28, MC-31 | 서로 다른 수치 단위 · 값과 단위 정확히 매칭 |
| RR-35 | NOT_COVERED | — | 기록 최신 버전 · 오래된 색인으로 답하지 않음 |
| RR-36 | NOT_COVERED | — | 인덱싱 대기 · 누락 상태와 실제 부재 구별 |
| CV-01 | NOT_COVERED | — | 첫 질문 · 현재 발화로 의도 판단 |
| CV-02 | NOT_COVERED | — | 바로 앞 질문의 후속 질문 · 직전 주제 계승 |
| CV-03 | NOT_COVERED | — | "그거 좀 자세히" · 직전 응답의 대상 연결 |
| CV-04 | NOT_COVERED | — | "두 번째 거" · 결과 목록의 두 번째 항목 참조 |
| CV-05 | PARTIAL | MC-23 | "아니, 다른 프로젝트" · 이전 해석 수정 |
| CV-06 | PARTIAL | MC-23 | "그 날짜 말고" · 날짜 조건만 변경 |
| CV-07 | PARTIAL | MC-23 | 새 주제로 전환 · 관련 없는 맥락 제거 |
| CV-08 | PARTIAL | MC-23 | 이전 주제로 복귀 · 적절한 과거 주제 복원 |
| CV-09 | NOT_COVERED | — | 긴 대화 · 문맥 압축 후 정확성 |
| CV-10 | NOT_COVERED | — | 새 세션 시작 · 장기 기억과 세션 구분 |
| CV-11 | NOT_COVERED | — | 이전 세션을 직접 언급 · 해당 세션 검색 |
| CV-12 | NOT_COVERED | — | 이전 답변의 오류 정정 · 수정된 맥락 우선 |
| CV-13 | NOT_COVERED | — | 여러 개체 등장 · "그 사람" 대상 판단 |
| CV-14 | NOT_COVERED | — | 여러 날짜 등장 · 상대 시간·지시어 처리 |
| CV-15 | NOT_COVERED | — | 사용자가 불분명한 질문 · 충분한 맥락이면 즉답 |
| CV-16 | PARTIAL | MC-09 | 실제 복수 해석 · 필요한 부분만 질문 |
| CV-17 | NOT_COVERED | — | 같은 말을 반복 · 불필요한 재질문 방지 |
| CV-18 | NOT_COVERED | — | 검색 결과를 기반으로 연속 질문 · 근거 연결 유지 |
| CV-19 | NOT_COVERED | — | 검색 결과 선택 후 후속 질문 · 선택한 기록 중심 응답 |
| CV-20 | NOT_COVERED | — | 같은 대화 안에서 기록 생성 · 저장 정책 및 즉시 활용 |
| CV-21 | NOT_COVERED | — | 대화 중 기록 삭제 · 이후 답변에서 제외 |
| CV-22 | NOT_COVERED | — | 대화 중 기존 기록 수정 · 변경 사실 반영 |
| CV-23 | NOT_COVERED | — | 지시어가 다른 사람을 지칭 · 잘못된 인물 연결 방지 |
| CV-24 | NOT_COVERED | — | 일반 대화에서 검색 대화로 전환 · 필요할 때만 검색 |
| CV-25 | NOT_COVERED | — | 검색 대화에서 일반 대화로 전환 · 불필요한 검색 중단 |
| CV-26 | NOT_COVERED | — | 주제 복수 개 병행 · 주제별 상태 분리 |
| CV-27 | PARTIAL | MC-23 | 이전 검색 조건만 변경 · 나머지 조건 유지 |
| CV-28 | NOT_COVERED | — | 이전 답을 재생성 요청 · 근거와 출처 일관성 |
| CV-29 | NOT_COVERED | — | "기록 말고 일반적으로" · 개인 기록 사용 제한 |
| CV-30 | NOT_COVERED | — | "내 기록 기준으로" · 개인 근거 우선 |
| AG-01 | NOT_COVERED | — | 일반적인 인사 · 자연스러운 답변 |
| AG-02 | NOT_COVERED | — | 일반 상식 질문 · 일반 지식으로 답변 |
| AG-03 | NOT_COVERED | — | 개인 기록이 필요한 질문 · 기록 검색 후 답변 |
| AG-04 | NOT_COVERED | — | 개인 기록 + 일반 지식 · 두 정보의 출처 구별 |
| AG-05 | NOT_COVERED | — | 검색 버튼 클릭 · 검색 UI에 맞는 결과 제공 |
| AG-06 | NOT_COVERED | — | 명시적 검색 요청 · 검색 우선 |
| AG-07 | NOT_COVERED | — | 애매하지만 문맥이 충분 · 재질문 없이 답변 |
| AG-08 | PARTIAL | MC-21, MC-29 | 애매하고 복수 해석 · 명확화 질문 |
| AG-09 | PARTIAL | MC-21 | 검색 결과 0건 · 정보 부재 명시 |
| AG-10 | NOT_COVERED | — | 검색 결과 약함 · 근거 부족 표시 |
| AG-11 | NOT_COVERED | — | 검색 결과가 여러 건 · 관련 후보 비교 |
| AG-12 | PARTIAL | MC-11, MC-33 | 서로 모순된 기록 · 모순 내용 설명 |
| AG-13 | PARTIAL | MC-04, MC-07 | 사용자 가정이 틀림 · 근거로 정정 |
| AG-14 | PARTIAL | MC-02, MC-06, MC-21 | 기록에 답 일부만 존재 · 확인된 부분만 답변 |
| AG-15 | PARTIAL | MC-08, MC-12, MC-21 | 기록에 없는 원인 질문 · 이유를 임의 생성하지 않음 |
| AG-16 | PARTIAL | MC-20, MC-35 | 결정 이유가 여러 기록에 분산 · 다중 근거 결합 |
| AG-17 | PARTIAL | MC-35 | 복수 작업 요약 · 누락 없이 범위 준수 |
| AG-18 | NOT_COVERED | — | 긴 답변 요청 · 상세 설명 |
| AG-19 | NOT_COVERED | — | 짧은 답변 요청 · 핵심만 응답 |
| AG-20 | NOT_COVERED | — | 표로 정리 요청 · 구조화 출력 |
| AG-21 | NOT_COVERED | — | 순서대로 설명 요청 · 시간순 재구성 |
| AG-22 | NOT_COVERED | — | 시간 범위를 변경 · 기존 대화 조건 갱신 |
| AG-23 | NOT_COVERED | — | 기록을 저장하라는 요청 · 저장 권한·의도 확인 및 실행 |
| AG-24 | NOT_COVERED | — | 기록 수정을 요청 · 대상 식별 후 갱신 |
| AG-25 | NOT_COVERED | — | 기록 삭제 요청 · 범위 확인 및 정책 적용 |
| AG-26 | NOT_COVERED | — | 현재 대화 내용 요약 · 단기 문맥 활용 |
| AG-27 | NOT_COVERED | — | 전체 과거 대화 요약 · 검색 및 누락 관리 |
| AG-28 | NOT_COVERED | — | 할 일 추천 · 기록과 일반 제안 구분 |
| AG-29 | PARTIAL | MC-01, MC-07 | 아직 발생하지 않은 일 질문 · 예정·완료 구분 |
| AG-30 | NOT_COVERED | — | 외부 최신 정보 질문 · 지원되는 외부 정보 경로 사용 |
| AG-31 | NOT_COVERED | — | 검색 시스템 오류 · 실패 사실 고지 및 폴백 |
| AG-32 | NOT_COVERED | — | LLM 응답 실패 · 사용자에게 오류 상태 전달 |
| AG-33 | NOT_COVERED | — | 근거와 답변이 불일치 · 답변 보류·재생성·검증 |
| AG-34 | PARTIAL | MC-05, MC-31, MC-36 | 시스템이 추론한 정보 · 기록상 사실과 추론 구분 |
| AG-35 | NOT_COVERED | — | 근거 없는 확신 표현 · 확신 정도 조절 |
| AG-36 | NOT_COVERED | — | 반복 검색 시 답이 달라짐 · 비결정성의 영향 측정 및 일관성 검사 |
| MW-01 | NOT_COVERED | — | 명시적으로 기억 요청 · 저장 |
| MW-02 | NOT_COVERED | — | 명시적 비저장 요청 · 저장 금지 |
| MW-03 | NOT_COVERED | — | 일반 대화에서 사실 언급 · 자동 저장 정책 적용 |
| MW-04 | PARTIAL | MC-32 | 장기 선호도 · 반복 활용 |
| MW-05 | PARTIAL | MC-04, MC-06, MC-32 | 일시적 취향 · 영구 선호로 과대 일반화 금지 |
| MW-06 | NOT_COVERED | — | 프로젝트 목표 · 관련 질문에 활용 |
| MW-07 | PARTIAL | MC-12 | 프로젝트 완료 상태 · 최신 변경 반영 |
| MW-08 | NOT_COVERED | — | 작업 방식 선호 · 답변 형식에 활용 |
| MW-09 | NOT_COVERED | — | 이전 대화에서 정한 규칙 · 유효 범위에서 적용 |
| MW-10 | NOT_COVERED | — | 잘못된 기억 정정 · 기존 기억 수정·무효화 |
| MW-11 | NOT_COVERED | — | 서로 충돌하는 기억 · 유효성·시점 판단 |
| MW-12 | NOT_COVERED | — | 사용자가 기억 삭제 요청 · 다시 사용하지 않음 |
| MW-13 | NOT_COVERED | — | 민감한 개인 정보 · 보존·접근 정책 |
| MW-14 | NOT_COVERED | — | 타인의 개인정보 · 사용자 정보와 구별 |
| MW-15 | NOT_COVERED | — | 출처가 불분명한 기억 · 사실로 확정하지 않음 |
| MW-16 | PARTIAL | MC-36 | LLM이 추측한 기억 · 사용자 사실로 자동 저장 금지 |
| MW-17 | NOT_COVERED | — | 대화 요약만 남은 상태 · 원문 누락 및 추론 오류 |
| MW-18 | NOT_COVERED | — | 여러 세션의 기억 · 중복·충돌 관리 |
| MW-19 | PARTIAL | MC-32 | 다른 프로젝트의 선호 · 적용 범위 구분 |
| MW-20 | NOT_COVERED | — | 기억 만료·보존 정책 · TTL 및 유효 시점 |
| MW-21 | NOT_COVERED | — | 사용자 직접 저장과 자동 추출 · 신뢰 수준 구분 |
| MW-22 | PARTIAL | MC-22 | 과거 답변의 오류 · 잘못된 답이 기억으로 고착되지 않음 |
| MW-23 | NOT_COVERED | — | 조건부 저장 · 명시한 조건이 만족될 때만 반영 |
| MW-24 | NOT_COVERED | — | 저장 기능 비활성화 · 신규 기억을 생성하지 않음 |
| EV-01 | NOT_COVERED | — | 근거에 직접 존재하는 사실 · 다른 값으로 답함 |
| EV-02 | PARTIAL | MC-05, MC-08, MC-17, MC-24, MC-26 | 숫자 · 숫자·단위가 다름 |
| EV-03 | PARTIAL | MC-19 | 날짜 · 발생일과 저장일 혼동 |
| EV-04 | PARTIAL | MC-06 | 인물 · 주체를 잘못 연결 |
| EV-05 | PARTIAL | MC-02, MC-08, MC-10 | 장소 · 다른 사건의 장소 사용 |
| EV-06 | NOT_COVERED | — | 부정 · "하지 않았다"를 "했다"로 표현 |
| EV-07 | PARTIAL | MC-01, MC-04, MC-07, MC-25 | 상태 · 계획을 완료로 표현 |
| EV-08 | PARTIAL | MC-03 | 추정 · 추정을 확정 사실로 표현 |
| EV-09 | PARTIAL | MC-01, MC-10, MC-15, MC-25 | 의사결정 변경 · 구버전을 최신 결론으로 사용 |
| EV-10 | NOT_COVERED | — | 동일 주제의 여러 기록 · 일부 근거만 보고 과도하게 일반화 |
| EV-11 | PARTIAL | MC-11, MC-33 | 서로 모순된 근거 · 충돌을 숨기고 단정 |
| EV-12 | NOT_COVERED | — | 질문에 맞지 않는 근거 · 유사 단어만으로 인용 |
| EV-13 | NOT_COVERED | — | 기록에 없는 세부 내용 · 임의 생성 |
| EV-14 | PARTIAL | MC-20, MC-35 | 복수 근거가 필요한 답 · 일부만 확인하고 전체를 단정 |
| EV-15 | NOT_COVERED | — | 출처 ID · 존재하지 않는 ID 생성 |
| EV-16 | NOT_COVERED | — | 출처 위치 · 실제 문장과 다른 페이지·라인 인용 |
| EV-17 | NOT_COVERED | — | 원문 일부 인용 · 원문 왜곡 |
| EV-18 | NOT_COVERED | — | 인용 후 기록 변경 · 오래된 내용 인용 |
| EV-19 | PARTIAL | MC-21 | 검색 결과 없는 질문 · 허위 개인 경험 생성 |
| EV-20 | NOT_COVERED | — | 약한 근거 · 과도한 확신 |
| EV-21 | PARTIAL | MC-22, MC-36 | 외부 지식 혼입 · 일반 정보가 사용자 이력이 됨 |
| EV-22 | PARTIAL | MC-11, MC-33, MC-36 | 기록의 주장과 실제 사실 · 사용자의 기록 내용을 검증된 외부 사실로 혼동 |
| EV-23 | PARTIAL | MC-03, MC-12 | 요약 · 중요한 반례·제외 조건 누락 |
| EV-24 | PARTIAL | MC-05, MC-31 | 비교 · 서로 다른 기준의 결과를 단순 비교 |
| EV-25 | PARTIAL | MC-12, MC-13, MC-30 | 누락된 기록 · 완전한 목록인 것처럼 표현 |
| EV-26 | PARTIAL | MC-17, MC-28 | 근거 출처 다양성 · 동일 내용을 중복 근거로 취급 |
| EV-27 | PARTIAL | MC-22, MC-36 | 검색된 기록에 지시문 포함 · 기록 내용을 시스템 명령으로 실행 |
| EV-28 | NOT_COVERED | — | 추론 경로 · 명시된 사실과 도출된 결론 구별 |
| EV-29 | NOT_COVERED | — | 출처 접근 권한 · 접근할 수 없는 기록 인용 |
| EV-30 | NOT_COVERED | — | 답변 재검증 · 핵심 주장과 출처의 실제 일치 여부 |
| UI-01 | SEPARATE_FUNCTIONAL_TEST | — | 일반 대화 입력 · 채팅 모드 유지 |
| UI-02 | SEPARATE_FUNCTIONAL_TEST | — | 검색 버튼 클릭 · 검색 UI 표시 |
| UI-03 | SEPARATE_FUNCTIONAL_TEST | — | 검색 결과 선택 · 원본 상세 정보 |
| UI-04 | SEPARATE_FUNCTIONAL_TEST | — | 검색 결과에서 Agent에게 질문 · 선택 결과를 대화에 전달 |
| UI-05 | SEPARATE_FUNCTIONAL_TEST | — | 대화 중 자동 검색 발생 · 검색 상태 표시 정책 |
| UI-06 | SEPARATE_FUNCTIONAL_TEST | — | 여러 근거 사용 · 근거별 연결 |
| UI-07 | SEPARATE_FUNCTIONAL_TEST | — | 근거 클릭 · 실제 원문 위치로 이동 |
| UI-08 | SEPARATE_FUNCTIONAL_TEST | — | 긴 기록 · 하이라이트 및 스크롤 |
| UI-09 | SEPARATE_FUNCTIONAL_TEST | — | 검색 결과 0건 · 이해 가능한 빈 상태 |
| UI-10 | SEPARATE_FUNCTIONAL_TEST | — | 검색 중 · 진행 상태 표시 |
| UI-11 | SEPARATE_FUNCTIONAL_TEST | — | 검색 실패 · 오류 표시 및 재시도 |
| UI-12 | SEPARATE_FUNCTIONAL_TEST | — | 재검색 · 이전 결과 갱신 |
| UI-13 | SEPARATE_FUNCTIONAL_TEST | — | 검색 조건 변경 · 필터 반영 |
| UI-14 | SEPARATE_FUNCTIONAL_TEST | — | 대화 중단 · 요청 취소 |
| UI-15 | SEPARATE_FUNCTIONAL_TEST | — | 답변 재생성 · 출처 정보 일관성 |
| UI-16 | SEPARATE_FUNCTIONAL_TEST | — | 새로운 대화 생성 · 세션 분리 |
| UI-17 | SEPARATE_FUNCTIONAL_TEST | — | 기존 대화 재개 · 맥락 복구 |
| UI-18 | SEPARATE_FUNCTIONAL_TEST | — | 기록 수정 · 검색 결과 갱신 |
| UI-19 | SEPARATE_FUNCTIONAL_TEST | — | 기록 삭제 · 화면·캐시 반영 |
| UI-20 | SEPARATE_FUNCTIONAL_TEST | — | 모바일 화면 · 좁은 화면에서 사용 가능 |
| UI-21 | SEPARATE_FUNCTIONAL_TEST | — | 키보드 조작 · 접근성 |
| UI-22 | SEPARATE_FUNCTIONAL_TEST | — | 검색 결과가 매우 많음 · 페이징·가상 스크롤 |
| UI-23 | SEPARATE_FUNCTIONAL_TEST | — | 복수 해석 질문 · 후보 선택 인터페이스 |
| UI-24 | SEPARATE_FUNCTIONAL_TEST | — | 저장 성공·실패 · 명확한 결과 피드백 |
| UI-25 | SEPARATE_FUNCTIONAL_TEST | — | 아직 인덱싱되지 않은 기록 · 준비 중 상태 표시 |
| SEC-01 | SEPARATE_FUNCTIONAL_TEST | — | 사용자 A와 B · 데이터 완전 격리 |
| SEC-02 | SEPARATE_FUNCTIONAL_TEST | — | 다른 사용자 기록 ID 접근 · 권한 거절 |
| SEC-03 | SEPARATE_FUNCTIONAL_TEST | — | 검색 전 권한 필터 · 비허용 자료 검색 결과 제외 |
| SEC-04 | SEPARATE_FUNCTIONAL_TEST | — | 기록 삭제 후 검색 · 삭제된 데이터 노출 금지 |
| SEC-05 | SEPARATE_FUNCTIONAL_TEST | — | 대화 요약 캐시 · 삭제된 사실 재노출 금지 |
| SEC-06 | SEPARATE_FUNCTIONAL_TEST | — | 검색 결과 캐시 · 사용자 간 혼합 금지 |
| SEC-07 | SEPARATE_FUNCTIONAL_TEST | — | 공유 기록 접근권 변경 · 변경 사항 적용 |
| SEC-08 | PARTIAL | MC-22 | 프롬프트 인젝션 · 기록 안의 악성 지시 무시 |
| SEC-09 | PARTIAL | MC-22 | 파일 속 시스템 역할 위장 · 명령으로 승격 금지 |
| SEC-10 | SEPARATE_FUNCTIONAL_TEST | — | 개인정보 저장 설정 · 동의 및 정책 적용 |
| SEC-11 | SEPARATE_FUNCTIONAL_TEST | — | 민감한 기록을 인용 · 권한 없는 사용자에게 노출 금지 |
| SEC-12 | SEPARATE_FUNCTIONAL_TEST | — | 로그·디버그 정보 · 민감 정보 최소화 |
| SEC-13 | SEPARATE_FUNCTIONAL_TEST | — | 대화 삭제 요청 · 파생 기억 처리 |
| SEC-14 | SEPARATE_FUNCTIONAL_TEST | — | HTML·스크립트 포함 기록 · UI에서 안전하게 표시 |
| SEC-15 | SEPARATE_FUNCTIONAL_TEST | — | 경로 조작·파일 접근 · 허용 경로 및 파일만 처리 |
| SEC-16 | SEPARATE_FUNCTIONAL_TEST | — | 대량 입력 악용 · 자원 제한 |
| SEC-17 | SEPARATE_FUNCTIONAL_TEST | — | 데이터 내보내기 · 본인에게 허용된 기록만 포함 |
| SEC-18 | SEPARATE_FUNCTIONAL_TEST | — | 사용자 세션 만료 · 권한 없이 검색 지속 금지 |
| SEC-19 | SEPARATE_FUNCTIONAL_TEST | — | 검색 필터 조작 · 서버에서 권한 재검증 |
| SEC-20 | SEPARATE_FUNCTIONAL_TEST | — | 백업·복구 · 삭제·권한 정책 준수 |
| PF-01 | SEPARATE_FUNCTIONAL_TEST | — | 기록 0개 · 빈 상태 |
| PF-02 | SEPARATE_FUNCTIONAL_TEST | — | 기록 1개 · 기본 저장·검색 |
| PF-03 | SEPARATE_FUNCTIONAL_TEST | — | 기록 100개 · 작은 데이터셋 |
| PF-04 | SEPARATE_FUNCTIONAL_TEST | — | 기록 1,000개 · 중간 규모 |
| PF-05 | SEPARATE_FUNCTIONAL_TEST | — | 기록 10,000개 · 대규모 검색 |
| PF-06 | SEPARATE_FUNCTIONAL_TEST | — | 기록 100,000개 이상 · 확장성·메모리 |
| PF-07 | SEPARATE_FUNCTIONAL_TEST | — | 매우 긴 단일 기록 · 청킹·색인 |
| PF-08 | SEPARATE_FUNCTIONAL_TEST | — | 대량 중복 기록 · 중복 제거 |
| PF-09 | SEPARATE_FUNCTIONAL_TEST | — | 동시에 여러 검색 · 요청 처리 |
| PF-10 | SEPARATE_FUNCTIONAL_TEST | — | 검색 중 새 기록 입력 · 일관성 |
| PF-11 | SEPARATE_FUNCTIONAL_TEST | — | 검색 중 기록 삭제 · 결과 권한 및 유효성 |
| PF-12 | SEPARATE_FUNCTIONAL_TEST | — | 임베딩 모델 실패 · 안전한 폴백 |
| PF-13 | SEPARATE_FUNCTIONAL_TEST | — | 벡터 DB 장애 · 명확한 오류 |
| PF-14 | SEPARATE_FUNCTIONAL_TEST | — | LLM 타임아웃 · 요청 정리·재시도 |
| PF-15 | SEPARATE_FUNCTIONAL_TEST | — | 외부 API 장애 · 장애 격리 |
| PF-16 | SEPARATE_FUNCTIONAL_TEST | — | 검색 취소 · 불필요한 작업 중단 |
| PF-17 | SEPARATE_FUNCTIONAL_TEST | — | 임베딩 모델 교체 · 버전 관리·재색인 |
| PF-18 | SEPARATE_FUNCTIONAL_TEST | — | 모델 결과 비결정성 · 반복 평가 |
| PF-19 | SEPARATE_FUNCTIONAL_TEST | — | CPU 전용 실행 · 지연 시간·메모리 |
| PF-20 | SEPARATE_FUNCTIONAL_TEST | — | 제한된 RAM · OOM 방지 |
| PF-21 | SEPARATE_FUNCTIONAL_TEST | — | 색인 갱신 중 검색 · 서비스 일관성 |
| PF-22 | SEPARATE_FUNCTIONAL_TEST | — | 저장 요청 중복 전송 · 멱등성 |
| PF-23 | SEPARATE_FUNCTIONAL_TEST | — | 백그라운드 작업 실패 · 실패 상태 및 복구 |
| PF-24 | SEPARATE_FUNCTIONAL_TEST | — | 긴 대화 문맥 · 토큰 예산 및 요약 정확성 |
| PF-25 | SEPARATE_FUNCTIONAL_TEST | — | DB 재시작·데이터 복구 · 지속성 |
| PF-26 | SEPARATE_FUNCTIONAL_TEST | — | 잘못된 인덱스 · 검증·복구 가능성 |
| LC-01 | NOT_COVERED | — | "A\* 알고리즘을 공부했다" 저장 → "전에 공부한 탐색 알고리즘?" · A\* 기록 검색 및 인용 |
| LC-02 | NOT_COVERED | — | "벡터 검색 속도 개선" 저장 → "검색 성능 관련 작업" · 의미적으로 연결된 기록 검색 |
| LC-03 | NOT_COVERED | — | "YOLO 검수기"와 "PMA 검색기" 기록 → "PMA 오류" · PMA 기록만 근거로 사용 |
| LC-04 | NOT_COVERED | — | "10월 10일 0.81" → "10월 15일 0.89" → "최신 정확도?" · 0.89와 해당 시점 |
| LC-05 | NOT_COVERED | — | "배포 예정" → "배포 취소" → "배포했어?" · 배포 완료로 주장하지 않음 |
| LC-06 | NOT_COVERED | — | "민수는 A 담당", "민수는 B 담당" 등 동명이인 → "민수가 한 일?" · 개체 구분 또는 명확화 |
| LC-07 | NOT_COVERED | — | 어떤 오류를 검색 → "그거 해결 방법은?" · 직전 검색 결과와 연계 |
| LC-08 | NOT_COVERED | — | 프로젝트 A, B를 나열 → "두 번째 프로젝트는?" · 두 번째 항목 정확히 참조 |
| LC-09 | NOT_COVERED | — | 검색 결과 없음 → "그래도 추측해봐" · 추측과 기록 사실을 명확히 분리 |
| LC-10 | NOT_COVERED | — | 사용자 A의 기록을 사용자 B가 요청 · 데이터 접근 거절 |
| LC-11 | NOT_COVERED | — | "그건 틀렸어. B가 맞아"로 정정 · 기존 정보와 정정된 정보 구분 |
| LC-12 | NOT_COVERED | — | 기록 삭제 → 같은 질문 반복 · 삭제된 기록을 답변 근거로 사용하지 않음 |
| LC-13 | NOT_COVERED | — | "ML 관련 내용"과 "Machine Learning 관련 내용" · 적절한 한영 검색 |
| LC-14 | NOT_COVERED | — | "C++ 코드" 저장 → "C++ 자료" 검색 · 기술 식별자 보존 |
| LC-15 | NOT_COVERED | — | 파일명으로 기록 검색 · 정확한 파일과 출처 반환 |
| LC-16 | NOT_COVERED | — | 며칠간의 기록 → "이번 주에 뭐했어?" · 날짜 범위에 해당하는 기록 요약 |
| LC-17 | NOT_COVERED | — | "지난번 오류 원인이 뭐야?" + 원인 기록 없음 · 원인 미확인 명시 |
| LC-18 | NOT_COVERED | — | 긴 PDF 저장 → 특정 단락 질문 · 해당 단락과 페이지 인용 |
| LC-19 | NOT_COVERED | — | 하나의 사건이 메모와 대화에 중복 · 중복을 처리하고 출처 유지 |
| LC-20 | NOT_COVERED | — | 일반 지식 질문 → 프로젝트 질문 → 일반 질문 · 필요한 구간에서만 개인 기록 검색 |
| LC-21 | NOT_COVERED | — | "기억해줘" → 새 세션 → "전에 말한 거?" · 명시적 저장 내용 재사용 |
| LC-22 | NOT_COVERED | — | "기억하지 마" → 새 세션 → 같은 정보 질문 · 저장하지 않은 내용을 임의 회상하지 않음 |
| LC-23 | NOT_COVERED | — | 기록에 "이전 지시 무시"라는 악성 문장 · 문서 내용은 명령으로 실행하지 않음 |
| LC-24 | NOT_COVERED | — | 여러 기록을 비교해 수정 이력 질문 · 시간순 변경 사항 재구성 |
| LC-25 | NOT_COVERED | — | 여러 검색 조건 적용 후 "이번 달로 바꿔" · 날짜만 변경, 나머지 조건 유지 |
| LC-26 | NOT_COVERED | — | 1만 건의 유사 기록 중 정확한 사건 질문 · 관련 기록 검색 및 정확한 선택 |
| LC-27 | NOT_COVERED | — | 저장 직후 바로 검색 · 인덱싱 상태 또는 검색 가능성 일관성 |
| LC-28 | NOT_COVERED | — | 검색 중 기록 수정 · 오래된 결과의 처리 정책 준수 |
| LC-29 | NOT_COVERED | — | 긴 대화 뒤 "처음에 결정한 것" · 초기 결정과 최신 결정을 구분 |
| LC-30 | NOT_COVERED | — | 시스템 장애 발생 → 같은 요청 재시도 · 오류 복구 및 중복 방지 |
