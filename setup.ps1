$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host

if (Test-Path "art.txt") {
    $ascii = Get-Content -Path "art.txt" -Encoding UTF8 -Raw
    Write-Host $ascii -ForegroundColor DarkMagenta
}

Write-Host "===================================================" -ForegroundColor Gray
Write-Host "    RR ALIADOS // ENVIRONMENT DIAGNOSTIC & SETUP" -ForegroundColor Magenta
Write-Host "===================================================`n" -ForegroundColor Gray

$faltanDependencias = $false

Write-Host "[1/5] Verificando Node.js..." -ForegroundColor Cyan
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ Node.js no detectado." -ForegroundColor Yellow
    Write-Host "    -> Descarga: https://nodejs.org/" -ForegroundColor Yellow
    Write-Host "    -> IMPORTANTE: Marca 'Add to PATH' durante la instalación." -ForegroundColor DarkGray
    $faltanDependencias = $true
} else {
    Write-Host "  ✔ Node.js detectado." -ForegroundColor Green
}

Write-Host "`n[2/5] Verificando gestor Python (UV)..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ UV no detectado." -ForegroundColor Yellow
    Write-Host "    -> Ejecuta este comando en una terminal nueva para instalarlo:" -ForegroundColor Yellow
    Write-Host "        powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'" -ForegroundColor DarkCyan
    $faltanDependencias = $true
} else {
    Write-Host "  ✔ UV detectado." -ForegroundColor Green
}

Write-Host "`n[3/5] Verificando Mosquitto Broker..." -ForegroundColor Cyan
$mosquittoPath = 'C:\Program Files\mosquitto\mosquitto.conf'

if (-not (Test-Path $mosquittoPath)) {
    Write-Host "  ⚠ Mosquitto Broker no encontrado." -ForegroundColor Yellow
    Write-Host "    -> Descarga (Windows 64-bit): https://mosquitto.org/download/" -ForegroundColor Yellow
    Write-Host "    -> IMPORTANTE: Instala como Administrador." -ForegroundColor DarkGray
    $faltanDependencias = $true
} else {
    $confContent = Get-Content $mosquittoPath -Raw
    if ($confContent -notmatch "listener 9001") {
        Write-Host "  Configurando WebSockets en puerto 9001..." -ForegroundColor Yellow
        Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File .\add_mosquitto_ws.ps1" -Wait
    }
    Write-Host "  ✔ Mosquitto configurado correctamente." -ForegroundColor Green
}

Write-Host "`n[4/5] Verificando Ollama e IA Local..." -ForegroundColor Cyan
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ Ollama no encontrado." -ForegroundColor Yellow
    Write-Host "    -> Descarga: https://ollama.com/download/windows" -ForegroundColor Yellow
    $faltanDependencias = $true
} else {
    Write-Host "  ✔ Ollama detectado." -ForegroundColor Green
    Write-Host "  Verificando modelo phi4-mini..." -ForegroundColor Gray
    $models = ollama list 2>$null | Out-String
    if ($models -notmatch "phi4-mini") {
        Write-Host "  📥 Descargando modelo local phi4-mini (esto puede tomar un momento)..." -ForegroundColor Yellow
        ollama pull phi4-mini
    }
    Write-Host "  ✔ Modelo phi4-mini listo." -ForegroundColor Green
}

if ($faltanDependencias) {
    Write-Host "`n===================================================" -ForegroundColor Gray
    Write-Host " ❌ FALTAN DEPENDENCIAS BASE. Instala lo requerido," -ForegroundColor Red
    Write-Host " cierra esta terminal, ábrela de nuevo y reejecuta." -ForegroundColor Yellow
    Write-Host "===================================================`n" -ForegroundColor Gray
    exit
}

Write-Host "`n  Sincronizando entorno virtual de Python con UV..." -ForegroundColor Gray
uv sync

Write-Host "`n[5/5] Instalando dependencias del Frontend (React/Vite)..." -ForegroundColor Cyan
$frontendDir = Join-Path $PSScriptRoot "src\frontend\web"

if (Test-Path $frontendDir) {
    Push-Location $frontendDir
    npm install --silent
    Pop-Location
} else {
    Write-Host "  ❌ La ruta $frontendDir no existe." -ForegroundColor Red
}

Write-Host "`n===================================================" -ForegroundColor Gray
Write-Host "[✅ SUCCESS] TODO EL ENTORNO FUE CONFIGURADO." -ForegroundColor Green
Write-Host "Ejecuta 'uv run honcho start' o abre start_app.bat para despegar.`n" -ForegroundColor Yellow
