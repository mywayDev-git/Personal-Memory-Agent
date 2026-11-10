# Personal-Memory-Agent

대학 캡스톤 I 프로젝트. 일기를 로컬에서 저장하고, 나중에 질문하면 관련 기억과 요약 근거를 보여줍니다.

## 시연 화면 실행

Windows에서 [Node.js 24 LTS](https://nodejs.org/en/download)와 [llama.cpp](https://github.com/ggml-org/llama.cpp/releases/)를 준비합니다. 백엔드는 `C:\llama.cpp\llama-server.exe`를 사용합니다. NVIDIA GPU가 있는 PC에서는 Windows x64 CUDA 실행 파일과 같은 릴리스의 CUDA DLL을 이 폴더에 둡니다. CPU로 실행할 때는 Windows x64 CPU 패키지를 사용합니다.

저장소가 없다면 PowerShell에서 시연 브랜치를 내려받습니다.

```powershell
git clone --single-branch --branch twins1909/event-graph-model-comparison-20261109 https://github.com/mywayDev-git/Personal-Memory-Agent.git Personal-Memory-Agent-demo
Set-Location .\Personal-Memory-Agent-demo
```

1. 저장소 루트에서 **백엔드**를 켭니다.

   ```powershell
   node server.cjs
   ```

2. [모델 준비 화면](http://127.0.0.1:4319/baseline)에서 생성 모델을 선택합니다. 처음이라면 **Qwen3.5 2B → 선택 모델 준비**를 눌러 생성 모델과 **Qwen3 Embedding 0.6B**의 다운로드 및 검증을 마칩니다. 기존 `.models` 폴더를 옮겼다면 모델을 다시 받을 필요는 없습니다. **모델 서버 켜기**로 미리 로드할 수 있습니다.
3. 새 PowerShell 창을 열고 같은 저장소 루트에서 **시연 프론트**를 켭니다.

   ```powershell
   node .\demo-frontend\serve.cjs
   ```

4. 두 창을 열어 둔 채 [시연 화면](http://127.0.0.1:4320/)에 접속합니다. 별도의 `npm install`이나 Python 환경이 필요하지 않습니다. 모델 평가를 실행 중이라면 평가가 끝난 뒤 시연하세요.

## 사색 대화와 감정 갈무리 확인

1. **서재 홈**에 `어제 민수와 도서관에서 발표 자료를 정리했다.`를 입력하고 **시작하기**를 누릅니다. **사색 대화**에서 **기록하기**를 누르면 저장됩니다.
2. `어제 민수와 어디서 발표 자료를 정리했어?`라고 물으면 해당 날짜의 기록을 바탕으로 답합니다. 사용한 요약 근거는 답변 아래에 표시됩니다.
3. `그거 언제였지?`처럼 대상이 빠진 질문에는 어떤 일을 말하는지 먼저 묻습니다. 사건 이름이나 날짜를 답하면 이어서 검색합니다.
4. **감정 갈무리**에서 감정을 고르고 `기분이 우울해서 학교 운동장을 산책했더니 마음이 한결 편해졌다.`를 저장합니다. **달력에서 보기**에서 기록일과 감정을 확인할 수 있습니다.
5. **사색 대화**에 `오늘 마음이 무거운데 어떻게 하면 좋을까?`라고 입력합니다. **기록하기** 또는 **기록 없이 답변**을 고르면 두세 문장으로 답합니다. 관련 기억이 있으면 답변 아래에 표시합니다.

날짜는 한국 시간(Asia/Seoul) 기준입니다. `8일에 뭐 했어?`는 이번 달 8일의 기록만 검색합니다. 일기는 입력에 날짜가 없으면 오늘로 저장합니다. 일정은 날짜가 빠지거나 시작 시각이 애매하면 사색 대화에서 한 번 더 묻습니다.

새 일기의 감정은 로컬 모델이 요약할 때 함께 판단해 **서재 보관소**에 표시합니다. 감정 단서가 없는 일기는 **단서 없음**으로 표시합니다. 기존 일기는 [요약 기억 관리](http://127.0.0.1:4319/summary)에서 **원본으로 다시 만들기**를 누르면 감정을 판단할 수 있습니다.

모델 파일은 로컬 `.models`에, 일기와 평가 기록은 로컬 `.local/baseline`에 저장합니다. 다른 PC에서 새 기록으로 시연하려면 모델 파일만 옮기거나 다시 준비하세요. 평가 워크벤치와 저장 방식에 대한 자세한 설명은 [BASELINE.md](BASELINE.md)를 참고하세요.
