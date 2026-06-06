#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

from clients.window_client import capturar_janela_bgr, encontrar_janela
from config import carregar_yaml, resolver_diretorio_debug
from utils.image_utils import desenhar_grade, escrever_png


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--step', type=int, default=100)
    args = parser.parse_args()

    caminho_config = Path(args.config).resolve()
    cfg = carregar_yaml(caminho_config)
    diretorio_debug = resolver_diretorio_debug(cfg, caminho_config)
    diretorio_debug.mkdir(parents=True, exist_ok=True)

    retangulo = encontrar_janela(cfg['window']['title_contains'], ativar=bool(cfg['window']['activate_before_click']))
    imagem = capturar_janela_bgr(retangulo)
    grade = desenhar_grade(imagem, passo=args.step)
    saida = diretorio_debug / f"screenshot_grade_{time.strftime('%Y%m%d-%H%M%S')}.png"
    if not escrever_png(saida, grade):
        raise RuntimeError(f'Falha ao codificar screenshot: {saida}')
    print(f'Salvo em: {saida}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
