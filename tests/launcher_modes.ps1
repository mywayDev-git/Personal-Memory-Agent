$ErrorActionPreference = 'Stop'
$source = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../run_app.ps1')
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$definition = $ast.FindAll({param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Start-ModelServers'
}, $true)[0]
Invoke-Expression $definition.Extent.Text

function Reset-Mocks {
    $script:launched = [System.Collections.Generic.List[object]]::new()
    $script:stopped = [System.Collections.Generic.List[int]]::new()
    $script:waited = [System.Collections.Generic.List[int]]::new()
    $script:deviceQueries = 0
    $script:deviceListing = 'CUDA0: fake device'
    $script:failEmbeddingGpu = $false
    $script:failAll = $false
}
function Test-Devices {
    param([Parameter(ValueFromRemainingArguments=$true)]$Arguments)
    $script:deviceQueries++
    $global:LASTEXITCODE = 0
    $script:deviceListing
}
function Start-Process {
    param($FilePath, $ArgumentList, $WindowStyle, [switch]$PassThru)
    $process = [pscustomobject]@{Id = $script:launched.Count + 1; HasExited = $false}
    $process | Add-Member ScriptMethod WaitForExit { $script:waited.Add($this.Id) }
    $script:launched.Add([pscustomobject]@{Process=$process; Args=$ArgumentList; Window=$WindowStyle})
    $process
}
function Stop-Process {
    param([int]$Id)
    $script:stopped.Add($Id)
    $script:launched[$Id - 1].Process.HasExited = $true
}
function Wait-Model {
    param($Port, $Process)
    if ($script:failAll -or ($script:failEmbeddingGpu -and $Port -eq 8082 -and $Process.Id -eq 2)) {
        throw 'synthetic startup failure'
    }
}
function Assert($Condition, $Message) { if (-not $Condition) { throw $Message } }
function Layers($Entry) { $Entry.Args[[Array]::IndexOf($Entry.Args, '-ngl') + 1] }
function Assert-CpuOnly($Entry) {
    Assert ($Entry.Args -contains '--no-op-offload') 'CPU host operations must not use a GPU'
    Assert ($Entry.Args -contains '--no-kv-offload') 'CPU KV cache must not use a GPU'
    Assert ($Entry.Args[[Array]::IndexOf($Entry.Args, '--device') + 1] -eq 'none') 'CPU device selection must be none'
}

Reset-Mocks
$models = @(Start-ModelServers Test-Devices 'generation model.gguf' 'embedding model.gguf' cpu 4 2)
Assert ($models.Count -eq 2 -and $script:deviceQueries -eq 0) 'CPU must not query GPU devices'
Assert ((Layers $script:launched[0]) -eq '0' -and (Layers $script:launched[1]) -eq '0') 'CPU offload must be zero'
Assert-CpuOnly $script:launched[0]
Assert-CpuOnly $script:launched[1]
Assert ($script:launched[0].Args[-1] -eq '4' -and $script:launched[1].Args[-1] -eq '2') 'per-server thread options lost'
Assert (-not ($script:launched[0].Args -contains '-tb')) 'unset batch threads must preserve the server default'

Reset-Mocks
$models = @(Start-ModelServers Test-Devices gen emb cpu 8 4 auto raw-v1 auto 16 8)
Assert ($script:launched[0].Args[[Array]::IndexOf($script:launched[0].Args, '-tb') + 1] -eq '16') 'generation batch thread option lost'
Assert ($script:launched[1].Args[[Array]::IndexOf($script:launched[1].Args, '-tb') + 1] -eq '8') 'embedding batch thread option lost'

Reset-Mocks
$script:failEmbeddingGpu = $true
$models = @(Start-ModelServers Test-Devices gen emb auto 0 0)
Assert ($script:launched.Count -eq 4 -and $models[0].Id -eq 3) 'auto must retry CPU once'
Assert (($script:stopped -join ',') -eq '1,2' -and ($script:waited -join ',') -eq '1,2') 'failed GPU pair must exit before retry'
Assert ((Layers $script:launched[0]) -eq '99' -and (Layers $script:launched[2]) -eq '0') 'fallback offload flags incorrect'
Assert (-not ($script:launched[2].Args -contains '-t')) 'unset threads must preserve server default'
Assert-CpuOnly $script:launched[2]
Assert-CpuOnly $script:launched[3]
Assert (-not ($script:launched[0].Args -contains '--no-op-offload')) 'GPU attempt must retain acceleration'
Assert (@($script:launched | Where-Object Window -ne Hidden).Count -eq 0) 'background windows must stay hidden'

Reset-Mocks
$models = @(Start-ModelServers Test-Devices gen emb gpu 0 0 cpu)
Assert ((Layers $script:launched[0]) -eq '99' -and (Layers $script:launched[1]) -eq '0') 'mixed placement must keep generation on GPU and embeddings on CPU'
Assert-CpuOnly $script:launched[1]
Assert (-not ($script:launched[0].Args -contains '--device')) 'mixed generation must retain its GPU'

Reset-Mocks
$models = @(Start-ModelServers Test-Devices gen emb gpu 0 0 cpu 'qwen3-retrieval-v1' 'off')
Assert ($script:launched[1].Args -contains 'last') 'Qwen embeddings require last-token pooling'
Assert ($script:launched[1].Args -contains 'qwen3-embedding-0.6b') 'embedding alias must match the selected profile'
Assert ($script:launched[0].Args -contains 'off') 'explicit Flash Attention selection lost'

Reset-Mocks
$models = @(Start-ModelServers Test-Devices gen emb cpu 0 0 gpu)
Assert ($script:deviceQueries -eq 0 -and (Layers $script:launched[1]) -eq '0') 'CPU-only mode must override embedding placement'

Reset-Mocks
$script:deviceListing = 'CPU: fake CPU'
$models = @(Start-ModelServers Test-Devices gen emb auto 0 0)
Assert ($script:launched.Count -eq 2 -and (Layers $script:launched[0]) -eq '0') 'auto without GPU must use CPU'

Reset-Mocks
$script:deviceListing = 'CUDA error: no devices'
$models = @(Start-ModelServers Test-Devices gen emb auto 0 0)
Assert ((Layers $script:launched[0]) -eq '0') 'CUDA error text must not be mistaken for a device'

Reset-Mocks
$script:deviceListing = 'CPU: fake CPU'
$message = ''
try { Start-ModelServers Test-Devices gen emb gpu 0 0 } catch { $message = $_.Exception.Message }
Assert ($message -match 'no supported GPU' -and $script:launched.Count -eq 0) 'explicit GPU must report unavailable device'

Reset-Mocks
$script:failAll = $true
$message = ''
try { Start-ModelServers Test-Devices gen emb auto 0 0 } catch { $message = $_.Exception.Message }
Assert ($script:launched.Count -eq 2 -and $script:stopped.Count -eq 2) 'both failed attempts must be cleaned up'
Assert ($message -match 'failed \(cpu\)') 'CPU fallback failure must propagate'

Reset-Mocks
$ExternalServers = $true
$external = $ast.FindAll({param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
    $node.Extent.Text.StartsWith('if (-not $ExternalServers)')
}, $true)[0]
Invoke-Expression $external.Extent.Text
Assert ($script:launched.Count -eq 0 -and $script:deviceQueries -eq 0) 'external servers must not be reconfigured'

Write-Output 'launcher tests passed'
