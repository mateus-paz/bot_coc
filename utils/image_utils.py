"""Utilitarios simples para desenho, leitura e escrita de imagens."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def desenhar_grade(imagem: np.ndarray, passo: int = 100) -> np.ndarray:
    """Desenha uma grade de referencia sobre a imagem informada."""
    saida = imagem.copy()
    altura, largura = saida.shape[:2]
    for x in range(0, largura, passo):
        cv2.line(saida, (x, 0), (x, altura), (220, 220, 220), 1)
        cv2.putText(saida, str(x), (x + 4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3)
        cv2.putText(saida, str(x), (x + 4, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    for y in range(0, altura, passo):
        cv2.line(saida, (0, y), (largura, y), (220, 220, 220), 1)
        cv2.putText(saida, str(y), (8, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 3)
        cv2.putText(saida, str(y), (8, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
    return saida


def ler_imagem_bgr(caminho: Path) -> np.ndarray | None:
    """Le uma imagem do disco em formato BGR."""
    bruto = np.fromfile(str(caminho), dtype=np.uint8)
    return cv2.imdecode(bruto, cv2.IMREAD_COLOR)


def escrever_png(caminho: Path, imagem: np.ndarray) -> bool:
    """Escreve uma imagem PNG no disco retornando sucesso ou falha."""
    ok, codificada = cv2.imencode('.png', imagem)
    if not ok:
        return False
    codificada.tofile(str(caminho))
    return True


def recortar_imagem(imagem: np.ndarray, *, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Recorta uma subimagem protegendo os limites da imagem original."""
    altura_imagem, largura_imagem = imagem.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(largura_imagem, x + w)
    y2 = min(altura_imagem, y + h)
    return imagem[y1:y2, x1:x2]
