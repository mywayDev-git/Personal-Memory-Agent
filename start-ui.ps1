$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Plant Thought + Memory Lab UI: http://127.0.0.1:4330/'
Write-Host 'UI only. No model, database, API, or experiment is started.'
node .\ui\preview.cjs
