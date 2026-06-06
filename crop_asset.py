#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from utils.image_utils import escrever_png, ler_imagem_bgr, recortar_imagem


def main() -> int:
    parser = argparse.ArgumentParser(description='Recorta um asset PNG a partir de screenshot.')
    parser.add_argument('--input', required=True, help='Screenshot de entrada.')
    parser.add_argument('--output', required=True, help='PNG de saida.')
    parser.add_argument('--x', type=int, required=True)
    parser.add_argument('--y', type=int, required=True)
    parser.add_argument('--w', type=int, required=True)
    parser.add_argument('--h', type=int, required=True)
    args = parser.parse_args()

    origem = Path(args.input)
    destino = Path(args.output)
    destino.parent.mkdir(parents=True, exist_ok=True)

    imagem = ler_imagem_bgr(origem)
    if imagem is None:
        print(f'Nao consegui ler a imagem: {origem}')
        return 1

    recorte = recortar_imagem(imagem, x=args.x, y=args.y, w=args.w, h=args.h)
    if recorte.size == 0:
        print('Recorte invalido.')
        return 1

    if not escrever_png(destino, recorte):
        print(f'Nao consegui codificar a imagem de saida: {destino}')
        return 1
    print(f'Asset salvo em: {destino}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
