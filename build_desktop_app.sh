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

echo "[1/4] Verificando PyInstaller..."
if ! "$PYTHON_EXE" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller nao encontrado. Instalando..."
  "$PYTHON_EXE" -m pip install pyinstaller
fi

echo "[2/4] Limpando saidas anteriores..."
rm -rf "$ROOT_DIR/build" "$ROOT_DIR/dist"

echo "[3/4] Gerando executavel desktop..."
"$PYTHON_EXE" -m PyInstaller --noconfirm "$SPEC_FILE"

echo "[4/4] Build concluido."
echo "Executavel gerado em: $ROOT_DIR/dist/playgames-bot-desktop.exe"
echo "Pasta de saida: $ROOT_DIR/dist"
echo "Dados do usuario em runtime: %APPDATA%/PlayGamesBot"
