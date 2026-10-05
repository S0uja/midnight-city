$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$defaultModel = 'C:\AI\MidnightBrain_v2_MapAgnostic\models\Qwen3-4B-Nymphaea-RP'
$defaultAdapter = 'C:\AI\MidnightBrain_v2_MapAgnostic\output\MidnightBrain-v3\adapter'

$model = $env:MIDNIGHT_BRAIN_MODEL
if ([string]::IsNullOrWhiteSpace($model)) { $model = $defaultModel }
$adapter = $env:MIDNIGHT_BRAIN_ADAPTER
if ([string]::IsNullOrWhiteSpace($adapter)) { $adapter = $defaultAdapter }

if (-not (Test-Path (Join-Path $model 'config.json'))) {
    Get-ChildItem 'C:\AI\MidnightBrain_v2_MapAgnostic\models' -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { if (Test-Path (Join-Path $_.FullName 'config.json')) { $model = $_.FullName } }
}

if (-not (Test-Path (Join-Path $adapter 'adapter_model.safetensors'))) {
    $adapterCandidate = 'C:\AI\MidnightBrain_v2_MapAgnostic\output\MidnightBrain-v3\adapter'
    if (Test-Path (Join-Path $adapterCandidate 'adapter_model.safetensors')) { $adapter = $adapterCandidate }
}

Write-Host ('=' * 68)
Write-Host 'MIDNIGHT CITY - LOCAL MIDNIGHTBRAIN V25'
Write-Host ('=' * 68)
Write-Host "Model:   $model"
Write-Host "Adapter: $adapter"

if (-not (Test-Path (Join-Path $model 'config.json'))) {
    Write-Host '[ERROR] Transformers model not found.' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
if (-not (Test-Path (Join-Path $adapter 'adapter_model.safetensors'))) {
    Write-Host '[ERROR] MidnightBrain v3 adapter not found.' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}

$env:MIDNIGHT_BRAIN_MODEL = $model
$env:MIDNIGHT_BRAIN_ADAPTER = $adapter

if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3 "$Root\midnight_city_server_local.py"
} else {
    & python.exe "$Root\midnight_city_server_local.py"
}

Read-Host 'Press Enter to close'
