"""Testes das acoes de entrada usadas para normalizar a vila."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from clients.window_client import JanelaRetangulo
from utils.input_actions import rolar_relativo


class InputActionsTest(unittest.TestCase):
    @patch('utils.input_actions.pyautogui.scroll')
    @patch('utils.input_actions.pyautogui.moveTo')
    def test_scroll_uses_window_center(self, move_to, scroll) -> None:
        window = JanelaRetangulo(
            titulo='Clash of Clans',
            esquerda=100,
            topo=50,
            largura=1600,
            altura=900,
        )

        rolar_relativo(window, clicks=-12, dry_run=False, duration=0.04)

        move_to.assert_called_once_with(900, 500, duration=0.04)
        scroll.assert_called_once_with(-12)


if __name__ == '__main__':
    unittest.main()
