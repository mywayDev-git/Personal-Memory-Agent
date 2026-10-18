# Stop TCP listeners used by the local PMA app and model servers.
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [ValidateRange(1, 65535)]
    [int[]]$Ports = @(8765, 8766, 8081, 8082)
)
$ErrorActionPreference = 'Stop'
$failed = $false

try {
    # Query all listeners so an unused requested port is not treated as an error.
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
} catch {
    Write-Error "포트 정보를 조회하지 못했습니다. 권한과 Windows 네트워크 상태를 확인하세요. $($_.Exception.Message)"
    exit 1
}

$stopped = @{}
foreach ($port in ($Ports | Select-Object -Unique)) {
    $owners = @($listeners | Where-Object LocalPort -EQ $port |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -eq 0) {
        Write-Host "[PMA] 포트 ${port}: 이미 종료되어 있습니다."
        continue
    }
    foreach ($ownerId in $owners) {
        if ($stopped.ContainsKey($ownerId)) { continue }
        if ($ownerId -le 4 -or $ownerId -eq $PID) {
            Write-Warning "포트 ${port}: 시스템 또는 현재 실행 프로세스는 종료하지 않습니다."
            $failed = $true
            continue
        }
        try {
            $process = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
            if ($null -eq $process) { continue }
            $target = "포트 $port / $($process.ProcessName) (PID $ownerId)"
            if ($PSCmdlet.ShouldProcess($target, '포트를 사용하는 프로세스 종료')) {
                Stop-Process -InputObject $process -Force -ErrorAction Stop
                if (-not $process.WaitForExit(5000)) {
                    throw '5초 안에 프로세스가 종료되지 않았습니다.'
                }
                $stopped[$ownerId] = $true
                Write-Host "[PMA] 종료 완료: $target"
            }
        } catch {
            $failed = $true
            Write-Warning "포트 ${port} 종료 실패: $($_.Exception.Message) 권한 오류라면 관리자 PowerShell에서 다시 실행하세요."
        }
    }
}
if ($failed) { exit 1 }
