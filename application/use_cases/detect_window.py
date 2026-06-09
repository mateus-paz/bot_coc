"""Caso de uso para localizar a janela alvo."""

from __future__ import annotations


class DetectWindowUseCase:
    """Encapsula a chamada de deteccao de janela."""

    def __init__(self, setup_service) -> None:
        self.setup_service = setup_service

    def execute(self, settings):
        return self.setup_service.detect_window(settings)

