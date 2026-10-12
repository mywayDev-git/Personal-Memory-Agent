from ollama import chat
import extract_memory as em


def measure(msgs, num_ctx, fmt=None):
    r = chat(model=em.MODEL, messages=msgs, format=fmt,
             options={"temperature": 0, "num_ctx": num_ctx, "num_predict": 40})
    ptok = r.prompt_eval_count
    psec = r.prompt_eval_duration / 1e9
    print(f"num_ctx={num_ctx}: 프롬프트 {ptok}토큰, 읽는 데 {psec:.1f}초")
    if ptok >= num_ctx - 10:
        print("  주의: 프롬프트가 num_ctx를 거의 채움 -> 앞부분이 잘렸을 가능성")


print("[1] 현재 추출 프롬프트")
measure(em.build_messages("오늘 팀원들과 캡스톤 회의를 했다.", "2026-10-10"), 4096, "json")

print("\n[2] 기억 N개를 넣었을 때 (답변 생성 상황 가정)")
for n in (5, 20, 50):
    mems = "\n".join(
        f"[M{i}, 2026-09-{(i % 28) + 1:02d}] 캡스톤 회의에서 모델 선정 근거와 일정에 대해 "
        f"의견을 나누었고 다음 회의에서 결정하기로 함 (감정: 걱정)"
        for i in range(n))
    msgs = [{"role": "user", "content": f"{mems}\n\n질문: 모델 선정과 관련된 기억의 ID를 알려줘."}]
    print(f"기억 {n}개:", end=" ")
    measure(msgs, 16384)