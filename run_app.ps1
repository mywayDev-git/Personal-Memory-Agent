param(
    [string]$Server = 'C:\llama.cpp\llama-server.exe',
    [string]$GenerationModel = 'C:\models\Qwen3-8B-Q4_K_M.gguf',
    [string]$EmbeddingModel = 'C:\models\bge-m3-Q8_0.gguf',
    [ValidateSet('auto', 'cpu', 'gpu')][string]$Acceleration = 'auto',
    [ValidateSet('auto', 'cpu', 'gpu')][string]$EmbeddingAcceleration = 'auto',
    [ValidateRange(0, 1024)][int]$GenerationThreads = 0,
    [ValidateRange(0, 1024)][int]$EmbeddingThreads = 0,
    [ValidateSet('raw-v1', 'qwen3-retrieval-v1')][string]$EmbeddingProfile = 'raw-v1',
    [ValidateSet('auto', 'on', 'off')][string]$FlashAttention = 'auto',
    [switch]$NoBrowser,
    [switch]$ExternalServers,
    [switch]$Evaluation,
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 is required. Run: pwsh -File ./run_app.ps1'
}
Write-Host '[PMA] Starting Personal Memory Agent...'
if ($Evaluation) { $env:PMA_EVALUATION = '1' }
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    throw 'Run uv sync --frozen --python 3.14 first.'
}
$ownedProcesses = @()
function Wait-Model([int]$Port, $Process) {
    $started = [DateTime]::UtcNow
    $nextStatus = $started
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) { throw "Model server on port $Port exited (code $($Process.ExitCode))." }
        if ([DateTime]::UtcNow -ge $nextStatus) {
            $elapsed = [int]([DateTime]::UtcNow - $started).TotalSeconds
            Write-Host "[PMA] Loading model on port $Port... ${elapsed}s elapsed (timeout: 300s)."
            $nextStatus = [DateTime]::UtcNow.AddSeconds(10)
        }
        try {
            $health = Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 2 -NoProxy
            if ($health.StatusCode -eq 200) {
                Write-Host "[PMA] Model on port $Port is ready."
                return
            }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "Model server on port $Port did not become ready."
}
function Start-ModelServers {
    param($Server, $GenerationModel, $EmbeddingModel, $Acceleration, $GenerationThreads, $EmbeddingThreads, $EmbeddingAcceleration = 'auto', $EmbeddingProfile = 'raw-v1', $FlashAttention = 'auto')
    $modes = @($Acceleration)
    if ($Acceleration -ne 'cpu') {
        # Query the installed backend, rather than assuming NVIDIA is required.
        $devices = & $Server --list-devices 2>&1 | Out-String
        $available = $LASTEXITCODE -eq 0 -and $devices -match '(?im)^\s*(CUDA|Vulkan|SYCL|Metal|ROCm|HIP)\d*\s*:'
        if ($Acceleration -eq 'gpu' -and -not $available) {
            throw 'GPU mode requested, but the server reports no supported GPU device.'
        }
        if ($Acceleration -eq 'auto') {
            $modes = if ($available) { @('gpu', 'cpu') } else { @('cpu') }
        }
    }
    foreach ($mode in $modes) {
        $attemptProcesses = @()
        try {
            $layers = if ($mode -eq 'cpu') { '0' } else { '99' }
            $embeddingLayers = if ($mode -eq 'cpu' -or $EmbeddingAcceleration -eq 'cpu') { '0' } else { '99' }
            $generationArgs = @('-m', ('"' + $GenerationModel + '"'), '--host', '127.0.0.1', '--port', '8081', '-c', '16384', '-np', '1', '--alias', 'qwen3', '--log-disable', '-ngl', $layers)
            $embeddingArgs = @('-m', ('"' + $EmbeddingModel + '"'), '--host', '127.0.0.1', '--port', '8082', '-c', '8192', '-b', '8192', '-ub', '8192', '--embedding', '--pooling', 'cls', '--alias', 'bge-m3', '--log-disable', '-ngl', $embeddingLayers)
            if ($EmbeddingProfile -eq 'qwen3-retrieval-v1') {
                $embeddingArgs[$embeddingArgs.IndexOf('cls')] = 'last'
                $embeddingArgs[$embeddingArgs.IndexOf('bge-m3')] = 'qwen3-embedding-0.6b'
            }
            $embeddingArgs += @('--embd-normalize', '2', '--flash-attn', $FlashAttention)
            $generationArgs += @('--flash-attn', $FlashAttention)
            if ($mode -eq 'cpu') {
                $generationArgs += @('--device', 'none', '--no-op-offload', '--no-kv-offload')
            }
            if ($mode -eq 'cpu' -or $EmbeddingAcceleration -eq 'cpu') {
                $embeddingArgs += @('--device', 'none', '--no-op-offload', '--no-kv-offload')
            }
            if ($GenerationThreads -gt 0) { $generationArgs += @('-t', "$GenerationThreads") }
            if ($EmbeddingThreads -gt 0) { $embeddingArgs += @('-t', "$EmbeddingThreads") }
            Write-Host "[PMA] Launching models ($mode)..."
            $generation = Start-Process -FilePath $Server -ArgumentList $generationArgs -WindowStyle Hidden -PassThru
            $attemptProcesses += $generation
            Wait-Model 8081 $generation
            $embedding = Start-Process -FilePath $Server -ArgumentList $embeddingArgs -WindowStyle Hidden -PassThru
            $attemptProcesses += $embedding
            Wait-Model 8082 $embedding
            return $attemptProcesses
        } catch {
            foreach ($process in $attemptProcesses) {
                if (-not $process.HasExited) {
                    Stop-Process -Id $process.Id
                    $process.WaitForExit()
                }
            }
            if ($Acceleration -ne 'auto' -or $mode -eq 'cpu') {
                throw "Model startup failed ($mode): $($_.Exception.Message)"
            }
            Write-Host '[PMA] GPU startup failed; retrying once with CPU.'
        }
    }
}

