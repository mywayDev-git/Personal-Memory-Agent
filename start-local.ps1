$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Memory Lab 로컬 Baseline: http://127.0.0.1:4319/baseline'
Write-Host '화면을 열어도 모델 평가가 시작되지 않습니다. 테스트 실행은 화면 버튼으로 시작합니다.'
node --disable-warning=ExperimentalWarning server.cjs
