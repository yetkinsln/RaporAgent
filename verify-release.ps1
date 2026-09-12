[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$testRun = Join-Path $projectRoot ".test-runs\release-$PID"

Push-Location $projectRoot
try {
    Write-Host 'Docker Compose sözleşmesi doğrulanıyor...' -ForegroundColor Cyan
    & docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'compose.yaml doğrulanamadı.' }

    Write-Host 'Ön uç testleri ve üretim derlemesi çalıştırılıyor...' -ForegroundColor Cyan
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw 'Ön uç testleri başarısız.' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Ön uç üretim derlemesi başarısız.' }
        & npm.cmd audit --audit-level=moderate
        if ($LASTEXITCODE -ne 0) { throw 'Ön uç bağımlılık denetimi başarısız.' }
    }
    finally {
        Pop-Location
    }

    Write-Host 'Web Docker imajı gerçek yayın bağlamıyla oluşturuluyor...' -ForegroundColor Cyan
    & docker compose build web
    if ($LASTEXITCODE -ne 0) { throw 'Web Docker imajı oluşturulamadı.' }

    $python = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Arka uç test ortamı bulunamadı: backend\.venv'
    }
    New-Item -ItemType Directory -Force -Path $testRun | Out-Null
    Write-Host 'Arka uç sözleşme testleri çalıştırılıyor...' -ForegroundColor Cyan
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $python -m pytest -q -p no:cacheprovider --basetemp=$testRun
        if ($LASTEXITCODE -ne 0) { throw 'Arka uç testleri başarısız.' }
    }
    finally {
        Pop-Location
    }

    Write-Host 'Yayın doğrulaması tamamlandı.' -ForegroundColor Green
}
finally {
    Pop-Location
}
