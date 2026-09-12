[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$appUrl = 'http://127.0.0.1:5173/'
$healthUrl = "${appUrl}api/health"

Push-Location $projectRoot
try {
    $requiredPaths = @(
        'qwen3-8b\config.json',
        'qwen3-8b\tokenizer.json',
        'qwen3-8b\model.safetensors.index.json',
        'Templates\adli-rapor-sablonu-v2.docx',
        'Templates\kurumsal-girdiler_mapping_alan-esleme-v2.json'
    )
    $missingPaths = @($requiredPaths | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_)) })
    if ($missingPaths.Count -gt 0) {
        throw "Yayın girdileri eksik: $($missingPaths -join ', ')"
    }

    $dockerVersion = & docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) {
        $dockerCommand = Get-Command docker -ErrorAction Stop
        $dockerDesktopRoot = Split-Path (Split-Path (Split-Path $dockerCommand.Source -Parent) -Parent) -Parent
        $dockerDesktopApp = Join-Path $dockerDesktopRoot 'frontend\Docker Desktop.exe'

        if (-not (Test-Path -LiteralPath $dockerDesktopApp)) {
            throw 'Docker Desktop çalışmıyor. Docker Desktop uygulamasını açıp Linux containers modunda olduğundan emin olun.'
        }

        Write-Host 'Docker Desktop başlatılıyor...' -ForegroundColor Yellow
        Start-Process -FilePath $dockerDesktopApp -WindowStyle Hidden
        for ($attempt = 1; $attempt -le 60; $attempt++) {
            Start-Sleep -Seconds 2
            $dockerVersion = & docker version --format '{{.Server.Version}}' 2>$null
            if ($LASTEXITCODE -eq 0 -and $dockerVersion) {
                break
            }
        }

        if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) {
            $backendLog = Join-Path $env:LOCALAPPDATA 'Docker\log\host\com.docker.backend.exe.log'
            if ((Test-Path -LiteralPath $backendLog) -and (Select-String -LiteralPath $backendLog -Pattern 'sailor-ingest.sock' -Quiet)) {
                throw 'Docker Desktop geçici çalışma soketine erişemedi. Windows sistemini yeniden başlatın; ardından bu betiği tekrar çalıştırın. Proje ve runtime-data dosyalarını silmeyin.'
            }
            throw 'Docker Desktop 120 saniye içinde hazır olmadı. Uygulamayı açıp Linux containers modunu veya Docker tanılama ekranını kontrol edin.'
        }
    }

    $composeArgs = @('compose', 'up', '-d', '--remove-orphans')
    if ($Rebuild) {
        $composeArgs += '--build'
    }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose servisleri başlatılamadı.'
    }

    $ready = $false
    $health = $null
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
            if ($health.version) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $ready) {
        & docker compose ps
        & docker compose logs --tail 80 api web
        throw "Uygulama $appUrl adresinde hazır olmadı. Yukarıdaki Docker günlüklerini inceleyin."
    }

    Write-Host "Rapor Agent v$($health.version) hazır: $appUrl" -ForegroundColor Green
    Write-Host "OCR: $($health.components.ocr.ready) | Qwen3: $($health.components.llm.ready) | Word: $($health.components.docx.ready)" -ForegroundColor Cyan
    if ($health.status -ne 'ready') {
        Write-Warning 'Uygulama açıldı ancak en az bir yerel bileşen hazır değil. Üst durum çubuğunu kontrol edin.'
    }
    Write-Host 'Durdurmak için: docker compose down' -ForegroundColor DarkGray

    if (-not $NoBrowser) {
        Start-Process $appUrl
    }
}
finally {
    Pop-Location
}
