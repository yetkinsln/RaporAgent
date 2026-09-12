[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & docker compose stop
    if ($LASTEXITCODE -ne 0) {
        throw 'Rapor Agent servisleri durdurulamadı.'
    }
    Write-Host 'Rapor Agent durduruldu. runtime-data içindeki yerel vakalar korunuyor.' -ForegroundColor Green
}
finally {
    Pop-Location
}
