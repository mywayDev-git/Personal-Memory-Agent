import time
from ollama import chat
import extract_memory as em

diaries = [
    "오늘 팀원들과 캡스톤 회의를 했다.",
    "오늘 점심에 친구와 학식을 먹었다.",
    "오늘 도서관에서 과제를 했다.",
]
for i, d in enumerate(diaries, 1):
    r = chat(model=em.MODEL, messages=em.build_messages(d, "2026-10-10"), format="json",
             options={"temperature": 0, "num_ctx": 4096, "num_predict": 40}, keep_alive="30m")
    print(f"{i}번째: 새로 읽은 토큰 {r.prompt_eval_count}, "
          f"읽는 시간 {r.prompt_eval_duration / 1e9:.1f}초, 모델 로딩 {r.load_duration / 1e9:.1f}초")