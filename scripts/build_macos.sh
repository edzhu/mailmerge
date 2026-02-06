#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
pip install -e ".[build]"
pip install -e ".[build,gui]"

pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py

echo "Build complete. See dist/UIApp"
