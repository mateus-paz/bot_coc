"""Testes unitarios para resolucao de slot_ref no deploy roteirizado."""

from __future__ import annotations

import unittest

from battle_bar.domain import (
    AvailabilityState,
    BattleBarSnapshot,
    BoundingBox,
    ContentState,
    SlotContent,
    SlotContentType,
    SlotLaneHint,
    SlotPosition,
)
from services.bot_deployment import BotDeploymentMixin


class _DeploymentHarness(BotDeploymentMixin):
    def checkpoint_controle(self) -> None:
        return None


def _slot(
    index: int,
    *,
    lane: SlotLaneHint,
    content_type: SlotContentType,
    availability: AvailabilityState,
    quantity_hint: int | None = None,
    selected: bool = False,
) -> SlotPosition:
    return SlotPosition(
        index=index,
        bbox=BoundingBox(x=100 + index * 10, y=200, w=40, h=40),
        lane_hint=lane,
        relative_x=0.0,
        content=SlotContent(
            content_id=f'slot-{index}',
            type=content_type,
            state=ContentState(availability=availability, selected=selected, confidence=0.9),
            name=f'{content_type.value}-{index}',
            quantity_hint=quantity_hint,
            confidence=0.95,
        ),
    )


class SlotRefResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = _DeploymentHarness()
        self.snapshot = BattleBarSnapshot(
            frame_id='frame-1',
            bar_bbox=BoundingBox(x=0, y=0, w=400, h=60),
            slots=(
                _slot(
                    0,
                    lane=SlotLaneHint.TROOP_SECTION,
                    content_type=SlotContentType.TROOP,
                    availability=AvailabilityState.AVAILABLE,
                    quantity_hint=8,
                ),
                _slot(
                    1,
                    lane=SlotLaneHint.TROOP_SECTION,
                    content_type=SlotContentType.TROOP,
                    availability=AvailabilityState.AVAILABLE,
                    quantity_hint=3,
                ),
                _slot(
                    2,
                    lane=SlotLaneHint.HERO_SECTION,
                    content_type=SlotContentType.HERO,
                    availability=AvailabilityState.USED,
                ),
                _slot(
                    3,
                    lane=SlotLaneHint.SPELL_SECTION,
                    content_type=SlotContentType.SPELL,
                    availability=AvailabilityState.AVAILABLE,
                    quantity_hint=2,
                ),
            ),
            timestamp=123.0,
        )

    def test_resolve_slot_ref_by_type_and_occurrence(self) -> None:
        slot = self.harness.resolver_slot_referencia(
            self.snapshot,
            {'content_type': 'troop', 'availability': 'available', 'occurrence': 2},
        )

        self.assertEqual(1, slot.index)

    def test_resolve_slot_ref_accepts_lane_alias_and_highest_quantity(self) -> None:
        slot = self.harness.resolver_slot_referencia(
            self.snapshot,
            {'lane': 'troops', 'availability': 'available', 'prefer': 'highest_quantity'},
        )

        self.assertEqual(0, slot.index)

    def test_resolve_slot_ref_raises_when_no_candidate_matches(self) -> None:
        with self.assertRaisesRegex(RuntimeError, 'Nenhum slot detectado corresponde'):
            self.harness.resolver_slot_referencia(
                self.snapshot,
                {'content_type': 'hero', 'availability': 'available'},
            )


if __name__ == '__main__':
    unittest.main()
