# 성능 관측 비교

동일 PC의 이미 실행 중인 Qwen3-8B/BGE-M3 서버를 재사용한 소규모 합성 측정이다. 부하·캐시·생성 편차가 있어 인과적인 성능 개선으로 해석하지 않는다.

| 항목 | 이전 실행 | 현재 실행 |
|---|---:|---:|
| baseline 색인 | 15.14s | 11.63s |
| correction 색인 | 11.71s | 11.28s |
| preference 색인 | 8.27s | 8.21s |
| proposal 색인 | 15.68s | 15.67s |
| project_decision 색인 | 16.07s | 16.02s |

후보 생성+승인 트랜잭션 30회: 평균 16.46ms, P95 17.52ms. 이전 평균 16.16ms/P95 16.95ms. 모델·색인은 제외한다.

의미 관계 검토 8회: 평균 4.78s, P95 5.92s(최근접 순위, 8개 표본에서는 최댓값). 실제 HTTP 14회(토큰 계산 포함), 검색 API 0회. 원문 중복 1개는 모델 호출 없이 검출했다.

저장·검색 통합 평가: 모델 gateway 18회, 실제 HTTP 40회, 검색 API 2회. GENERAL 메시지 내부의 별도 budget 호출은 바깥 budget과 분리되므로 40회를 전체 실행의 완전한 HTTP 총합으로 해석하지 않는다. 이를 보완한 최종 live-03 실행에서는 HTTP 요청 함수를 평가 프로세스 안에서 관측하여 **46회**를 확인했다.

RSS/GPU 관측(JSON 원자료):

```json
{
  "before": {
    "python_rss_bytes": 66015232,
    "python_peak_rss_bytes": 66932736,
    "gpu_total_used_mib": [
      7232
    ]
  },
  "after": {
    "python_rss_bytes": 69455872,
    "python_peak_rss_bytes": 69459968,
    "gpu_total_used_mib": [
      7232
    ]
  },
  "scope": "evaluation Python process RSS and whole GPU usage; warm shared servers"
}
```

원자료: output/memory-capture-live-01.json, memory-capture-live-02.json, memory-relations-live-01~03.json, memory-capture-benchmark-01~02.json. 출력 파일은 기존 파일을 덮어쓰지 않고 새 이름으로 작성한다.

최종 HTTP 관측 실행(live-03)의 자원: Python RSS 68,227,072 → 72,691,712 bytes(+4,464,640 bytes), 공유 GPU 전체 7,232 → 7,232 MiB. 이전 live-02 수치와 별도 실행이다.
