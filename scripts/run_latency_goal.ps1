param(
    [ValidateSet('cpu', 'gpu', 'both')][string]$Placement = 'cpu',
    [ValidateSet(5, 20)][int]$Samples = 5,
    [ValidateRange(1, 1024)][int]$Threads = 8,
    [ValidateRange(0, 1024)][int]$GenerationBatchThreads = 0,
    [switch]$DisableCpuRepacking,
    [switch]$InterpretationReuse,
    [switch]$IntermediatePlanning,
    [switch]$BoundedExpansions,
    [switch]$SourceDateDrafts,
    [switch]$ContextShortcut,
    [switch]$ScopedIdentitySearch,
    [switch]$BatchEight,
    [switch]$QualityScreen,
    [switch]$BaselineOnly,
    [switch]$RetrievalOnly,
    [switch]$ReviewBank,
    [switch]$ReviewOnly,
    [string]$RetrievalBaseline = '',
    [string]$AnchorTemplates = '',
    [string]$SeedTemplate = '',
    [switch]$CandidateOnly,
    [ValidateSet('llama', 'openvino')][string]$Runtime = 'llama',
    [string]$RuntimePython = '',
    [string]$RuntimeModel = '',
    [ValidateSet('legacy', 'development', 'holdout', 'identity_confirmation', 'identity_search_confirmation')][string]$FixtureSplit = 'legacy',
    [ValidateSet('baseline', 'q4', 'q8')][string]$Generation = 'baseline',
    [string]$ModelDirectory = '.local/response-latency/models',
    [switch]$ColdInterpretations,
    [string[]]$Cases = @('simple_search', 'simple_answer'),
    [string]$RunName = ('manual-' + (Get-Date -Format 'yyyyMMdd-HHmmss')),
    [string]$PythonExe = '',
    [switch]$PauseOrdinaryModels,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $PythonExe) { $PythonExe = Join-Path $root '.venv\Scripts\python.exe' }
