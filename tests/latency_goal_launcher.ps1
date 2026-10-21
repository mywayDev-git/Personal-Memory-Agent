param([string]$Root, [string]$Scenario)
$ErrorActionPreference = 'Stop'
$global:latencyGoalStops = @()
$global:latencyGoalAttempts = @()
$global:latencyGoalModels = @(
    [pscustomobject]@{ProcessId=101; ExecutablePath='C:\llama.cpp\llama-server.exe'; CommandLine='"C:\llama.cpp\llama-server.exe" --port 8081'},
    [pscustomobject]@{ProcessId=102; ExecutablePath='C:\llama.cpp\llama-server.exe'; CommandLine='"C:\llama.cpp\llama-server.exe" --port 8082'}
)
function Get-CimInstance($ClassName, $Filter) {
    if ($Filter -match 'ProcessId = (\d+)') { return $global:latencyGoalModels | Where-Object ProcessId -eq ([int]$Matches[1]) }
    return $global:latencyGoalModels
}
function Stop-Process($Id) { $global:latencyGoalStops += $Id }
function Start-Process($FilePath, $ArgumentList, $WindowStyle, [switch]$PassThru) {
    $global:latencyGoalAttempts += $ArgumentList
    if ($WindowStyle -ne 'Hidden') { throw 'Unexpected visible server window.' }
    if ($Scenario -eq 'restore-first-failure' -and $global:latencyGoalAttempts.Count -eq 1) { throw 'injected restore failure' }
    return [pscustomobject]@{Id=(200 + $global:latencyGoalAttempts.Count)}
}
function Invoke-WebRequest($Uri, $TimeoutSec, [switch]$UseBasicParsing) {
    return [pscustomobject]@{StatusCode=200}
}
$launcher = Join-Path $Root 'scripts/run_latency_goal.ps1'
$python = Join-Path $Root 'fake-python.ps1'
if ($Scenario -eq 'plan') {
    & $launcher -Placement both -RunName 'test-plan' -PauseOrdinaryModels -PythonExe $python
    if ($global:latencyGoalStops.Count -or $global:latencyGoalAttempts.Count -or (Test-Path (Join-Path $Root '.local'))) {
        throw 'Plan mode mutated files or model processes.'
    }
} else {
    $failed = $false
    try {
        & $launcher -Placement cpu -RunName 'test-failure' -PauseOrdinaryModels -Execute -PythonExe $python
    } catch { $failed = $true; Write-Output $_.Exception.Message }
    if (-not $failed) { throw 'Injected measurement failure was hidden.' }
    if (($global:latencyGoalStops -join ',') -ne '101,102') { throw "Unexpected stopped process set: $($global:latencyGoalStops -join ',')" }
    if ($global:latencyGoalAttempts.Count -ne 2 -or $global:latencyGoalAttempts[0] -ne '--port 8081' -or $global:latencyGoalAttempts[1] -ne '--port 8082') {
        throw 'Both original model commands must be restored, including after one restore failure.'
    }
    $output = Join-Path $Root '.local/latency-goal/test-failure'
    if (-not (Test-Path (Join-Path $output 'ordinary-models-before.json'))) { throw 'Missing recovery snapshot.' }
    $errors = @(Get-Content (Join-Path $output 'ordinary-models-restore-errors.json') -Raw | ConvertFrom-Json)
    if ($Scenario -eq 'restore-first-failure' -and $errors.Count -ne 1) { throw 'Missing restoration failure report.' }
}
Write-Output 'latency goal launcher passed'

