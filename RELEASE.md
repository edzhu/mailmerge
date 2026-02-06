# Release Build Guide (Standalone executables)

## 1) Scope / what this produces
- Builds `UIApp` (macOS) and `UIApp.exe` (Windows) using PyInstaller.
- Output artifacts land under `dist/`.
- Intermediate build files land under `build/`.
- Builds must be performed on the target OS and architecture (no cross-compilation).

## 2) Prerequisites
- Git.
- Python **3.9–3.12** (the repo requires `>=3.9,<4.0`). **3.11** is recommended to match the repo’s development defaults.
- `pip` (bundled with Python).
- Windows: PowerShell.

Note on GUI dependencies (PyInstaller analysis): the build scripts only install the `.[build]` extra. If PyInstaller errors mention missing Qt/PySide6, or the GUI fails to launch, rebuild using `.[build,gui]` (see the build sections for exact commands).

## 3) Pick the source revision
```bash
git fetch --tags
git checkout <tag-or-commit>
# working tree should be clean
git status --porcelain
```
The canonical version string is `project.version` in `pyproject.toml` (use it for artifact names).
```bash
python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"
```
If you are on Python 3.9/3.10, open `pyproject.toml` and read `project.version` directly.

## 4) Run tests (required gate)
Tests are designed to run offline (no network calls).

macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
pytest -q
```

Windows (PowerShell):
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest -q
```

## 5) Build: macOS
Primary build command:
```bash
bash scripts/build_macos.sh
```
Artifacts land under `dist/` (either `dist/UIApp` or `dist/UIApp.app`).

Smoke tests (works for either a binary or an app bundle):
```bash
# Help output
if [ -d "dist/UIApp.app" ]; then
  ./dist/UIApp.app/Contents/MacOS/UIApp --help
else
  ./dist/UIApp --help
fi

# GUI launch
if [ -d "dist/UIApp.app" ]; then
  open "dist/UIApp.app" --args --gui
else
  ./dist/UIApp --gui
fi
```

If PyInstaller reports missing PySide6/Qt or the GUI fails to start, rebuild with the GUI extra:
```bash
rm -rf .venv build dist
python -m venv .venv
source .venv/bin/activate
pip install -e ".[build,gui]"
pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py
```

## 6) Build: Windows (PowerShell)
Primary build command:
```powershell
.\scripts\build_windows.ps1
```
If PowerShell blocks script execution, run the following in the same shell and retry:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Smoke tests:
```powershell
.\dist\UIApp.exe --help
.\dist\UIApp.exe --gui
```

If PyInstaller reports missing PySide6/Qt or the GUI fails to start, rebuild with the GUI extra:
```powershell
Remove-Item -Recurse -Force .venv, build, dist
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[build,gui]"
pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py
```

## 7) Packaging artifacts for distribution
Naming convention: `mailmerge-v<VERSION>-<os>-<arch>.zip`.

macOS example:
```bash
VERSION=<project.version>
ARCH=$(uname -m)
zip -r "mailmerge-v${VERSION}-macos-${ARCH}.zip" dist/UIApp*
shasum -a 256 "mailmerge-v${VERSION}-macos-${ARCH}.zip" > "mailmerge-v${VERSION}-macos-${ARCH}.zip.sha256"
```

Windows (PowerShell) example:
```powershell
$Version = "<project.version>"
$Arch = $env:PROCESSOR_ARCHITECTURE
Compress-Archive -Path dist\UIApp.exe -DestinationPath "mailmerge-v$Version-windows-$Arch.zip"
Get-FileHash -Algorithm SHA256 "mailmerge-v$Version-windows-$Arch.zip" | Format-List
```

## 8) (Optional) Signing / notarization
- macOS: sign the binary or app bundle with `codesign`, then submit for notarization (e.g., `notarytool`) and staple the ticket. Use your organization’s Apple Developer credentials and provisioning workflow.
- Windows: sign `UIApp.exe` with Authenticode using `signtool` and your organization’s code-signing certificate.
