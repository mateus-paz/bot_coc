"""Servico para iniciar e controlar a automacao em background."""

from __future__ import annotations

from services.automacao_service import PlayGamesAppBot
from services.bot_controller import BotController


class DesktopAutomationService:
    """Adaptador entre a UI desktop e o bot existente."""

    def __init__(self, *, settings_repository, runtime_config_builder) -> None:
        self.settings_repository = settings_repository
        self.runtime_config_builder = runtime_config_builder
        self.controller = BotController()

    def start(self) -> bool:
        """Inicia a automacao em background."""
        settings = self.settings_repository.load()
        if settings is None:
            raise ValueError('Salve a configuracao antes de iniciar a automacao.')
        return self.controller.start(lambda: self._run(settings))

    def pause(self) -> bool:
        """Aborta o ciclo atual no proximo checkpoint seguro."""
        return self.controller.pause()

    def stop(self) -> bool:
        """Solicita encerramento da automacao."""
        return self.controller.stop()

    def status(self):
        """Retorna snapshot thread-safe do estado do worker."""
        return self.controller.snapshot()

    def _run(self, settings) -> None:
        cfg, caminho_template = self.runtime_config_builder.build(settings)
        PlayGamesAppBot(cfg, caminho_template, controller=self.controller).run()
