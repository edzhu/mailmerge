# UI App (Python)

Minimal Python workspace for building macOS and Windows UI executables using PyInstaller.

## Installation
- Python 3.9+ (recommended 3.11)
```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```
Keep secrets out of the repository. If you add integrations that require credentials,
provide them via environment variables (for example, `export APP_SECRET="..."`) and
avoid committing them to source control.

## Running the CLI (dry-run)
The default CLI path is a dry-run that prints a status message and exits.
```bash
python -m app.main
```

## Running the GUI (optional, requires PySide6)
```bash
pip install PySide6
python -m app.main --gui
```
If PySide6 is not installed, the CLI will report the missing dependency and exit.

## Offline-safe testing
```bash
pytest -q
```
Tests are expected to run without network access; avoid adding tests that call out
to external services.

## Packaging (PyInstaller)
Use the helper scripts, which create a virtual environment, install dependencies,
and run PyInstaller:
- `scripts/build_macos.sh`
- `scripts/build_windows.ps1`

Manual command (both platforms):
```bash
pyinstaller --onefile --windowed --name UIApp src/app/main.py
```
The output executable will be in `dist/` (macOS) or `dist\UIApp.exe` (Windows).