try {
    # Check before hashing/loading models; the app also locks during its lifespan.
    & './.venv/Scripts/python.exe' -B -m pma --check-startup
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath $EmbeddingModel -PathType Leaf)) {
        throw 'BGE-M3 GGUF is missing. See README.md for the verified download.'
    }
    Write-Host '[PMA] Checking embedding model SHA-256...'
    $hashTimer = [Diagnostics.Stopwatch]::StartNew()
    $env:PMA_EMBEDDING_REVISION = (Get-FileHash -LiteralPath $EmbeddingModel -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "[PMA] SHA-256 complete ($([Math]::Round($hashTimer.Elapsed.TotalSeconds, 1))s)."
    $env:PMA_EMBEDDING_PROFILE = $EmbeddingProfile
    $env:PMA_EMBEDDING_MODEL = if ($EmbeddingProfile -eq 'qwen3-retrieval-v1') { 'qwen3-embedding-0.6b' } else { 'bge-m3' }
    $env:PMA_GENERATION_REVISION = (Get-FileHash -LiteralPath $GenerationModel -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:PMA_MODEL = 'qwen3'
    $env:PMA_CONTEXT_TOKENS = '16384'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    if (-not $ExternalServers) {
        foreach ($path in @($Server, $GenerationModel)) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing file: $path" }
        }
        foreach ($port in @(8081, 8082)) {
            Write-Host "[PMA] Checking port $port..."
            $client = [System.Net.Sockets.TcpClient]::new()
            try { $client.Connect('127.0.0.1', $port); throw "Port $port is already in use. Use -ExternalServers only for compatible servers." }
            catch [System.Net.Sockets.SocketException] { }
            finally { $client.Dispose() }
        }
        $ownedProcesses += @(Start-ModelServers -Server $Server -GenerationModel $GenerationModel -EmbeddingModel $EmbeddingModel -Acceleration $Acceleration -GenerationThreads $GenerationThreads -EmbeddingThreads $EmbeddingThreads -EmbeddingAcceleration $EmbeddingAcceleration -EmbeddingProfile $EmbeddingProfile -FlashAttention $FlashAttention)
    }
    Write-Host '[PMA] Starting web app. Keep this terminal open; press Ctrl+C to stop.'
    $appArguments = @('-u', '-B', '-m', 'pma')
    if ($NoBrowser) { $appArguments += '--no-browser' }
    if ($Test) { $appArguments += '--test' }
    & './.venv/Scripts/python.exe' @appArguments
    $appExitCode = $LASTEXITCODE
} finally {
    foreach ($process in $ownedProcesses) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    }
}
exit $appExitCode
