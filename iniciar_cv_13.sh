#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt

python main.py --config config.yaml --cv cv_13
