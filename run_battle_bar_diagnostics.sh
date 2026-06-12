#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_EXE="$ROOT_DIR/.venv/Scripts/python.exe"
INPUT_DIR="$ROOT_DIR/tmp/battle_bar_inputs"
OUTPUT_DIR="$ROOT_DIR/tmp/battle_bar_diagnostics_batch"

if [[ ! -f "$PYTHON_EXE" ]]; then
  echo "[ERRO] Python da virtualenv nao encontrado em .venv/Scripts/python.exe"
  echo "Crie a virtualenv e instale as dependencias antes de rodar este script."
  exit 1
fi

mkdir -p "$INPUT_DIR"
mkdir -p "$OUTPUT_DIR"

shopt -s nullglob
IMAGES=(
  "$INPUT_DIR"/*.png
  "$INPUT_DIR"/*.jpg
  "$INPUT_DIR"/*.jpeg
  "$INPUT_DIR"/*.bmp
  "$INPUT_DIR"/*.webp
)
shopt -u nullglob

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  echo "[ERRO] Nenhuma imagem encontrada em: $INPUT_DIR"
  echo "Coloque screenshots nessa pasta e rode novamente."
  exit 1
fi

echo "[1/3] Pasta de entrada: $INPUT_DIR"
echo "[2/3] Pasta de saida: $OUTPUT_DIR"

for IMAGE_PATH in "${IMAGES[@]}"; do
  FILE_NAME="$(basename "$IMAGE_PATH")"
  BASE_NAME="${FILE_NAME%.*}"
  IMAGE_OUT_DIR="$OUTPUT_DIR/$BASE_NAME"

  echo ""
  echo "[3/3] Processando: $FILE_NAME"
  "$PYTHON_EXE" diagnose_battle_bar_image.py \
    --image "$IMAGE_PATH" \
    --out-dir "$IMAGE_OUT_DIR"
done

echo ""
echo "Diagnostico concluido."
echo "Imagens de entrada: $INPUT_DIR"
echo "Artefatos gerados em: $OUTPUT_DIR"
