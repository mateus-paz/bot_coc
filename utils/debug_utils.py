"""Funcoes auxiliares para logging e persistencia de imagens de debug."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from services.bot_shared import ErroBot


def configurar_logging(diretorio_debug: Path) -> None:
    """Configura logging em stdout e no arquivo `bot.log`."""
    diretorio_debug.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(diretorio_debug / 'bot.log', encoding='utf-8')],
    )


def salvar_debug(diretorio_debug: Path, nome: str, imagem_bgr: np.ndarray) -> Path:
    """Salva uma imagem PNG de debug com timestamp no nome."""
    saida = diretorio_debug / f"{time.strftime('%Y%m%d-%H%M%S')}_{nome}.png"
    ok, codificada = cv2.imencode('.png', imagem_bgr)
    if not ok:
        raise ErroBot(f'Nao consegui codificar imagem de debug: {saida}')
    codificada.tofile(str(saida))
    return saida
