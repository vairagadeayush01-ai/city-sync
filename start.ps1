#!/usr/bin/env pwsh
# CitySync - Start all services
# Run from the project root: .\start.ps1

Write-Host ""
Write-Host "----------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "              CitySync - Civic Complaint Platform               " -ForegroundColor Cyan
Write-Host "----------------------------------------------------------------" -ForegroundColor Cyan
Write-Host ""

# -- Check .env ----------------------------------------------------------------
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "   OK: .env created (MOCK_AI=true)" -ForegroundColor Green
}

# -- Docker Check --------------------------------------------------------------
Write-Host "Docker Launch Option" -ForegroundColor Magenta
$runDocker = Read-Host "Do you want to start everything in Docker instead of local? (y/n)"
if ($runDocker -eq 'y') {
    Write-Host "🐳 Starting full CitySync stack in Docker..." -ForegroundColor Cyan
    docker-compose up --build
    exit
}

# -- Step 1: Start Docker infrastructure ---------------------------------------

Write-Host "Starting infrastructure (PostgreSQL, Redis, MinIO)..." -ForegroundColor Cyan
docker-compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker failed. Make sure Docker Desktop is running." -ForegroundColor Red
    exit 1
}
Write-Host "   OK: Waiting 8 seconds for services to be ready..." -ForegroundColor Green
Start-Sleep -Seconds 8

# -- Step 2: Install Python deps ------------------------------------------------
Write-Host "Installing Python backend dependencies..." -ForegroundColor Cyan
Set-Location backend

pip install -r ..\requirements.txt --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: pip install failed." -ForegroundColor Red
    exit 1
}
Write-Host "   OK: Python packages installed" -ForegroundColor Green

# -- Step 3: Initialize database ------------------------------------------------
Write-Host "Initializing database + PostGIS..." -ForegroundColor Cyan
python migrations/init_db.py
python migrations/seed_data.py
Write-Host "   OK: Database ready" -ForegroundColor Green

# -- Step 4: Start backend services --------------------------------------------
Write-Host "Starting backend services..." -ForegroundColor Cyan

# Gateway (port 8000) 
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m uvicorn gateway.main:socket_app --host 0.0.0.0 --port 8000 --reload" -WindowStyle Normal

# AI Pipeline consumer
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m ai_pipeline.main" -WindowStyle Normal

# Routing service (port 8001)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m uvicorn routing.main:app --host 0.0.0.0 --port 8001 --reload" -WindowStyle Normal

# Also start routing consumer
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m routing.main" -WindowStyle Normal

# Verification engine (port 8002)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m uvicorn verification.main:app --host 0.0.0.0 --port 8002 --reload" -WindowStyle Normal

# Notification service
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python -m notifications.main" -WindowStyle Normal

Set-Location ..

Write-Host "   OK: Backend services starting..." -ForegroundColor Green

# -- Step 5: Department portal --------------------------------------------------
Write-Host "Starting department portal..." -ForegroundColor Cyan
Set-Location dept-portal
if (-not (Test-Path "node_modules")) { npm install --silent }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; npm start" -WindowStyle Normal
Set-Location ..
Write-Host "   OK: Department portal starting..." -ForegroundColor Green

# -- Step 6: Frontend -----------------------------------------------------------
Write-Host "Starting React frontend..." -ForegroundColor Cyan
Set-Location frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "   Installing frontend packages (first run)..." -ForegroundColor Yellow
    npm install --silent
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; npm run dev" -WindowStyle Normal
Set-Location ..

# -- Done -----------------------------------------------------------------------
Write-Host ""
Write-Host "===============================================================" -ForegroundColor Green
Write-Host " CitySync is starting up! Services:" -ForegroundColor Green
Write-Host ""
Write-Host "   Citizen PWA        -> http://localhost:5173" -ForegroundColor White
Write-Host "   Gateway API        -> http://localhost:8000/docs" -ForegroundColor White
Write-Host "   Routing API        -> http://localhost:8001/docs" -ForegroundColor White
Write-Host "   Verification API   -> http://localhost:8002/docs" -ForegroundColor White
Write-Host "   Dept Portal        -> http://localhost:3000" -ForegroundColor White
Write-Host "   MinIO Console      -> http://localhost:9001" -ForegroundColor White
Write-Host ""
Write-Host " AI: MOCK_AI=true" -ForegroundColor Yellow
Write-Host " Notifications: MOCK_NOTIFICATIONS=true" -ForegroundColor Yellow
Write-Host "===============================================================" -ForegroundColor Green
Write-Host ""
