"""Ponto de entrada da tarefa principal de execucao do bot."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pyautogui

from config import carregar_configuracao_runtime, resolver_caminho_config
from services.automacao_service import ErroBot, PlayGamesAppBot
from services.bot_controller import BotController, BotStopRequested


def criar_parser() -> argparse.ArgumentParser:
    """Monta o parser de argumentos da CLI principal."""
    parser = argparse.ArgumentParser(description='QA visual para app proprio no Play Games.')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--cv', help='seleciona um perfil de estrategia/CV definido em cv_profiles')
    parser.add_argument('--preliminary', action='store_true', help='clica apenas flow.pre_search_steps e encerra')
    parser.add_argument('--deploy-now', action='store_true', help='solta tropas na tela atual sem clicar botoes iniciais')
    return parser


def executar_bot(
    caminho_config: str | Path = 'config.yaml',
    *,
    cv_profile: str | None = None,
    preliminary_only: bool = False,
    deploy_now: bool = False,
    controller: BotController | None = None,
) -> int:
    """Executa o fluxo principal de forma programatica e traduz excecoes conhecidas para codigos de saida."""
    caminho_config_resolvido = resolver_caminho_config(caminho_config)
    caminho_config = Path(caminho_config_resolvido)
    if not caminho_config.exists():
        print('Arquivo config.yaml nao encontrado. Copie config.example.yaml para config.yaml.')
        return 2

    try:
        cfg = carregar_configuracao_runtime(caminho_config, cv_profile)
        PlayGamesAppBot(
            cfg,
            caminho_config,
            preliminary_only=preliminary_only,
            deploy_now=deploy_now,
            controller=controller,
        ).run()
    except BotStopRequested:
        logging.info('Encerrado pelo controller.')
        return 0
    except KeyboardInterrupt:
        logging.info('Interrompido pelo usuario.')
        return 0
    except pyautogui.FailSafeException:
        logging.error('Fail-safe acionado: mouse no canto superior esquerdo.')
        return 1
    except (ErroBot, ValueError) as exc:
        logging.error('%s', exc)
        return 1
    return 0


def executar_fluxo(argv: list[str] | None = None) -> int:
    """Executa o fluxo principal via argumentos de linha de comando."""
    args = criar_parser().parse_args(argv)
    return executar_bot(
        args.config,
        cv_profile=args.cv,
        preliminary_only=args.preliminary,
        deploy_now=args.deploy_now,
    )
