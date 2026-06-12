"""Inicializacao da aplicacao Qt."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from config import resolver_diretorio_bundle
from presentation.desktop.toolbar_window import ToolbarWindow


def run_desktop_app(*, setup_service, automation_service) -> int:
    """Sobe a aplicacao Qt principal."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('PlayGames Bot')
    icon_path = resolver_diretorio_bundle() / 'assets' / 'app_icon.png'
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    settings = setup_service.load_settings()
    try:
        target_window = setup_service.find_target_window(settings, activate=False)
    except Exception as exc:
        QMessageBox.critical(
            None,
            'Clash of Clans nao encontrado',
            f'Abra o Clash of Clans antes de iniciar o bot.\n\nDetalhes: {exc}',
        )
        return 1

    window = ToolbarWindow(
        setup_service=setup_service,
        automation_service=automation_service,
        settings=settings,
        target_window=target_window,
    )
    window.show()
    return app.exec()
