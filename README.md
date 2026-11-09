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

## 일기와 기억 질문 확인

1. **서재 홈**의 입력 방식을 **자동 판단**으로 두고 `어제 민수와 도서관에서 캡스톤 발표 자료를 정리했다.`를 입력합니다.
2. **시작하기**를 누르면 모델이 기록을 요약하고 검색을 준비합니다. 저장 후 **서재 보관소**의 해당 날짜에서 일기를 확인할 수 있습니다.
3. **서재 홈**이나 **사색 대화**에서 `민수와 캡스톤 발표 자료를 어디서 정리했어?`라고 묻고 **최근 답변의 요약 근거 보기**를 펼칩니다.

자동 판단은 문장 표현을 사용합니다. 구분이 어려우면 **일기로 저장**이나 **기억에 질문**을 직접 고를 수 있습니다. 날짜를 직접 선택하면 그 날짜를 우선합니다. 그 외에는 일기 앞의 날짜나 `어제` 같은 표현을 사용하고, 날짜가 없으면 오늘로 저장합니다.

모델 파일은 로컬 `.models`에, 일기와 평가 기록은 로컬 `.local/baseline`에 저장합니다. 다른 PC에서 새 기록으로 시연하려면 모델 파일만 옮기거나 다시 준비하세요. 평가 워크벤치와 저장 방식에 대한 자세한 설명은 [BASELINE.md](BASELINE.md)를 참고하세요.
