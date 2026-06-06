#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyautogui

from clients.window_client import encontrar_janela
from config import carregar_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.yaml')
    args = parser.parse_args()

    cfg = carregar_yaml(Path(args.config))
    retangulo = encontrar_janela(cfg['window']['title_contains'], ativar=bool(cfg['window']['activate_before_click']))

    print(f"Janela: {retangulo.titulo!r}")
    print(f"left={retangulo.esquerda} top={retangulo.topo} width={retangulo.largura} height={retangulo.altura}")
    print('Pressione Ctrl+C para sair.')

    try:
        while True:
            x, y = pyautogui.position()
            relativo_x = x - retangulo.esquerda
            relativo_y = y - retangulo.topo
            dentro = 0 <= relativo_x <= retangulo.largura and 0 <= relativo_y <= retangulo.altura
            flag = 'DENTRO' if dentro else 'fora'
            print(f"\rabsoluto=({x:4d},{y:4d}) | relativo=({relativo_x:4d},{relativo_y:4d}) | {flag:6s}", end='', flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print('\nEncerrado.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
