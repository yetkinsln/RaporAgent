[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$appUrl = 'http://127.0.0.1:5173/'

Push-Location $projectRoot
try {
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
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            Start-Sleep -Seconds 2
            $dockerVersion = & docker version --format '{{.Server.Version}}' 2>$null
            if ($LASTEXITCODE -eq 0 -and $dockerVersion) {
                break
            }
        }

        if ($LASTEXITCODE -ne 0 -or -not $dockerVersion) {
            throw 'Docker Desktop 60 saniye içinde hazır olmadı. Uygulamayı açıp Linux containers modunu kontrol edin.'
        }
    }

    $composeArgs = @('compose', 'up', '-d')
    if ($Rebuild) {
        $composeArgs += '--build'
    }
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker Compose servisleri başlatılamadı.'
    }

    $ready = $false
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $appUrl -TimeoutSec 3 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
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

    Write-Host "Uygulama hazır: $appUrl" -ForegroundColor Green
    Write-Host 'Durdurmak için: docker compose down' -ForegroundColor DarkGray

    if (-not $NoBrowser) {
        Start-Process $appUrl
    }
}
finally {
    Pop-Location
}
