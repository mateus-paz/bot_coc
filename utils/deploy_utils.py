"""Funcoes puras usadas para calcular pontos de deploy e desenhar depuracao."""

from __future__ import annotations

from typing import Any, Iterable

import cv2
import numpy as np

from services.bot_shared import ErroBot


def mascara_vermelha(imagem_bgr: np.ndarray, cfg_mascara: dict[str, list[int]]) -> np.ndarray:
    """Gera mascara binaria para tons vermelhos em HSV."""
    hsv = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array(cfg_mascara['lower1'], dtype=np.uint8)
    upper1 = np.array(cfg_mascara['upper1'], dtype=np.uint8)
    lower2 = np.array(cfg_mascara['lower2'], dtype=np.uint8)
    upper2 = np.array(cfg_mascara['upper2'], dtype=np.uint8)
    return cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))


def ponto_proximo_da_mascara(mascara: np.ndarray, x: int, y: int, raio: int) -> bool:
    """Verifica se existe mascara ativa perto do ponto informado."""
    altura, largura = mascara.shape[:2]
    x1 = max(0, x - raio)
    x2 = min(largura, x + raio + 1)
    y1 = max(0, y - raio)
    y2 = min(altura, y + raio + 1)
    return bool(np.any(mascara[y1:y2, x1:x2] > 0))


def pontos_borda(largura: int, altura: int, margem: int, quantidade: int) -> list[tuple[int, int]]:
    """Gera pontos distribuidos na borda de um retangulo."""
    if quantidade <= 0:
        return []
    xs = np.linspace(margem, largura - margem, quantidade, dtype=int)
    ys = np.linspace(margem, altura - margem, quantidade, dtype=int)
    pontos: list[tuple[int, int]] = []
    for x in xs:
        pontos.append((int(x), margem))
    for y in ys:
        pontos.append((largura - margem, int(y)))
    for x in reversed(xs):
        pontos.append((int(x), altura - margem))
    for y in reversed(ys):
        pontos.append((margem, int(y)))
    vistos = set()
    unicos = []
    for ponto in pontos:
        if ponto not in vistos:
            unicos.append(ponto)
            vistos.add(ponto)
    return unicos


