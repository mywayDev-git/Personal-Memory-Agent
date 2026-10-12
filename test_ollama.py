import time
from ollama import chat

t = time.time()
stream = chat(
    model="qwen3:4b-instruct",
    messages=[{"role": "user", "content": "취업준비 때문에 불안한데, 뭐해야할까? 위로해줄래?"}],
    stream=True,
)
for chunk in stream:
    print(chunk.message.content or "", end="", flush=True)
    if chunk.done:
        speed = chunk.eval_count / (chunk.eval_duration / 1e9)
        print(f"\n생성 {chunk.eval_count}토큰, 속도 {speed:.1f} 토큰/초")
print(f"완료 ({time.time() - t:.1f}초)")