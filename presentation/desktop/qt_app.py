"""Inicializacao da aplicacao Qt."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from presentation.desktop.main_window import MainWindow


def run_desktop_app(*, setup_service, automation_service) -> int:
    """Sobe a aplicacao Qt principal."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(setup_service=setup_service, automation_service=automation_service)
    window.show()
    return app.exec()