def intercalar_pontos(pontos: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Intercala inicio e fim da lista para espalhar a ordem de clique."""
    if len(pontos) <= 2:
        return pontos
    saida = []
    esquerda = 0
    direita = len(pontos) - 1
    while esquerda <= direita:
        saida.append(pontos[esquerda])
        if esquerda != direita:
            saida.append(pontos[direita])
        esquerda += 1
        direita -= 1
    return saida


def pontos_unicos(pontos: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove pontos duplicados preservando a ordem original."""
    vistos = set()
    unicos = []
    for ponto in pontos:
        if ponto not in vistos:
            unicos.append(ponto)
            vistos.add(ponto)
    return unicos


def pontos_cantos(largura: int, altura: int, margem: int) -> list[tuple[int, int]]:
    """Retorna os quatro cantos internos de um retangulo."""
    return [
        (margem, margem),
        (largura - margem, margem),
        (largura - margem, altura - margem),
        (margem, altura - margem),
    ]


def pontos_externos_borda_vermelha(mascara: np.ndarray, cfg_deploy: dict[str, Any]) -> list[tuple[int, int]]:
    """Amostra a borda vermelha e gera pontos ligeiramente para fora dela."""
    min_pixels = int(cfg_deploy.get('red_boundary_min_pixels', 80))
    ys, xs = np.where(mascara > 0)
    if len(xs) < min_pixels:
        return []

    altura, largura = mascara.shape[:2]
    centro_x = float(np.mean(xs))
    centro_y = float(np.mean(ys))
    deslocamento = float(cfg_deploy.get('red_boundary_outside_offset_px', 18))
    quantidade_amostras = int(cfg_deploy.get('red_boundary_sample_points', 96))
    angulos: dict[int, tuple[float, int, int]] = {}

    for x, y in zip(xs, ys):
        dx = float(x) - centro_x
        dy = float(y) - centro_y
        distancia = dx * dx + dy * dy
        angulo = (np.arctan2(dy, dx) + 2 * np.pi) % (2 * np.pi)
        bucket = int(angulo / (2 * np.pi) * quantidade_amostras)
        if bucket not in angulos or distancia > angulos[bucket][0]:
            angulos[bucket] = (distancia, int(x), int(y))

    pontos = []
    for bucket in sorted(angulos):
        _, x, y = angulos[bucket]
        dx = float(x) - centro_x
        dy = float(y) - centro_y
        norma = max(1.0, float(np.hypot(dx, dy)))
        px = int(round(x + (dx / norma) * deslocamento))
        py = int(round(y + (dy / norma) * deslocamento))
        px = max(0, min(largura - 1, px))
        py = max(0, min(altura - 1, py))
        pontos.append((px, py))

    return intercalar_pontos(pontos_unicos(pontos))


def pontos_candidatos_deploy(cfg_deploy: dict[str, Any], largura: int, altura: int) -> list[tuple[int, int]]:
    """Monta a lista base de candidatos de deploy conforme a estrategia configurada."""
    margem = int(cfg_deploy['border_margin_px'])
    pontos_por_lado = int(cfg_deploy['points_per_side'])
    ordem = cfg_deploy.get('candidate_order', 'corners_then_edges')
    cantos = pontos_cantos(largura, altura, margem)
    bordas = pontos_borda(largura=largura, altura=altura, margem=margem, quantidade=pontos_por_lado)
    if ordem == 'edges_only':
        return bordas
    if ordem == 'corners_only':
        return cantos
    if ordem != 'corners_then_edges':
        raise ErroBot(f'deployment.candidate_order invalido: {ordem}')
    return pontos_unicos([*cantos, *intercalar_pontos(bordas)])


def desenhar_pontos(imagem: np.ndarray, pontos: Iterable[tuple[int, int]]) -> np.ndarray:
    """Desenha pontos de debug sobre uma imagem."""
    saida = imagem.copy()
    for x, y in pontos:
        cv2.circle(saida, (x, y), 6, (255, 255, 255), 2)
    return saida


def desenhar_rois(imagem: np.ndarray, rois: Iterable[dict[str, int]]) -> np.ndarray:
    """Desenha ROIs de debug sobre uma imagem."""
    saida = imagem.copy()
    for roi in rois:
        x = int(roi['x'])
        y = int(roi['y'])
        w = int(roi['w'])
        h = int(roi['h'])
        cv2.rectangle(saida, (x, y), (x + w, y + h), (255, 255, 255), 2)
    return saida


def priorizar_pontos_deploy(pontos: list[tuple[int, int]], cfg_deploy: dict[str, Any], largura: int, altura: int) -> list[tuple[int, int]]:
    """Reordena os pontos de deploy de acordo com filtros e prioridades laterais."""
    min_y_ratio = float(cfg_deploy.get('min_deploy_y_ratio', 0.0))
    priorizar_lateral = bool(cfg_deploy.get('prioritize_lateral_deploy', False))
    faixa_lateral = float(cfg_deploy.get('lateral_band_ratio', 0.34))

    filtrados = [(x, y) for x, y in pontos if y >= int(altura * min_y_ratio)]
    if not filtrados:
        filtrados = pontos
    if not priorizar_lateral:
        return filtrados

    faixa = int(largura * faixa_lateral)
    esquerda = [(x, y) for x, y in filtrados if x <= faixa]
    direita = [(x, y) for x, y in filtrados if x >= largura - faixa]
    meio = [(x, y) for x, y in filtrados if faixa < x < largura - faixa]
    pontos_laterais = []
    esquerda_ordenada = intercalar_pontos(esquerda)
    direita_ordenada = intercalar_pontos(direita)
    for i in range(max(len(esquerda_ordenada), len(direita_ordenada))):
        if i < len(esquerda_ordenada):
            pontos_laterais.append(esquerda_ordenada[i])
        if i < len(direita_ordenada):
            pontos_laterais.append(direita_ordenada[i])
    return pontos_unicos([*pontos_laterais, *intercalar_pontos(meio)])
