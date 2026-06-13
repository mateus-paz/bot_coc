"""Testes do filtro de saque em batalha."""

from __future__ import annotations

import unittest

from services.bot_targeting import BotTargetingMixin


class _TargetingHarness(BotTargetingMixin):
    def __init__(self) -> None:
        self.cfg = {
            'flow': {
                'attack_loot_minimums': {
                    'gold': 500000,
                    'elixir': 500000,
                },
                'attack_loot_total_minimum': 1000000,
            }
        }


class BotTargetingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = _TargetingHarness()

    def test_approves_when_gold_and_elixir_reach_five_hundred_k_each(self) -> None:
        self.assertTrue(
            self.harness.saque_aprovado({'gold': 500000, 'elixir': 500000})
        )

    def test_approves_when_one_resource_reaches_one_million(self) -> None:
        self.assertTrue(
            self.harness.saque_aprovado({'gold': 1000000, 'elixir': 0})
        )

    def test_rejects_when_total_is_below_one_million(self) -> None:
        self.assertFalse(
            self.harness.saque_aprovado({'gold': 700000, 'elixir': 299999})
        )

    def test_rejects_when_both_resources_stay_below_individual_minimums(self) -> None:
        self.assertFalse(
            self.harness.saque_aprovado({'gold': 499999, 'elixir': 499999})
        )

    def test_approves_when_total_reaches_one_million_and_one_resource_crosses_minimum(self) -> None:
        self.assertTrue(
            self.harness.saque_aprovado({'gold': 500001, 'elixir': 499999})
        )


if __name__ == '__main__':
    unittest.main()
