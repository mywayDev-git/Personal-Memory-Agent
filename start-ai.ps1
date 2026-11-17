$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Plant Thought AI: http://127.0.0.1:4330/#chat'
Write-Host 'Uses the existing local AI server on port 4319. Start start-local.ps1 first if needed.'
node .\ui\connected.cjs
