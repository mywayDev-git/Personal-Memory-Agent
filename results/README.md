모델별 raw output과 summary JSON을 저장합니다. GGUF 파일명/양자화, llama.cpp 빌드, 컨텍스트 길이, GPU offload 설정을 함께 기록하세요.

### 1차 테스트
| 실패 유형      | 건수  | 확인된 현상                 |
| ---------- | --- | ---------------------- |
| 출력이 비어 있음  | 8건  | `raw_output`이 빈 문자열    |
| JSON 파싱 실패 | 5건  | JSON이 불완전하거나 문법 오류가 있음 |

### 2차 테스트
1. extraction_v1 → extraction_v2
2. `/no_think` 추가 X → O 