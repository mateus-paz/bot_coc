"""Caso de uso para salvar configuracao local."""

from __future__ import annotations


class SaveSettingsUseCase:
    """Encapsula persistencia de settings."""

    def __init__(self, setup_service) -> None:
        self.setup_service = setup_service

    def execute(self, settings) -> None:
        self.setup_service.save_settings(settings)

