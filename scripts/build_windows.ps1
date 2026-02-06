$ErrorActionPreference = "Stop"

python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py

Write-Host "Build complete. See dist\UIApp.exe"
