#!/usr/bin/env bash
set -euo pipefail

python -m venv .venv
source .venv/Scripts/activate
python main.py --config config.yaml --cv cv_17
