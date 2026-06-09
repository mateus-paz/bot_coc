"""Caso de uso para iniciar a automacao."""

from __future__ import annotations


class StartAutomationUseCase:
    """Encapsula o start do worker da automacao."""

    def __init__(self, automation_service) -> None:
        self.automation_service = automation_service

    def execute(self) -> bool:
        return self.automation_service.start()

