"""Operacoes geometricas usadas na resolucao de ROIs e pontos relativos."""

from __future__ import annotations

import random
from typing import Any

import numpy as np


def resolver_roi(tamanho: tuple[int, int], cfg_roi: dict[str, Any]) -> tuple[int, int, int, int]:
    """Converte uma ROI absoluta ou relativa em coordenadas normalizadas da tela."""
    largura_tela, altura_tela = tamanho
    if 'x_ratio' in cfg_roi:
        x = int(float(cfg_roi['x_ratio']) * largura_tela)
        y = int(float(cfg_roi['y_ratio']) * altura_tela)
        w = int(float(cfg_roi['w_ratio']) * largura_tela)
        h = int(float(cfg_roi['h_ratio']) * altura_tela)
    else:
        x = int(cfg_roi['x'])
        y = int(cfg_roi['y'])
        w = int(cfg_roi['w'])
        h = int(cfg_roi['h'])
    x = max(0, min(largura_tela - 1, x))
    y = max(0, min(altura_tela - 1, y))
    w = max(1, min(largura_tela - x, w))
    h = max(1, min(altura_tela - y, h))
    return x, y, w, h


def resolver_ponto(tamanho: tuple[int, int], cfg_ponto: dict[str, Any]) -> tuple[int, int]:
    """Converte um ponto absoluto ou relativo em coordenadas seguras da tela."""
    largura_tela, altura_tela = tamanho
    if 'x_ratio' in cfg_ponto:
        x = int(float(cfg_ponto['x_ratio']) * largura_tela)
        y = int(float(cfg_ponto['y_ratio']) * altura_tela)
    else:
        x = int(cfg_ponto['x'])
        y = int(cfg_ponto['y'])
    x = max(0, min(largura_tela - 1, x))
    y = max(0, min(altura_tela - 1, y))
    return x, y


def gerar_pontos_aleatorios_em_faixa(
    tamanho: tuple[int, int],
    *,
    cfg_inicio: dict[str, Any],
    cfg_fim: dict[str, Any],
    quantidade: int,
    meia_largura_px: float,
) -> list[tuple[int, int]]:
    """Gera pontos aleatorios ao longo de uma faixa entre dois pontos."""
    if quantidade <= 0:
        return []
    largura_tela, altura_tela = tamanho
    x1, y1 = resolver_ponto(tamanho, cfg_inicio)
    x2, y2 = resolver_ponto(tamanho, cfg_fim)
    delta_x = float(x2 - x1)
    delta_y = float(y2 - y1)
    comprimento = max(1.0, float(np.hypot(delta_x, delta_y)))
    normal_x = -delta_y / comprimento
    normal_y = delta_x / comprimento
    pontos: list[tuple[int, int]] = []
    for _ in range(quantidade):
        t = random.random()
        base_x = x1 + delta_x * t
        base_y = y1 + delta_y * t
        deslocamento = random.uniform(-meia_largura_px, meia_largura_px)
        px = int(round(base_x + normal_x * deslocamento))
        py = int(round(base_y + normal_y * deslocamento))
        px = max(0, min(largura_tela - 1, px))
        py = max(0, min(altura_tela - 1, py))
        pontos.append((px, py))
    return pontos


def extrair_roi(tela: np.ndarray, roi: dict[str, int]) -> np.ndarray:
    """Recorta uma subimagem a partir de uma ROI absoluta ou relativa."""
    altura, largura = tela.shape[:2]
    if 'x_ratio' in roi:
        x, y, rw, rh = resolver_roi((largura, altura), roi)
    else:
        x = max(0, int(roi['x']))
        y = max(0, int(roi['y']))
        rw = max(1, int(roi['w']))
        rh = max(1, int(roi['h']))
    return tela[y:min(altura, y + rh), x:min(largura, x + rw)]
