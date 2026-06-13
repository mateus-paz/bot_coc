"""Bootstrap de dependencias do app desktop."""

from __future__ import annotations

from application.services.automation_service import DesktopAutomationService
from application.services.setup_service import SetupService
from infrastructure.capture.mss_capture import MSSScreenCapture
from infrastructure.persistence.settings_repository import AppDataSettingsRepository
from infrastructure.runtime_config import RuntimeConfigBuilder
from infrastructure.window.pygetwindow_locator import PyGetWindowLocator
from presentation.desktop.qt_app import run_desktop_app
from config import carregar_configuracao_runtime, resolver_caminho_config
from utils.tesseract_runtime import warm_up_tesseract_runtime


def bootstrap_desktop_app() -> int:
    """Monta dependencias concretas e inicia a UI."""
    settings_repository = AppDataSettingsRepository()
    window_locator = PyGetWindowLocator()
    screen_capture = MSSScreenCapture()
    setup_service = SetupService(
        window_locator=window_locator,
        screen_capture=screen_capture,
        settings_repository=settings_repository,
    )
    runtime_config_builder = RuntimeConfigBuilder(repository=settings_repository)
    automation_service = DesktopAutomationService(
        settings_repository=settings_repository,
        runtime_config_builder=runtime_config_builder,
    )

    def startup_initializer() -> None:
        settings = settings_repository.load()
        cv_profile = None if settings is None else settings.cv_profile
        cfg = carregar_configuracao_runtime(resolver_caminho_config('config.yaml'), cv_profile)
        warm_up_tesseract_runtime(cfg)

    return run_desktop_app(
        setup_service=setup_service,
        automation_service=automation_service,
        startup_initializer=startup_initializer,
    )
