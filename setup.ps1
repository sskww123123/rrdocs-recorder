# setup.ps1 - Provisionamiento de Entorno RR ALIADOS
$ErrorActionPreference = "Stop"

# Forzar codificación UTF-8 en la consola de PowerShell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host

# Cargar y mostrar el arte ASCII desde el archivo externo con UTF-8
if (Test-Path "art.txt") {
    $ascii = Get-Content -Path "art.txt" -Encoding UTF8 -Raw
    Write-Host $ascii -ForegroundColor DarkMagenta
}

Write-Host "===================================================" -ForegroundColor Gray
Write-Host "   RR ALIADOS // GROWTH PARTNER OS PROVISIONING" -ForegroundColor Magenta
Write-Host "===================================================`n" -ForegroundColor Gray

# 1. UV Sync
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "[1/3] Sincronizando entorno virtual de Python con UV..." -ForegroundColor Cyan
    uv sync
} else {
    Write-Error "[ERROR] UV no está instalado. Ejecuta: pip install uv"
}

# 2. WebSockets en Mosquitto
$mosquittoConf = 'C:\Program Files\mosquitto\mosquitto.conf'
if (Test-Path $mosquittoConf) {
    Write-Host "[2/3] Verificando WebSockets en Mosquitto..." -ForegroundColor Cyan
    $confContent = Get-Content $mosquittoConf -Raw
    if ($confContent -notmatch "listener 9001") {
        Write-Host "Configurando WebSockets en puerto 9001..." -ForegroundColor Yellow
        Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File .\add_mosquitto_ws.ps1" -Wait
    }
}

# 3. NPM Install Frontend
Write-Host "[3/3] Instalando dependencias de React/Vite..." -ForegroundColor Cyan
Push-Location src/frontend/web
npm install
Pop-Location

Write-Host "`n[SUCCESS] ENTORNO LISTO PARA EJECUCION." -ForegroundColor Green
Write-Host "Ejecuta 'uv run honcho start' o abre start_app.bat para despegar.`n" -ForegroundColor Yellow