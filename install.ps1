# Force TLS 1.2 for Github downloads
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "    FlashTicket Secure Setup Script (VENV)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. �إߨñҰʵ�������
Write-Host "1. Creating Python Virtual Environment (venv)..." -ForegroundColor Yellow
if (-not (Test-Path ".\venv")) {
    python -m venv venv
    Write-Host "-> Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "-> Virtual environment already exists." -ForegroundColor Green
}

# ����������Ҥ��� Python �M Pip ���|
$venvPython = ".\venv\Scripts\python.exe"
$venvPip = ".\venv\Scripts\pip.exe"
$venvPlaywright = ".\venv\Scripts\playwright.exe"

# 2. �b�������Ҥ��w�ˮM��
Write-Host "`n2. Installing Python Requirements in venv..." -ForegroundColor Yellow
& $venvPip install -r requirements.txt

# 3. �b�������Ҥ��w�� Playwright �s����
Write-Host "`n3. Installing Playwright Browsers in venv..." -ForegroundColor Yellow
& $venvPlaywright install chromium

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "    Secure Setup is complete!" -ForegroundColor Green
Write-Host "    To run the bot securely, just type:" -ForegroundColor Green
Write-Host "    .\run.ps1" -ForegroundColor Yellow
Write-Host "=============================================" -ForegroundColor Cyan
