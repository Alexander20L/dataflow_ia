<#
.SYNOPSIS
  Publica DataFlow AI desde este equipo con un túnel rápido de Cloudflare (sin servidor propio).

.DESCRIPTION
  1. Comprueba que Docker esté en marcha y levanta la aplicación (perfil full).
  2. Abre `cloudflared tunnel --url http://localhost:3002` en segundo plano y lee su dirección
     https://<algo>.trycloudflare.com (cambia cada vez que se abre).
  3. Guarda esa dirección en infrastructure/compose/.env (DATAFLOW_PUBLIC_URL) y reinicia la API
     con compose.tunnel.yaml: acepta ese origen y las cookies de sesión van sólo por HTTPS.
  4. Comprueba la cadena entera desde la dirección pública y la muestra.

  El túnel sigue abierto aunque se cierre esta ventana; se cierra con -Stop, al apagar el equipo
  o al cerrar sesión.

.PARAMETER Stop
  Cierra el túnel abierto por este script.

.PARAMETER Registration
  on / off: abre o cierra el registro de cuentas nuevas (se guarda en .env).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File infrastructure\compose\tunnel.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File infrastructure\compose\tunnel.ps1 -Registration off
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File infrastructure\compose\tunnel.ps1 -Stop
#>
param(
    [switch]$Stop,
    [ValidateSet("on", "off")]
    [string]$Registration
)

# Docker escribe su progreso en stderr: en PowerShell 5.1 eso no debe cortar el script; los
# fallos se comprueban con $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$here = $PSScriptRoot
$envFile = Join-Path $here ".env"
$pidFile = Join-Path $here ".tunnel.pid"
$logFile = Join-Path $here ".tunnel.log"
$compose = @(
    "compose", "-f", (Join-Path $here "compose.yaml"),
    "-f", (Join-Path $here "compose.tunnel.yaml"), "--profile", "full"
)

function Write-Step([string]$text) { Write-Host "» $text" -ForegroundColor Cyan }

# Escribe una variable en .env sin tocar las demás (UTF-8 sin BOM y saltos LF, como lo lee Compose).
function Set-EnvValue([string]$name, [string]$value) {
    $lines = @()
    if (Test-Path $envFile) {
        $lines = [IO.File]::ReadAllLines($envFile) | Where-Object { $_ -notmatch "^$name=" }
    }
    $lines += "$name=$value"
    [IO.File]::WriteAllText($envFile, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
}

function Stop-Tunnel {
    if (Test-Path $pidFile) {
        $old = Get-Content $pidFile -ErrorAction SilentlyContinue
        if ($old) {
            Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

if ($Stop) {
    Stop-Tunnel
    Write-Host "Túnel cerrado. La aplicación sigue en http://localhost:3002." -ForegroundColor Green
    exit 0
}

# 1. Docker y la aplicación.
Write-Step "Comprobando Docker"
docker version --format "{{.Server.Version}}" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker no está en marcha: abre Docker Desktop, espera a «Engine running» y vuelve a ejecutar." -ForegroundColor Red
    exit 1
}
$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $cloudflared = Get-ChildItem "C:\Program Files*\cloudflared\cloudflared.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $cloudflared) {
    Write-Host "Falta cloudflared: winget install --id Cloudflare.cloudflared" -ForegroundColor Red
    exit 1
}
if ($Registration) {
    Set-EnvValue "DATAFLOW_REGISTRATION_ENABLED" ($(if ($Registration -eq "on") { "true" } else { "false" }))
}

# 2. El túnel (se cierra el anterior: su dirección ya no sirve).
Write-Step "Abriendo el túnel de Cloudflare"
Stop-Tunnel
Remove-Item $logFile -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath $cloudflared `
    -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://localhost:3002" `
    -RedirectStandardError $logFile -WindowStyle Hidden -PassThru
Set-Content -Path $pidFile -Value $process.Id
$url = $null
for ($i = 0; $i -lt 60 -and -not $url; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $found = Select-String -Path $logFile -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" |
            Select-Object -First 1
        if ($found) { $url = $found.Matches[0].Value }
    }
    if ($process.HasExited) { break }
}
if (-not $url) {
    Write-Host "No se obtuvo la dirección del túnel. Registro: $logFile" -ForegroundColor Red
    Stop-Tunnel
    exit 1
}

# 3. La API acepta la dirección nueva.
Write-Step "Configurando la API para $url"
Set-EnvValue "DATAFLOW_PUBLIC_URL" $url
& docker @compose up -d *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se pudo levantar la aplicación: docker $($compose -join ' ') up -d" -ForegroundColor Red
    exit 1
}
for ($i = 0; $i -lt 60; $i++) {
    $health = docker inspect -f "{{.State.Health.Status}}" dataflow-api-1 2>$null
    if ($health -eq "healthy") { break }
    Start-Sleep -Seconds 2
}

# 4. La cadena entera desde fuera: 401 en /auth/me = web, proxy y API responden.
Write-Step "Comprobando la dirección pública"
$ok = $false
for ($i = 0; $i -lt 30 -and -not $ok; $i++) {
    try {
        Invoke-WebRequest -Uri "$url/api/v1/auth/me" -UseBasicParsing -TimeoutSec 10 | Out-Null
        $ok = $true
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 401) { $ok = $true }
        else { Start-Sleep -Seconds 2 }
    }
}
$registro = if (Test-Path $envFile) {
    (Select-String -Path $envFile -Pattern "^DATAFLOW_REGISTRATION_ENABLED=false" -Quiet)
} else { $false }

Write-Host ""
if ($ok) {
    Write-Host "DataFlow AI está publicado en:" -ForegroundColor Green
} else {
    Write-Host "El túnel está abierto pero todavía no responde; prueba en un minuto:" -ForegroundColor Yellow
}
Write-Host "  $url" -ForegroundColor White
Write-Host ""
Write-Host "Registro de cuentas nuevas: $(if ($registro) { 'cerrado' } else { 'abierto (ciérralo con -Registration off)' })"
Write-Host "El equipo debe seguir encendido con Docker abierto. Para cerrarlo: tunnel.ps1 -Stop"
