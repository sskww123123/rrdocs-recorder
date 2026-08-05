# setup.ps1 - Provisionamiento Zero-Friction RR ALIADOS
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host

# 0. Cargar Arte ASCII
if (Test-Path "art.txt") {
    $ascii = Get-Content -Path "art.txt" -Encoding UTF8 -Raw
    Write-Host $ascii -ForegroundColor DarkMagenta
}

Write-Host "===================================================" -ForegroundColor Gray
Write-Host "   RR ALIADOS // AUTOMATED ENVIRONMENT SETUP" -ForegroundColor Magenta
Write-Host "===================================================`n" -ForegroundColor Gray

# ---------------------------------------------------------
# 1. VERIFICAR E INSTALAR NODE.JS
# ---------------------------------------------------------
Write-Host "[1/5] Verificando Node.js..." -ForegroundColor Cyan
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ Node.js no detectado. Instalando vía Winget..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
    Write-Host "  ✔ Node.js detectado." -ForegroundColor Green
}

# ---------------------------------------------------------
# 2. VERIFICAR E INSTALAR UV (PYTHON)
# ---------------------------------------------------------
Write-Host "`n[2/5] Verificando gestor Python (UV)..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ UV no detectado. Instalando automáticamente..." -ForegroundColor Yellow
    pip install uv --quiet
}
Write-Host "  Sincronizando entorno virtual de Python con UV..." -ForegroundColor Gray
uv sync

# ---------------------------------------------------------
# 3. VERIFICAR E INSTALAR MOSQUITTO BROKER
# ---------------------------------------------------------
Write-Host "`n[3/5] Verificando Mosquitto Broker..." -ForegroundColor Cyan
$mosquittoPath = 'C:\Program Files\mosquitto\mosquitto.conf'

if (-not (Test-Path $mosquittoPath)) {
    Write-Host "  ⚠ Mosquitto Broker no encontrado. Instalando vía Winget..." -ForegroundColor Yellow
    winget install EclipseFoundation.Mosquitto --accept-source-agreements --accept-package-agreements
}

if (Test-Path $mosquittoPath) {
    $confContent = Get-Content $mosquittoPath -Raw
    if ($confContent -notmatch "listener 9001") {
        Write-Host "  Configurando WebSockets en puerto 9001..." -ForegroundColor Yellow
        Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File .\add_mosquitto_ws.ps1" -Wait
    }
    Write-Host "  ✔ Mosquitto configurado correctamente." -ForegroundColor Green
}

# ---------------------------------------------------------
# 4. VERIFICAR E INSTALAR OLLAMA Y DESCARGAR MODELO PHI4-MINI
# ---------------------------------------------------------
Write-Host "`n[4/5] Verificando Ollama e IA Local..." -ForegroundColor Cyan
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "  ⚠ Ollama no encontrado. Instalando vía Winget..." -ForegroundColor Yellow
    winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "  Verificando modelo phi4-mini..." -ForegroundColor Gray
    $models = ollama list
    if ($models -notmatch "phi4-mini") {
        Write-Host "  📥 Descargando modelo local phi4-mini (esto puede tomar un momento)..." -ForegroundColor Yellow
        ollama pull phi4-mini
    }
    Write-Host "  ✔ Modelo phi4-mini listo." -ForegroundColor Green
}

# ---------------------------------------------------------
# 5. INSTALAR DEPENDENCIAS FRONTEND
# ---------------------------------------------------------
Write-Host "`n[5/5] Instalando dependencias del Frontend (React/Vite)..." -ForegroundColor Cyan
Push-Location src/frontend/web
npm install --silent
Pop-Location

Write-Host "`n===================================================" -ForegroundColor Gray
Write-Host "[✅ SUCCESS] TODO EL ENTORNO FUE CONFIGURADO." -ForegroundColor Green
Write-Host "Ejecuta 'uv run honcho start' o abre start_app.bat para despegar.`n" -ForegroundColor Yellow