"""Acoes de entrada do usuario simuladas pelo PyAutoGUI."""

from __future__ import annotations

import logging
import time

import pyautogui

from clients.window_client import JanelaRetangulo

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02


def clicar_relativo(retangulo: JanelaRetangulo, x: int, y: int, *, dry_run: bool, duration: float) -> None:
    """Clica em um ponto relativo a janela alvo."""
    absoluto_x = retangulo.esquerda + x
    absoluto_y = retangulo.topo + y
    if dry_run:
        logging.info('DRY-RUN clique relativo=(%s,%s) absoluto=(%s,%s)', x, y, absoluto_x, absoluto_y)
        return
    pyautogui.moveTo(absoluto_x, absoluto_y, duration=duration)
    pyautogui.click()


def pressionar_tecla(tecla: str, *, dry_run: bool, hold_seconds: float = 0.04) -> None:
    """Pressiona e solta uma tecla com pequena duracao configuravel."""
    logging.info('Pressionando tecla=%s', tecla)
    if dry_run:
        return
    pyautogui.keyDown(tecla)
    time.sleep(hold_seconds)
    pyautogui.keyUp(tecla)
