"""Utilitario isolado para validar zoom in/out na janela alvo."""

from __future__ import annotations

import argparse
import logging
import time

from config import carregar_configuracao_runtime, resolver_caminho_config
from clients.window_client import encontrar_janela
from utils.input_actions import rolar_relativo


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Valida zoom in e zoom out na janela alvo.')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--cv', help='perfil CV opcional para carregar o config final')
    parser.add_argument('--zoom-in-clicks', type=int, default=10)
    parser.add_argument('--zoom-out-clicks', type=int, default=10)
    parser.add_argument('--settle-seconds', type=float, default=1.2)
    parser.add_argument('--dry-run', action='store_true')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

    caminho_config = resolver_caminho_config(args.config)
    cfg = carregar_configuracao_runtime(caminho_config, args.cv)

    titulo = str(cfg['window']['title_contains'])
    match_mode = str(cfg['window'].get('title_match_mode', 'contains'))
    activate = bool(cfg['window'].get('activate_before_click', True))
    duration = float(cfg.get('clicking', {}).get('move_duration_seconds', 0.04))

    logging.info('Localizando janela alvo titulo=%r match_mode=%s', titulo, match_mode)
    janela = encontrar_janela(titulo, ativar=activate, modo_comparacao=match_mode)
    logging.info(
        'Janela localizada titulo=%r pos=(%s,%s) tamanho=%sx%s',
        janela.titulo,
        janela.esquerda,
        janela.topo,
        janela.largura,
        janela.altura,
    )

    if activate:
        time.sleep(0.3)

    logging.info('Executando zoom in clicks=%s', args.zoom_in_clicks)
    rolar_relativo(
        janela,
        clicks=abs(int(args.zoom_in_clicks)),
        dry_run=bool(args.dry_run),
        duration=duration,
    )
    time.sleep(args.settle_seconds)

    logging.info('Executando zoom out clicks=%s', args.zoom_out_clicks)
    rolar_relativo(
        janela,
        clicks=-abs(int(args.zoom_out_clicks)),
        dry_run=bool(args.dry_run),
        duration=duration,
    )
    time.sleep(args.settle_seconds)

    logging.info('Validacao de zoom concluida.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
