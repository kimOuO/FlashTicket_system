$venvPython = ".\venv\Scripts\python.exe"`nif (Test-Path $venvPython) { & $venvPython main_auto_ocr.py } else { Write-Host "Please run install.ps1 first." -ForegroundColor Red }
