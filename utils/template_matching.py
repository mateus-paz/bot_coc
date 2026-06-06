"""Rotinas de leitura de assets e busca de template na tela."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from services.bot_shared import Correspondencia, ErroBot


def ler_imagem(caminho: Path) -> np.ndarray:
    """Le um asset em BGR validando existencia e decodificacao."""
    if not caminho.exists():
        raise ErroBot(f'Asset nao encontrado: {caminho}')
    bruto = np.fromfile(str(caminho), dtype=np.uint8)
    imagem = cv2.imdecode(bruto, cv2.IMREAD_COLOR)
    if imagem is None:
        raise ErroBot(f'Nao consegui ler o asset: {caminho}')
    return imagem


def encontrar_template(tela: np.ndarray, asset: Path, confianca: float) -> Correspondencia | None:
    """Executa `matchTemplate` e retorna a melhor correspondencia acima do limiar."""
    template = ler_imagem(asset)
    if template.shape[0] > tela.shape[0] or template.shape[1] > tela.shape[1]:
        return None
    resultado = cv2.matchTemplate(tela, template, cv2.TM_CCOEFF_NORMED)
    _, valor_maximo, _, local_maximo = cv2.minMaxLoc(resultado)
    if valor_maximo < confianca:
        return None
    altura, largura = template.shape[:2]
    return Correspondencia(x=int(local_maximo[0]), y=int(local_maximo[1]), w=int(largura), h=int(altura), confidence=float(valor_maximo))
