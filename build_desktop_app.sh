#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_EXE="$ROOT_DIR/.venv/Scripts/python.exe"
SPEC_FILE="infrastructure/packaging/pyinstaller/playgames_bot.spec"

if [[ ! -f "$PYTHON_EXE" ]]; then
  echo "[ERRO] Python da virtualenv nao encontrado em .venv/Scripts/python.exe"
  echo "Crie a virtualenv e instale as dependencias antes de rodar este build."
  exit 1
fi

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "[ERRO] Arquivo spec nao encontrado: $SPEC_FILE"
  exit 1
fi

echo "[1/5] Verificando PyInstaller..."
if ! "$PYTHON_EXE" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller nao encontrado. Instalando..."
  "$PYTHON_EXE" -m pip install pyinstaller
fi

echo "[2/5] Gerando icone do Windows..."
"$PYTHON_EXE" "$ROOT_DIR/infrastructure/packaging/generate_app_icon.py"

echo "[3/5] Limpando saidas anteriores..."
rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist"

echo "[4/5] Gerando executavel desktop..."
"$PYTHON_EXE" -m PyInstaller --noconfirm "$SPEC_FILE"

echo "[5/5] Build concluido."
echo "Executavel gerado em: $ROOT_DIR/dist/playgames-bot-desktop.exe"
echo "Pasta de saida: $ROOT_DIR/dist"
echo "Dados do usuario em runtime: %APPDATA%/PlayGamesBot"
