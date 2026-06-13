"""Testes das acoes de entrada usadas para normalizar a vila."""

from __future__ import annotations

import unittest
from unittest.mock import call, patch

from clients.window_client import JanelaRetangulo
from utils.input_actions import rolar_relativo


class InputActionsTest(unittest.TestCase):
    @patch('utils.input_actions._scroll_mouse_wheel_windows')
    @patch('utils.input_actions.pyautogui.moveTo')
    def test_scroll_uses_window_center(self, move_to, scroll_native) -> None:
        window = JanelaRetangulo(
            titulo='Clash of Clans',
            esquerda=100,
            topo=50,
            largura=1600,
            altura=900,
        )

        rolar_relativo(window, clicks=-12, dry_run=False, duration=0.04)

        move_to.assert_called_once_with(900, 500, duration=0.04)
        self.assertEqual(12, scroll_native.call_count)
        scroll_native.assert_has_calls([call(-1)] * 12)


if __name__ == '__main__':
    unittest.main()
