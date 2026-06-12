"""Testes da ordem de preparacao da vila antes do deploy."""

from __future__ import annotations

import unittest

from services.bot_flow import BotFlowMixin


class _FlowHarness(BotFlowMixin):
    def __init__(self) -> None:
        self.cfg = {
            'flow': {
                'target_mode': 'direct_attack',
                'battle_screen_delay_seconds': 5,
                'pre_search_step_timeouts': {},
                'pre_search_step_after_delays': {},
            }
        }
        self.pre_search_steps = []
        self.optional_pre_search_steps = set()
        self.after_button = 0.5
        self.events: list[str] = []

    def checkpoint_controle(self) -> None:
        return None

    def dormir_interrompivel(self, seconds: float) -> None:
        self.events.append(f'sleep:{seconds}')

    def normalizar_zoom_batalha(self) -> None:
        self.events.append('zoom_out')

    def filtro_saque_ativo(self) -> bool:
        return False

    def ler_saque_ataque(self):
        self.events.append('loot')
        return {}

    def executar_deploy(self) -> None:
        self.events.append('deploy')

    def aguardar_fim_acao(self) -> None:
        self.events.append('wait_end')

    def retornar_inicio(self) -> None:
        self.events.append('return')


class BotFlowTest(unittest.TestCase):
    def test_zoom_out_happens_before_loot_and_deploy(self) -> None:
        harness = _FlowHarness()

        harness.executar_um_ciclo()

        self.assertLess(harness.events.index('zoom_out'), harness.events.index('loot'))
        self.assertLess(harness.events.index('zoom_out'), harness.events.index('deploy'))


if __name__ == '__main__':
    unittest.main()
