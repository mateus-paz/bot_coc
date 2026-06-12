"""Bootstrap de dependencias do app desktop."""

from __future__ import annotations

from application.services.automation_service import DesktopAutomationService
from application.services.setup_service import SetupService
from infrastructure.capture.mss_capture import MSSScreenCapture
from infrastructure.persistence.settings_repository import AppDataSettingsRepository
from infrastructure.runtime_config import RuntimeConfigBuilder
from infrastructure.vision.opencv_battle_bar_analyzer import OpenCvBattleBarAnalyzerAdapter
from infrastructure.window.pygetwindow_locator import PyGetWindowLocator
from presentation.desktop.qt_app import run_desktop_app
from utils.tesseract_runtime import configure_tesseract_runtime

from config import resolver_diretorio_bundle


def bootstrap_desktop_app() -> int:
    """Monta dependencias concretas e inicia a UI."""
    configure_tesseract_runtime()
    settings_repository = AppDataSettingsRepository()
    window_locator = PyGetWindowLocator()
    screen_capture = MSSScreenCapture()
    battle_bar_analyzer = OpenCvBattleBarAnalyzerAdapter(asset_base_dir=resolver_diretorio_bundle())
    setup_service = SetupService(
        window_locator=window_locator,
        screen_capture=screen_capture,
        battle_bar_analyzer=battle_bar_analyzer,
        settings_repository=settings_repository,
    )
    runtime_config_builder = RuntimeConfigBuilder(repository=settings_repository)
    automation_service = DesktopAutomationService(
        settings_repository=settings_repository,
        runtime_config_builder=runtime_config_builder,
    )
    return run_desktop_app(setup_service=setup_service, automation_service=automation_service)
