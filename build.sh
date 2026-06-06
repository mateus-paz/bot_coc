#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_EXE="$ROOT_DIR/.venv/Scripts/python.exe"
if [[ ! -f "$PYTHON_EXE" ]]; then
  echo "[ERRO] Python da virtualenv nao encontrado em .venv/Scripts/python.exe"
  echo "Crie a virtualenv e instale as dependencias antes de rodar este build."
  exit 1
fi

echo "[1/3] Verificando PyInstaller..."
if ! "$PYTHON_EXE" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller nao encontrado. Instalando..."
  "$PYTHON_EXE" -m pip install pyinstaller
fi

echo "[2/3] Gerando executavel unico..."
"$PYTHON_EXE" -m PyInstaller \
  --noconfirm \
  --onefile \
  --windowed \
  --name playgames-bot-toolbar \
  --add-data "config.yaml;." \
  --add-data "assets;assets" \
  gui_main.py

echo "[3/3] Build concluido."
echo "Executavel unico gerado em: $ROOT_DIR/dist/playgames-bot-toolbar.exe"
echo "O config.yaml e os assets estao embutidos no proprio exe."
