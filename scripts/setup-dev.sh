#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -c constraints.txt -e vendor/diplomacy
.venv/bin/python -m pip install -c constraints.txt -e '.[dev]'
