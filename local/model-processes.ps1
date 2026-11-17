$ErrorActionPreference = 'Stop'
$request = $env:MEMORY_LAB_PROCESS_REQUEST | ConvertFrom-Json
if ($request.mode -notin @('inspect','terminate')) { throw 'Invalid process action' }
$appRoot = [IO.Path]::GetFullPath([string]$request.root).TrimEnd('\')
$expectedExe = [IO.Path]::GetFullPath([string]$request.exe)
function Test-Argument([string]$line,[string]$flag,[string]$value) {
    $pattern = '(?:^|\s)' + [regex]::Escape($flag) + '\s+(?:"' + [regex]::Escape($value) + '"|' + [regex]::Escape($value) + ')(?=\s|$)'
    return [regex]::IsMatch($line,$pattern,[Text.RegularExpressions.RegexOptions]::IgnoreCase)
}
function Find-AppModels {
    @(Get-CimInstance Win32_Process -Filter "Name='llama-server.exe'" | Where-Object {
        $candidate = $_
        if ($candidate.ExecutablePath -ine $expectedExe) { return $false }
        foreach ($model in $request.models) {
            $modelPath = Join-Path (Join-Path $appRoot '.models') ([string]$model.file)
            $port = if ($model.role -eq 'generation') {'18491'} else {'18492'}
            if ((Test-Argument $candidate.CommandLine '-m' $modelPath) -and (Test-Argument $candidate.CommandLine '--port' $port)) { return $true }
        }
        return $false
    })
}
$initial = @(Find-AppModels)
$terminated = @()
if ($request.mode -eq 'terminate') {
    foreach ($candidate in $initial) {
        # Re-read PID identity immediately before termination; never kill by image name.
        $fresh = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $candidate.ProcessId)
        if (-not $fresh) { continue }
        if ($fresh.CreationDate -ne $candidate.CreationDate -or $fresh.CommandLine -ne $candidate.CommandLine -or $fresh.ExecutablePath -ine $expectedExe) { throw 'Process identity changed; termination refused.' }
        Stop-Process -Id $fresh.ProcessId -Force -ErrorAction Stop
        $terminated += [int]$fresh.ProcessId
    }
}
$remaining = @(if ($request.mode -eq 'terminate') { Find-AppModels } else { $initial })
if ($request.mode -eq 'terminate') {
    for ($attempt=0; $attempt -lt 20 -and $remaining.Count -gt 0; $attempt++) { Start-Sleep -Milliseconds 200; $remaining = @(Find-AppModels) }
}
$rows = @($remaining | ForEach-Object {
    $candidate = $_
    $processInfo = Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue
    $role = if (Test-Argument $candidate.CommandLine '--port' '18491') {'generation'} else {'embedding'}
    [pscustomobject]@{pid=[int]$candidate.ProcessId;role=$role;ram_mb=[math]::Round($processInfo.WorkingSet64/1MB);private_mb=[math]::Round($processInfo.PrivateMemorySize64/1MB)}
})
[pscustomobject]@{verified=$true;checked_at=[DateTime]::UtcNow.ToString('o');terminated_pids=@($terminated);remaining=@($rows);scope='Matching executable + exact registered app model path + dedicated port; other apps excluded'} | ConvertTo-Json -Depth 6 -Compress
