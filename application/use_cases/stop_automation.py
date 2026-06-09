"""Caso de uso para parar a automacao."""

from __future__ import annotations


class StopAutomationUseCase:
    """Encapsula o stop do worker."""

    def __init__(self, automation_service) -> None:
        self.automation_service = automation_service

    def execute(self) -> bool:
        return self.automation_service.stop()
