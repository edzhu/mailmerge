#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/bin/activate
pip install -e ".[build]"

pyinstaller --onefile --windowed --name UIApp src/mailmerge/main.py

echo "Build complete. See dist/UIApp"
