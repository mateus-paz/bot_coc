"""Cliente para descoberta de janela e captura de screenshot da aplicacao alvo."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw


@dataclass(frozen=True)
class JanelaRetangulo:
    """Retangulo e metadados da janela alvo."""

    titulo: str
    esquerda: int
    topo: int
    largura: int
    altura: int


class ErroJanela(RuntimeError):
    """Erro disparado quando a janela alvo nao pode ser encontrada ou usada."""


def titulo_janela_corresponde(titulo: str, esperado: str, modo_comparacao: str = 'contains') -> bool:
    """Compara o titulo da janela conforme o modo configurado."""
    titulo_normalizado = titulo.lower()
    esperado_normalizado = esperado.lower()
    if modo_comparacao == 'contains':
        return esperado_normalizado in titulo_normalizado
    if modo_comparacao == 'starts_with':
        return titulo_normalizado.startswith(esperado_normalizado)
    if modo_comparacao == 'exact':
        return titulo_normalizado == esperado_normalizado
    raise ErroJanela(f"window.title_match_mode invalido: {modo_comparacao}")


def obter_janela_ativa() -> JanelaRetangulo | None:
    """Retorna a janela atualmente focada, se existir."""
    janela = gw.getActiveWindow()
    if janela is None:
        return None
    return JanelaRetangulo(
        titulo=janela.title,
        esquerda=int(janela.left),
        topo=int(janela.top),
        largura=int(janela.width),
        altura=int(janela.height),
    )


def encontrar_janela(titulo_parcial: str, ativar: bool = True, modo_comparacao: str = 'contains') -> JanelaRetangulo:
    """Localiza a melhor janela candidata e opcionalmente a traz para frente."""
    correspondencias = [janela for janela in gw.getAllWindows() if titulo_janela_corresponde(janela.title, titulo_parcial, modo_comparacao)]
    if not correspondencias:
        raise ErroJanela(f"Nenhuma janela encontrada com match_mode={modo_comparacao!r} para: {titulo_parcial!r}")

    janela = max(correspondencias, key=lambda item: max(item.width, 0) * max(item.height, 0))
    if janela.width <= 0 or janela.height <= 0:
        raise ErroJanela('A janela encontrada esta minimizada ou sem tamanho valido.')

    if ativar:
        try:
            janela.activate()
        except Exception:
            pass

    return JanelaRetangulo(
        titulo=janela.title,
        esquerda=int(janela.left),
        topo=int(janela.top),
        largura=int(janela.width),
        altura=int(janela.height),
    )


def capturar_janela_bgr(retangulo: JanelaRetangulo) -> np.ndarray:
    """Captura a janela e converte a imagem para o formato BGR do OpenCV."""
    imagem = pyautogui.screenshot(region=(retangulo.esquerda, retangulo.topo, retangulo.largura, retangulo.altura))
    matriz_rgb = np.array(imagem)
    return cv2.cvtColor(matriz_rgb, cv2.COLOR_RGB2BGR)
