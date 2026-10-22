$ErrorActionPreference = 'Stop'
$repoRoot = 'C:\development\Personal-Memory-Agent'
$taskRoot = Join-Path $repoRoot '.local\latency-ten-second'
$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
$originals = Get-Content (Join-Path $taskRoot 'processes-before.json') -Raw | ConvertFrom-Json
$models = @($originals | Where-Object { $_.ExecutablePath -eq 'C:\llama.cpp\llama-server.exe' -and $_.CommandLine -match '--port 808[12]\b' })
if ($models.Count -ne 2) { throw 'Expected exactly the two recorded ordinary model servers.' }
$evaluationStatus = Get-Content (Join-Path $repoRoot '.local\main-suite\ui-f4a76ab2e0064599a666f86c60e8e78b\execution-status.json') -Raw | ConvertFrom-Json
if ($evaluationStatus.status -ne 'cancelled') { throw 'Wait for cooperative evaluation shutdown.' }
$stopped = @()
$restored = @()
try {
    foreach ($model in $models) {
        $live = Get-CimInstance Win32_Process -Filter "ProcessId = $($model.ProcessId)"
        if ($live.CommandLine -ne $model.CommandLine) { throw 'Recorded process identity changed; refusing to stop it.' }
        Stop-Process -Id $model.ProcessId
        $stopped += $model
    }
    Set-Location -LiteralPath $taskRoot
    foreach ($placement in @('gpu', 'cpu')) {
        $output = Join-Path $taskRoot ".local\ten-second-$placement-001"
        & $pythonExe -u -m evaluation.response_latency --output $output --placement $placement --threads 8 --embedding-batch 4096 --samples 5 --port 18581 --variants current candidate --candidate-options token_cache selection_cache prefix_on batch8 planning_compact --cases simple_search simple_answer stopped --fixed-anchor --reset-prompt-cache
        if ($LASTEXITCODE -ne 0) { throw "Latency experiment failed: $placement" }
        & $pythonExe -m evaluation.latency_bottlenecks (Join-Path $output 'results.json') --output (Join-Path $output 'bottlenecks.json')
        if ($LASTEXITCODE -ne 0) { throw "Stage report failed: $placement" }
    }
} finally {
    foreach ($model in $stopped) {
        $arguments = $model.CommandLine.Substring(('"' + $model.ExecutablePath + '"').Length).TrimStart()
        $process = Start-Process -FilePath $model.ExecutablePath -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $restored += @{ original_pid=$model.ProcessId; restored_pid=$process.Id; arguments=$arguments }
    }
    $restored | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $taskRoot 'restored-processes.json')
}
