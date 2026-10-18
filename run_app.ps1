param(
    [string]$Server = 'C:\llama.cpp\llama-server.exe',
    [string]$GenerationModel = 'C:\models\Qwen3-8B-Q4_K_M.gguf',
    [string]$EmbeddingModel = 'C:\models\bge-m3-Q8_0.gguf',
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
        if ($Process.HasExited) { throw "Model server on port $Port exited." }
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
try {
    if (-not (Test-Path -LiteralPath $EmbeddingModel -PathType Leaf)) {
        throw 'BGE-M3 GGUF is missing. See README.md for the verified download.'
    }
    Write-Host '[PMA] Checking embedding model SHA-256...'
    $hashTimer = [Diagnostics.Stopwatch]::StartNew()
    $env:PMA_EMBEDDING_REVISION = (Get-FileHash -LiteralPath $EmbeddingModel -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "[PMA] SHA-256 complete ($([Math]::Round($hashTimer.Elapsed.TotalSeconds, 1))s)."
    $env:PMA_EMBEDDING_MODEL = 'bge-m3'
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
        Write-Host '[PMA] Launching Qwen server (8081). Windows process startup may take a while...'
        $generation = Start-Process -FilePath $Server -ArgumentList @('-m', ('"' + $GenerationModel + '"'), '--host', '127.0.0.1', '--port', '8081', '-c', '16384', '-np', '1', '--alias', 'qwen3', '--log-disable') -WindowStyle Hidden -PassThru
        $ownedProcesses += $generation
        Wait-Model 8081 $generation
        Write-Host '[PMA] Launching BGE-M3 server (8082). Windows process startup may take a while...'
        $embedding = Start-Process -FilePath $Server -ArgumentList @('-m', ('"' + $EmbeddingModel + '"'), '--host', '127.0.0.1', '--port', '8082', '-c', '8192', '-b', '8192', '-ub', '8192', '--embedding', '--pooling', 'cls', '--alias', 'bge-m3', '--log-disable') -WindowStyle Hidden -PassThru
        $ownedProcesses += $embedding
        Wait-Model 8082 $embedding
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
