"""Caso de uso para testar a deteccao dos slots."""

from __future__ import annotations


class DetectSlotsUseCase:
    """Encapsula o preview da deteccao de battle bar."""

    def __init__(self, setup_service) -> None:
        self.setup_service = setup_service

    def execute(self, settings):
        return self.setup_service.detect_slots_preview(settings)

