param([string]$OutputRoot = '.local/native-real-models-20261019', [int]$Samples = 5, [int]$Records = 10000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Use a fresh output directory.' }
$metadata = "$OutputRoot-control"
$null = New-Item -ItemType Directory -Path $metadata
$originals = @(Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" |
    Where-Object { $_.CommandLine -match '--port (8081|8082)( |$)' } |
    Select-Object ProcessId, ExecutablePath, CommandLine)
$originals | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$metadata/original-models.json"
@{
 cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
 memory = @(Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory)
 gpu = (& nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader | Out-String).Trim()
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$metadata/hardware.json"
try {
    foreach ($server in $originals) { Stop-Process -Id $server.ProcessId }
    & './.venv/Scripts/python.exe' -u -m evaluation.native_real_models --output $OutputRoot --samples $Samples --records $Records
    if ($LASTEXITCODE -ne 0) { throw "Real-model comparison failed: $LASTEXITCODE" }
} finally {
    # Restore the originally observed GPU settings if the original processes have
    # already exited; otherwise use the exact current captured command lines.
    if ($originals.Count -eq 0) {
        $originals = @(
            @{ ExecutablePath='C:/llama.cpp/llama-server.exe'; CommandLine='"C:/llama.cpp/llama-server.exe" -m "C:/models/Qwen3-8B-Q4_K_M.gguf" --host 127.0.0.1 --port 8081 -c 16384 -np 1 --alias qwen3 --log-disable -ngl 99' },
            @{ ExecutablePath='C:/llama.cpp/llama-server.exe'; CommandLine='"C:/llama.cpp/llama-server.exe" -m "C:/models/bge-m3-Q8_0.gguf" --host 127.0.0.1 --port 8082 -c 8192 -b 8192 -ub 8192 --embedding --pooling cls --alias bge-m3 --log-disable -ngl 99' }
        )
    }
    foreach ($server in $originals) {
        $arguments = $server.CommandLine -replace '^"[^"]+"\s*', ''
        $null = Start-Process -FilePath $server.ExecutablePath -ArgumentList $arguments -WindowStyle Hidden -PassThru
    }
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    do {
        $ready = 0
        foreach ($port in @(8081,8082)) {
            try { if ((Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2 -NoProxy).status -eq 'ok') { $ready++ } } catch { }
        }
        if ($ready -eq 2) { break }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($ready -ne 2) { throw 'Restored model servers did not become ready.' }
    $env:PMA_EMBEDDING_REVISION = (Get-FileHash 'C:/models/bge-m3-Q8_0.gguf' -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:PMA_MODEL = 'qwen3'
    $env:PMA_CONTEXT_TOKENS = '16384'
    $env:PMA_KEYWORD_BACKEND = 'auto'
    $appEnv = '.local/native-real-app-env.json'
    if (Test-Path -LiteralPath $appEnv) {
        $saved = Get-Content -LiteralPath $appEnv -Raw | ConvertFrom-Json -AsHashtable
        foreach ($entry in $saved.GetEnumerator()) { [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process') }
        $env:PMA_KEYWORD_BACKEND = 'auto'
    }
    # User explicitly requested restarting the main app. Keep existing model
    # processes independent so stopping this probe does not stop those models.
    $existingApp = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8765 | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($appProcessId in $existingApp) {
        $appProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$appProcessId"
        if ($appProcess.CommandLine -notmatch '-m (pma|evaluation.app_native_probe)') { throw 'Port 8765 belongs to an unrelated process.' }
        Stop-Process -Id $appProcessId
    }
    $app = Start-Process -FilePath './.venv/Scripts/python.exe' -ArgumentList @('-u','-B','-m','evaluation.app_native_probe','--test') -WindowStyle Hidden -PassThru -RedirectStandardOutput "$metadata/app.stdout.log" -RedirectStandardError "$metadata/app.stderr.log"
    $app.Id | Set-Content -LiteralPath "$metadata/app.pid"
    Write-Host "Restored models; restarted app PID $($app.Id)."
}
