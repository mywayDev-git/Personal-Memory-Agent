param(
    [string]$OutputRoot = '.local/performance-20261019',
    [int]$Samples = 5,
    [string[]]$Scenarios = @('short_record', 'multi_chunk_record', 'search', 'memory_chat', 'concurrent'),
    [switch]$ConcurrentShort,
    [ValidateSet('auto', 'cpu', 'gpu')][string]$EmbeddingAcceleration = 'auto',
    [ValidateSet('cpu', 'gpu')][string[]]$Modes = @('gpu', 'cpu'),
    [ValidateRange(1, 3600)][int]$ModelTimeout = 180,
    [ValidateRange(0, 1024)][int]$Threads = 0,
    [switch]$NoWarmup
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
if (Test-Path -LiteralPath $OutputRoot) { throw 'Use a fresh output directory.' }
$null = New-Item -ItemType Directory -Path $OutputRoot
$originals = @(Get-CimInstance Win32_Process -Filter "Name = 'llama-server.exe'" |
    Where-Object { $_.CommandLine -match '--port (8081|8082)( |$)' } |
    Select-Object ProcessId, ExecutablePath, CommandLine)
$originals | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$OutputRoot/original-servers.json"
$gpuInfo = $null
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    try { $gpuInfo = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | Out-String).Trim() }
    catch { $gpuInfo = $null }
}
$runModes = $Modes
if ($Modes -contains 'gpu' -and $Modes -contains 'cpu') {
    $devices = & 'C:/llama.cpp/llama-server.exe' --list-devices 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $devices -notmatch '(?im)^\s*(CUDA|Vulkan|SYCL|Metal|ROCm|HIP)\d*\s*:') {
        $runModes = @('cpu')
    }
}
@{
    cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors)
    memory = @(Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory)
    gpu = $gpuInfo
    requested_modes = $Modes
    executed_modes = $runModes
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$OutputRoot/hardware.json"
$stopped = @()
try {
    foreach ($server in $originals) {
        Stop-Process -Id $server.ProcessId
        $stopped += $server
    }
    foreach ($mode in $runModes) {
        $benchmarkArgs = @('-u', '-m', 'evaluation.performance_benchmark', '--mode', $mode,
            '--output', "$OutputRoot/$mode", '--samples', "$Samples", '--scenarios') + $Scenarios
        if ($ConcurrentShort) { $benchmarkArgs += '--concurrent-short' }
        if ($EmbeddingAcceleration -ne 'auto') { $benchmarkArgs += @('--embedding-mode', $EmbeddingAcceleration) }
        $benchmarkArgs += @('--timeout', "$ModelTimeout")
        if ($Threads -gt 0) { $benchmarkArgs += @('--threads', "$Threads") }
        if ($NoWarmup) { $benchmarkArgs += '--no-warmup' }
        & './.venv/Scripts/python.exe' @benchmarkArgs
        if ($LASTEXITCODE -ne 0) { throw "Benchmark failed ($mode)." }
    }
} finally {
    foreach ($server in $stopped) {
        # Keep the exact original arguments; restore only the servers suspended here.
        $arguments = $server.CommandLine -replace '^"[^"]+"\s*', ''
        if ($arguments -eq $server.CommandLine) { throw 'Cannot safely parse original server command.' }
        $restored = Start-Process -FilePath $server.ExecutablePath -ArgumentList $arguments -WindowStyle Hidden -PassThru
        Write-Host "Restored original model server: $($restored.Id)"
    }
}
