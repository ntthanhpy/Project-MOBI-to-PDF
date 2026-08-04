#!/usr/bin/env sh
set -eu

if ! command -v ebook-convert >/dev/null 2>&1; then
  echo "Calibre ebook-convert is not installed or not in PATH." >&2
  exit 1
fi

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
