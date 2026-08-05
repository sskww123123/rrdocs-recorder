# setup.ps1 - Provisionamiento Zero-Friction RR ALIADOS
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Clear-Host

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# 0. Cargar Arte ASCII
$asciiPath = Join-Path $PSScriptRoot "art.txt"
if (Test-Path $asciiPath) {
    $ascii = Get-Content -Path $asciiPath -Encoding UTF8 -Raw
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
    Write-Host "  > Node.js no detectado. Ejecutando Winget..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
    Refresh-Path
} 
Write-Host "  [OK] Node.js operativo." -ForegroundColor Green

# ---------------------------------------------------------
# 2. VERIFICAR E INSTALAR UV (PYTHON)
# ---------------------------------------------------------
Write-Host "`n[2/5] Verificando gestor Python (UV)..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  > UV no detectado. Ejecutando Winget..." -ForegroundColor Yellow
    winget install astral-sh.uv --accept-source-agreements --accept-package-agreements --silent
    Refresh-Path
}
Write-Host "  > Sincronizando entorno virtual..." -ForegroundColor Gray
# Forzamos invocación desde cmd para evitar desincronización de PATH
cmd.exe /c "uv sync"

# ---------------------------------------------------------
# 3. VERIFICAR E INSTALAR MOSQUITTO BROKER
# ---------------------------------------------------------
Write-Host "`n[3/5] Verificando Mosquitto Broker..." -ForegroundColor Cyan
$mosquittoPath = 'C:\Program Files\mosquitto\mosquitto.conf'

if (-not (Test-Path $mosquittoPath)) {
    Write-Host "  > Mosquitto no encontrado. Ejecutando Winget..." -ForegroundColor Yellow
    winget install EclipseFoundation.Mosquitto --accept-source-agreements --accept-package-agreements --silent
}

if (Test-Path $mosquittoPath) {
    $confContent = Get-Content $mosquittoPath -Raw
    if ($confContent -notmatch "listener 9001") {
        Write-Host "  > Configurando WebSockets (9001) y reiniciando servicio..." -ForegroundColor Yellow
        $scriptWs = Join-Path $PSScriptRoot "add_mosquitto_ws.ps1"
        
        # El script auxiliar ahora DEBE incluir el reinicio del servicio: Restart-Service -Name mosquitto
        $proc = Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -Command `"& '$scriptWs'; Restart-Service -Name mosquitto -ErrorAction SilentlyContinue`"" -Wait -PassThru
        
        if ($proc.ExitCode -ne 0) {
            Write-Host "  [FAIL] Inyección de configuración Mosquitto fallida." -ForegroundColor Red
        } else {
            Write-Host "  [OK] Mosquitto configurado y reiniciado." -ForegroundColor Green
        }
    } else {
        Write-Host "  [OK] Mosquitto ya configurado." -ForegroundColor Green
    }
}

# ---------------------------------------------------------
# 4. VERIFICAR E INSTALAR OLLAMA Y DESCARGAR MODELO PHI4-MINI
# ---------------------------------------------------------
Write-Host "`n[4/5] Verificando Ollama e IA Local..." -ForegroundColor Cyan
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "  > Ollama no encontrado. Ejecutando Winget..." -ForegroundColor Yellow
    winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
    Refresh-Path
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "  > Verificando estado del Daemon de Ollama..." -ForegroundColor Gray
    
    # Intento de arranque silencioso del servidor por si es una instalación limpia
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3 # Tiempo de buffer para que el puerto 11434 abra

    $models = ollama list 2>$null | Out-String
    if ($models -notmatch "phi4-mini") {
        Write-Host "  > Descargando tensor local phi4-mini..." -ForegroundColor Yellow
        ollama pull phi4-mini
    }
    Write-Host "  [OK] Modelo phi4-mini instanciado." -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Binario Ollama ilocalizable en sesión." -ForegroundColor Red
}

# ---------------------------------------------------------
# 5. INSTALAR DEPENDENCIAS FRONTEND
# ---------------------------------------------------------
Write-Host "`n[5/5] Construyendo árbol de dependencias Frontend..." -ForegroundColor Cyan
$frontendDir = Join-Path $PSScriptRoot "src\frontend\web"

if (Test-Path $frontendDir) {
    Push-Location $frontendDir
    cmd.exe /c "npm install --no-fund --no-audit"
    Pop-Location
    Write-Host "  [OK] Frontend empaquetado." -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Directorio $frontendDir inexistente." -ForegroundColor Red
}

Write-Host "`n===================================================" -ForegroundColor Gray
Write-Host "[ SYSTEM READY ] ENTORNO RR ALIADOS DEPLOYADO." -ForegroundColor Magenta
Write-Host "Lanza 'uv run honcho start' o ejecuta start_app.bat`n" -ForegroundColor Gray