if ($RunName -notmatch '^[a-zA-Z0-9_-]+$') { throw 'RunName must contain letters, digits, underscores or hyphens.' }
if ($BaselineOnly -and $CandidateOnly) { throw 'Choose either BaselineOnly or CandidateOnly.' }
$outputRoot = Join-Path $root ('.local\latency-goal\' + $RunName)
$placements = if ($Placement -eq 'both') { @('cpu', 'gpu') } else { @($Placement) }
$commands = @()
foreach ($mode in $placements) {
    $output = Join-Path $outputRoot $mode
    $candidateOptions = @('compact_ids', 'source_facts')
    if ($InterpretationReuse) { $candidateOptions += 'interpretation_cache' }
    if ($IntermediatePlanning) { $candidateOptions += 'intermediate' }
    if ($BoundedExpansions) { $candidateOptions += 'bounded_expansions' }
    if ($SourceDateDrafts) { $candidateOptions += 'source_dates' }
    if ($ContextShortcut) { $candidateOptions += 'context_shortcut' }
    if ($ScopedIdentitySearch) { $candidateOptions += 'scoped_identity' }
    if ($BatchEight) { $candidateOptions += 'batch8' }
    $iterations = if ($QualityScreen) { 1 } else { $Samples }
    $arguments = @('-u', '-m', 'evaluation.response_latency', '--output', $output,
        '--placement', $mode, '--samples', "$iterations", '--threads', "$Threads",
        '--generation-batch-threads', "$GenerationBatchThreads", '--embedding-batch', '4096',
        '--generation', $Generation, '--model-directory', $ModelDirectory,
        '--startup-memory', '--min-free-gib', '8',
        '--port', '18581', '--variants', 'current', 'candidate',
        '--candidate-options') + $candidateOptions + @(
        '--fixed-anchor', '--reset-prompt-cache', '--cancel-file', (Join-Path $output 'cancel.request'))
    if ($BaselineOnly) {
        $variantIndex = [Array]::IndexOf($arguments, '--variants')
        $arguments = @($arguments[0..($variantIndex + 1)]) + @($arguments[($variantIndex + 3)..($arguments.Count - 1)])
    }
    if ($CandidateOnly) {
        $variantIndex = [Array]::IndexOf($arguments, '--variants')
        $arguments = @($arguments[0..$variantIndex]) + @($arguments[($variantIndex + 2)..($arguments.Count - 1)])
    }
    if ($BaselineOnly -or $InterpretationReuse -or $IntermediatePlanning) {
        # Compare with the already measured source-draft/compact-ID candidate.
        $arguments += @('--baseline-options', 'compact_ids', 'source_facts')
        if ($InterpretationReuse -and ($IntermediatePlanning -or $BaselineOnly)) { $arguments += 'interpretation_cache' }
    }
    if ($ColdInterpretations) { $arguments += '--cold-interpretations' }
    if ($FixtureSplit -ne 'legacy') {
        $arguments[2] = 'evaluation.first_response'
        $arguments += @('--execute', '--split', $FixtureSplit)
    }
    if ($FixtureSplit -eq 'legacy' -or $PSBoundParameters.ContainsKey('Cases')) { $arguments += @('--cases') + $Cases }
    if ($RetrievalOnly) { $arguments += @('--retrieval-only', '--multilingual', '--multilingual-current-only', '--skip-timing-on-retrieval-failure') }
    if ($RetrievalBaseline) { $arguments += @('--retrieval-baseline', $RetrievalBaseline) }
    if ($AnchorTemplates) { $arguments += @('--anchor-templates', $AnchorTemplates) }
    if ($SeedTemplate) { $arguments += @('--seed-template', $SeedTemplate) }
    if ($ReviewBank) { $arguments += '--review-bank' }
    if ($ReviewOnly) { $arguments += '--review-only' }
    if ($QualityScreen) { $arguments += '--quality-only' }
    if ($Runtime -eq 'openvino') {
        if ($mode -ne 'cpu' -or -not $RuntimePython -or -not $RuntimeModel) { throw 'OpenVINO requires CPU, RuntimePython and RuntimeModel.' }
        $arguments += @('--runtime', 'openvino', '--runtime-python', $RuntimePython, '--runtime-model', $RuntimeModel)
    }
    $commands += ,$arguments
}
if (-not $Execute) {
    Write-Host 'Plan only. Add -Execute to run real synthetic-data model measurements.'
    Write-Host "Ordinary models will be paused only with -PauseOrdinaryModels: $PauseOrdinaryModels"
    Write-Host "Disable weight repacking for owned CPU trials: $DisableCpuRepacking"
    foreach ($arguments in $commands) { Write-Output (@($PythonExe) + $arguments | ConvertTo-Json -Compress) }
    return
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Specify the project Python with -PythonExe.' }
if (Test-Path -LiteralPath $outputRoot) { throw 'Choose a new RunName; previous results are preserved.' }
$originals = @()
if ($PauseOrdinaryModels) {
    $originals = @(Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -eq 'C:\llama.cpp\llama-server.exe' -and $_.CommandLine -match '--port 808[12]\b'
    })
    if ($originals.Count -ne 2) { throw 'Expected exactly two known ordinary model servers; nothing stopped.' }
    foreach ($model in $originals) {
        if (-not $model.CommandLine.StartsWith(('"' + $model.ExecutablePath + '"'))) {
            throw 'Unexpected server command format; nothing stopped.'
        }
    }
}
New-Item -ItemType Directory -Path $outputRoot | Out-Null
ConvertTo-Json -InputObject @($originals | Select-Object ProcessId,ExecutablePath,CommandLine) |
    Set-Content (Join-Path $outputRoot 'ordinary-models-before.json')
$stopped = @()
$restored = @()
$restoreErrors = @()
$originalRepack = [Environment]::GetEnvironmentVariable('LLAMA_ARG_REPACK', 'Process')
$serverEnvironment = @()
$previousLocation = Get-Location
$launchPlan = [ordered]@{
    schema_version = 1
    record_kind = 'captured before owned model start'
    launcher_sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    python = $PythonExe
    placements = @($placements)
    baseline_only = [bool]$BaselineOnly
    commands = @($commands)
    effective_trial_environment = @{ LLAMA_ARG_REPACK = $(if ($DisableCpuRepacking) { '0' } else { $originalRepack }) }
}
$launchPlan | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $outputRoot 'launch-plan.json') -Encoding utf8
try {
    foreach ($model in $originals) {
        $live = Get-CimInstance Win32_Process -Filter "ProcessId = $($model.ProcessId)"
        if ($live.CommandLine -ne $model.CommandLine) { throw 'Process identity changed; refusing to stop it.' }
        Stop-Process -Id $model.ProcessId
        $stopped += $model
    }
    Set-Location -LiteralPath $root
    foreach ($arguments in $commands) {
        $mode = $arguments[[Array]::IndexOf($arguments, '--placement') + 1]
        $repack = if ($DisableCpuRepacking -and $mode -eq 'cpu') { '0' } else { $originalRepack }
        if ($null -eq $repack) {
            [Environment]::SetEnvironmentVariable('LLAMA_ARG_REPACK', [NullString]::Value, 'Process')
        } else {
            [Environment]::SetEnvironmentVariable('LLAMA_ARG_REPACK', $repack, 'Process')
        }
        $serverEnvironment += @{placement=$mode; LLAMA_ARG_REPACK=$repack}
        ConvertTo-Json -InputObject @($serverEnvironment) | Set-Content (Join-Path $outputRoot 'model-server-environment.json')
        & $PythonExe @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Measurement interrupted or failed. Partial results are preserved.' }
    }
    $results = @($placements | ForEach-Object { Join-Path $outputRoot "$_\results.json" })
    $reportModule = if ($BaselineOnly) { 'evaluation.latency_bottlenecks' } elseif ($IntermediatePlanning -or $FixtureSplit -ne 'legacy') { 'evaluation.first_response_report' } elseif ($InterpretationReuse) { 'evaluation.interpretation_reuse_report' } else { 'evaluation.latency_target_report' }
    $reportFile = if ($BaselineOnly) { 'baseline.json' } elseif ($reportModule -eq 'evaluation.first_response_report') { 'comparison.json' } else { 'comparison.rst' }
    & $PythonExe -m $reportModule @results --output (Join-Path $outputRoot $reportFile)
    if ($LASTEXITCODE -ne 0) { throw 'Report generation failed; raw results remain available.' }
    Write-Host "Result: $(Join-Path $outputRoot $reportFile)"
    if ($FixtureSplit -ne 'legacy' -and -not $RetrievalOnly -and -not $ReviewOnly) {
        foreach ($mode in $placements) {
            $modeRoot = Join-Path $outputRoot $mode
            & $PythonExe -m evaluation.first_response_review (Join-Path $modeRoot 'results.json') --output (Join-Path $modeRoot 'answers.html')
            if ($LASTEXITCODE -ne 0) { throw 'Answer review generation failed; raw results remain available.' }
            Write-Host "Answers: $(Join-Path $modeRoot 'answers.html')"
        }
    }
} finally {
    if ($null -eq $originalRepack) {
        [Environment]::SetEnvironmentVariable('LLAMA_ARG_REPACK', [NullString]::Value, 'Process')
    } else {
        [Environment]::SetEnvironmentVariable('LLAMA_ARG_REPACK', $originalRepack, 'Process')
    }
    Set-Location -LiteralPath $previousLocation.Path
    foreach ($model in $stopped) {
        $prefix = '"' + $model.ExecutablePath + '"'
        $arguments = $model.CommandLine.Substring($prefix.Length).TrimStart()
        try {
            $process = Start-Process -FilePath $model.ExecutablePath -ArgumentList $arguments -WindowStyle Hidden -PassThru
            $restored += @{ original_pid=$model.ProcessId; restored_pid=$process.Id; arguments=$arguments }
        } catch {
            $restoreErrors += @{ original_pid=$model.ProcessId; error_type=$_.Exception.GetType().Name }
        }
    }
    ConvertTo-Json -InputObject @($restored) -Depth 3 | Set-Content (Join-Path $outputRoot 'ordinary-models-restored.json')
    ConvertTo-Json -InputObject @($restoreErrors) | Set-Content (Join-Path $outputRoot 'ordinary-models-restore-errors.json')
    $health = @()
    foreach ($entry in $restored) {
        $port = if ($entry.arguments -match '--port (808[12])\b') { $Matches[1] } else { '' }
        $ready = $false
        $deadline = [DateTime]::UtcNow.AddMinutes(5)
        while ($port -and [DateTime]::UtcNow -lt $deadline) {
            try {
                $ready = (Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200
            } catch { }
            if ($ready) { break }
            Start-Sleep -Seconds 1
        }
        $health += @{ port=$port; ready=$ready }
    }
    ConvertTo-Json -InputObject @($health) | Set-Content (Join-Path $outputRoot 'ordinary-models-health.json')
    if ($restoreErrors.Count -or @($health | Where-Object { -not $_.ready }).Count) {
        throw 'Inspect the saved restoration and health reports; a restored server is not ready.'
    }
}
