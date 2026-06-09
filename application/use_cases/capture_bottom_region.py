"""Caso de uso para testar a captura da regiao inferior."""

from __future__ import annotations


class CaptureBottomRegionUseCase:
    """Encapsula a geracao do preview da regiao inferior."""

    def __init__(self, setup_service) -> None:
        self.setup_service = setup_service

    def execute(self, settings):
        return self.setup_service.capture_bottom_region_preview(settings)

