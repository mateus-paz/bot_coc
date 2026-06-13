"""Inicializacao da aplicacao Qt."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QVBoxLayout, QWidget

from config import resolver_diretorio_bundle
from presentation.desktop.toolbar_window import ToolbarWindow


class _LoadingSplash(QWidget):
    """Tela minima de carregamento exibida antes da toolbar."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.setWindowTitle('PlayGames Bot')
        self.setFixedSize(320, 110)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)


def run_desktop_app(*, setup_service, automation_service, startup_initializer=None) -> int:
    """Sobe a aplicacao Qt principal."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('PlayGames Bot')
    icon_path = resolver_diretorio_bundle() / 'assets' / 'app_icon.png'
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    splash = _LoadingSplash('Carregando OCR...')
    if app.windowIcon().isNull() is False:
        splash.setWindowIcon(app.windowIcon())
    splash.show()
    app.processEvents()

    if startup_initializer is not None:
        try:
            startup_initializer()
        except Exception as exc:
            splash.close()
            QMessageBox.critical(
                None,
                'Falha ao iniciar OCR',
                f'Nao foi possivel preparar o OCR antes de abrir o app.\n\nDetalhes: {exc}',
            )
            return 1

    settings = setup_service.load_settings()
    try:
        target_window = setup_service.find_target_window(settings, activate=False)
    except Exception as exc:
        splash.close()
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
    splash.close()
    window.show()
    return app.exec()
