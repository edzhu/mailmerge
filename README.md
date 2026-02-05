# UI App (Python)

Minimal Python workspace for building macOS and Windows UI executables using PyInstaller.

## Requirements
- Python 3.9+ (recommended 3.11)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Run the app (development)
```bash
python -m app.main
```

## Build macOS executable
```bash
pyinstaller --onefile --windowed --name UIApp src/app/main.py
```
The output executable will be in `dist/`.

## Build Windows executable (PowerShell)
```powershell
pyinstaller --onefile --windowed --name UIApp src/app/main.py
```
The output executable will be in `dist/`.

## Helper scripts
- `scripts/build_macos.sh`
- `scripts/build_windows.ps1`

These scripts create a virtual environment, install dependencies, and run PyInstaller.
