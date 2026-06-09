"""Planejadores simples baseados no snapshot da barra."""

from __future__ import annotations

from typing import Any

from battle_bar.domain import ActionableSlot, AvailabilityState, BattleBarSnapshot, SlotContentType


class DefaultActionPlanner:
    """Filtra e prioriza slots usaveis para uma futura acao."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def plan(self, snapshot: BattleBarSnapshot) -> list[ActionableSlot]:
        preferred_types = {
            SlotContentType(value)
            for value in self.config.get('preferred_types', ['troop', 'siege_machine', 'hero', 'spell'])
        }
        planned: list[ActionableSlot] = []
        for slot in snapshot.slots:
            if slot.content is None:
                continue
            if slot.content.state.availability != AvailabilityState.AVAILABLE:
                continue
            if slot.content.type not in preferred_types:
                continue
            planned.append(
                ActionableSlot(
                    slot_index=slot.index,
                    content_type=slot.content.type,
                    state=slot.content.state,
                    tap_point=slot.center,
                    priority=self._priority_for(slot.content.type),
                    content_name=slot.content.name,
                )
            )
        return sorted(planned, key=lambda item: (item.priority, item.slot_index))

    def _priority_for(self, content_type: SlotContentType) -> int:
        priorities: dict[SlotContentType, int] = {
            SlotContentType.TROOP: 10,
            SlotContentType.SIEGE_MACHINE: 20,
            SlotContentType.HERO: 30,
            SlotContentType.SPELL: 40,
            SlotContentType.UNKNOWN: 99,
        }
        return priorities.get(content_type, 99)
