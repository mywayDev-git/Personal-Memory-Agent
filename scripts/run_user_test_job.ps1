param([Parameter(Mandatory=$true)][string]$Configuration)
$ErrorActionPreference = 'Stop'
$values = Get-Content -LiteralPath $Configuration -Raw -Encoding UTF8 | ConvertFrom-Json
$options = @{}
foreach ($property in $values.PSObject.Properties) { $options[$property.Name] = $property.Value }
& (Join-Path $PSScriptRoot 'run_latency_goal.ps1') @options
if ($LASTEXITCODE) { exit $LASTEXITCODE }
