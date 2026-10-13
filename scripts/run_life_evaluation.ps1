param(
    [string]$RunDirectory = 'output/life-baseline',
    [string]$CacheDirectory = '',
    [string]$Server = 'C:\llama.cpp\llama-server.exe',
    [string]$GenerationModel = 'C:\models\Qwen3-8B-Q4_K_M.gguf',
    [string]$EmbeddingModel = 'C:\models\bge-m3-Q8_0.gguf',
    [ValidateSet('all', 'extract', 'questions', 'lifecycle')][string]$Phase = 'all',
    [switch]$ExternalServers
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$ownedProcesses = @()
$evaluationExitCode = 1
function Wait-EvaluationModel([int]$Port, $Process) {
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    $lastStatus = [DateTime]::MinValue
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) { throw "Model on port $Port exited." }
        try {
            $health = Invoke-WebRequest "http://127.0.0.1:$Port/health" -TimeoutSec 2 -NoProxy
            if ($health.StatusCode -eq 200) { return }
        } catch { }
        if (([DateTime]::UtcNow - $lastStatus).TotalSeconds -ge 10) {
            Write-Host "Waiting for local model on $Port..."
            $lastStatus = [DateTime]::UtcNow
        }
        Start-Sleep -Milliseconds 500
    }
    throw "Model on port $Port did not become ready."
}
try {
    $env:PMA_MODEL = 'qwen3'
    $env:PMA_EMBEDDING_MODEL = 'bge-m3'
    $env:PMA_CONTEXT_TOKENS = '16384'
    $env:PMA_EMBEDDING_REVISION = (Get-FileHash -LiteralPath $EmbeddingModel -Algorithm SHA256).Hash.ToLowerInvariant()
    $env:PMA_GENERATION_REVISION = (Get-FileHash -LiteralPath $GenerationModel -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $ExternalServers) {
        foreach ($port in @(8081, 8082)) {
            $client = [System.Net.Sockets.TcpClient]::new()
            try {
                $client.Connect('127.0.0.1', $port)
                throw "Port $port is already occupied. Use -ExternalServers only for matching local models."
            } catch [System.Net.Sockets.SocketException] { }
            finally { $client.Dispose() }
        }
        $gen = Start-Process -FilePath $Server -ArgumentList @('-m', ('"' + $GenerationModel + '"'), '--host', '127.0.0.1', '--port', '8081', '-c', '16384', '-np', '1', '--alias', 'qwen3', '--log-disable') -WindowStyle Hidden -PassThru
        $ownedProcesses += $gen
        Wait-EvaluationModel 8081 $gen
        $emb = Start-Process -FilePath $Server -ArgumentList @('-m', ('"' + $EmbeddingModel + '"'), '--host', '127.0.0.1', '--port', '8082', '-c', '8192', '-b', '8192', '-ub', '8192', '--embedding', '--pooling', 'cls', '--alias', 'bge-m3', '--log-disable') -WindowStyle Hidden -PassThru
        $ownedProcesses += $emb
        Wait-EvaluationModel 8082 $emb
    } else {
        Wait-EvaluationModel 8081 $null
        Wait-EvaluationModel 8082 $null
    }
    $evaluationArgs = @('-X', 'utf8', '-u', '-B', '-m', 'evaluation.life_diagnostics', '--run-dir', $RunDirectory, '--phase', $Phase)
    if ($CacheDirectory) { $evaluationArgs += @('--cache-dir', $CacheDirectory) }
    & './.venv/Scripts/python.exe' @evaluationArgs
    $evaluationExitCode = $LASTEXITCODE
} finally {
    if (Test-Path -LiteralPath (Join-Path $RunDirectory 'manifest.json')) {
        & './.venv/Scripts/python.exe' -X utf8 -B -m evaluation.life_report --run-dir $RunDirectory
    }
    foreach ($process in $ownedProcesses) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id }
    }
}
exit $evaluationExitCode
