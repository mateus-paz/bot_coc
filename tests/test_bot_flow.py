"""Testes da ordem de preparacao da vila antes do deploy."""

from __future__ import annotations

import unittest

from services.bot_flow import BotFlowMixin


class _FlowHarness(BotFlowMixin):
    def __init__(self, *, filtro_saque_ativo: bool = False) -> None:
        self.cfg = {
            'flow': {
                'target_mode': 'direct_attack',
                'battle_screen_delay_seconds': 5,
                'attack_loot_ready_timeout_seconds': 5,
                'pre_search_step_timeouts': {},
                'pre_search_step_after_delays': {},
            }
        }
        self.pre_search_steps = []
        self.optional_pre_search_steps = set()
        self.after_button = 0.5
        self.events: list[str] = []
        self._filtro_saque_ativo = filtro_saque_ativo

    def checkpoint_controle(self) -> None:
        return None

    def dormir_interrompivel(self, seconds: float) -> None:
        self.events.append(f'sleep:{seconds}')

    def normalizar_zoom_batalha(self) -> None:
        self.events.append('zoom_out')

    def filtro_saque_ativo(self) -> bool:
        return self._filtro_saque_ativo

    def encontrar_alvo_por_saque(self):
        self.events.append('loot_validated')
        return {'gold': 500000, 'elixir': 500000}

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
    def test_zoom_out_happens_after_loot_read_and_before_deploy(self) -> None:
        harness = _FlowHarness()

        harness.executar_um_ciclo()

        self.assertLess(harness.events.index('loot'), harness.events.index('zoom_out'))
        self.assertLess(harness.events.index('zoom_out'), harness.events.index('deploy'))

    def test_zoom_out_happens_after_validated_loot_and_before_deploy(self) -> None:
        harness = _FlowHarness(filtro_saque_ativo=True)

        harness.executar_um_ciclo()

        self.assertLess(harness.events.index('loot_validated'), harness.events.index('zoom_out'))
        self.assertLess(harness.events.index('zoom_out'), harness.events.index('deploy'))


if __name__ == '__main__':
    unittest.main()
