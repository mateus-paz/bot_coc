"""Toolbar beta acoplada a janela do Clash of Clans."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from presentation.desktop.toolbar_geometry import calculate_toolbar_geometry
from presentation.desktop.toolbar_state import resolve_toolbar_control_state


CV_PROFILES = (
    ('CV13', 'cv_13'),
    ('CV14', 'cv_14'),
    ('CV17', 'cv_17'),
)


class ToolbarWindow(QWidget):
    """Barra compacta independente e sempre visivel em primeiro plano."""

    def __init__(
        self,
        *,
        setup_service,
        automation_service,
        settings,
        target_window,
    ) -> None:
        super().__init__()
        self.setup_service = setup_service
        self.automation_service = automation_service
        self.settings = settings
        self.target_window_id = target_window.window_id
        self._missing_window_checks = 0
        self._closing = False
        self._last_error_message = ''
        self._drag_offset: QPoint | None = None

        if self.target_window_id is None:
            raise ValueError('A janela alvo nao possui identificador nativo.')

        self.setWindowTitle('PlayGames Bot Beta')
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setObjectName('betaToolbar')
        self._build_ui()
        self._apply_styles()
        self._set_initial_geometry(target_window)
        self._refresh_status()

        self.target_timer = QTimer(self)
        self.target_timer.timeout.connect(self._poll_target_window)
        self.target_timer.start(250)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start(400)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 7, 8, 7)
        root.setSpacing(7)

        self.cv_combo = QComboBox()
        for label, profile in CV_PROFILES:
            self.cv_combo.addItem(label, profile)
        selected_profile = self.settings.cv_profile or 'cv_13'
        selected_index = self.cv_combo.findData(selected_profile)
        self.cv_combo.setCurrentIndex(max(0, selected_index))
        self.cv_combo.currentIndexChanged.connect(self._save_selected_profile)

        self.start_button = QPushButton('Start')
        self.pause_button = QPushButton('Pause')
        self.stop_button = QPushButton('Stop')
        self.pin_button = QPushButton('Pin')
        self.pin_button.setCheckable(True)
        self.pin_button.setToolTip('Bloquear a posicao da barra')
        self.version_label = QLabel('Beta version 0.0.1')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cv_combo.setFixedWidth(68)
        for button in (
            self.start_button,
            self.pause_button,
            self.stop_button,
            self.pin_button,
        ):
            button.setFixedWidth(58)
        self.version_label.setFixedWidth(130)

        self.start_button.clicked.connect(self._handle_start)
        self.pause_button.clicked.connect(self._handle_pause)
        self.stop_button.clicked.connect(self._handle_stop)
        self.pin_button.toggled.connect(self._handle_pin_toggled)

        root.addWidget(self.cv_combo)
        root.addWidget(self.start_button)
        root.addWidget(self.pause_button)
        root.addWidget(self.stop_button)
        root.addWidget(self.pin_button)
        root.addWidget(self.version_label, stretch=1)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget#betaToolbar {
                background: #f3f3f3;
                border: 3px solid #707070;
            }
            QComboBox, QPushButton {
                min-height: 30px;
                padding: 0 5px;
                color: #171717;
                background: #ffffff;
                border: 1px solid #8a8a8a;
                border-radius: 3px;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover, QPushButton:hover {
                border-color: #3b82f6;
            }
            QPushButton:checked {
                color: #ffffff;
                background: #2563eb;
                border-color: #1d4ed8;
            }
            QPushButton:disabled, QComboBox:disabled {
                color: #8b8b8b;
                background: #dedede;
            }
            QComboBox QAbstractItemView {
                color: #171717;
                background: #ffffff;
                selection-color: #ffffff;
                selection-background-color: #2563eb;
                border: 1px solid #8a8a8a;
                outline: 0;
            }
            QLabel {
                color: #202020;
                font-size: 12px;
                font-weight: 600;
            }
            """
        )

    def _handle_pin_toggled(self, pinned: bool) -> None:
        self.pin_button.setToolTip(
            'Posicao bloqueada' if pinned else 'Bloquear a posicao da barra'
        )
        self._drag_offset = None

    def _selected_profile(self) -> str:
        return str(self.cv_combo.currentData())

    def _save_selected_profile(self) -> None:
        selected_profile = self._selected_profile()
        if self.settings.cv_profile == selected_profile:
            return
        self.settings = replace(self.settings, cv_profile=selected_profile)
        try:
            self.setup_service.save_settings(self.settings)
        except Exception as exc:
            self._show_error(str(exc))

    def _handle_start(self) -> None:
        try:
            self._save_selected_profile()
            if not self.setup_service.activate_target_window(self.target_window_id):
                self._show_error('Nao foi possivel colocar o Clash of Clans em primeiro plano.')
                return
            if not self.automation_service.start():
                self._show_error('A automacao ja esta em execucao.')
                return
            QTimer.singleShot(50, self._activate_target_window)
        except Exception as exc:
            self._show_error(str(exc))
        self._refresh_status()

    def _activate_target_window(self) -> None:
        if not self.setup_service.activate_target_window(self.target_window_id):
            self._show_error('Nao foi possivel colocar o Clash of Clans em primeiro plano.')

    def _handle_pause(self) -> None:
        if not self.automation_service.pause():
            self._show_error('Nenhuma automacao em execucao para interromper.')
        self._refresh_status()

    def _handle_stop(self) -> None:
        if not self.automation_service.stop():
            self._show_error('Nenhuma automacao em execucao para parar.')
        self._refresh_status()

    def _show_error(self, message: str) -> None:
        if not message or message == self._last_error_message:
            return
        self._last_error_message = message
        QMessageBox.critical(self, 'PlayGames Bot', message)

    def _refresh_status(self) -> None:
        status = self.automation_service.status()
        labels = {
            'idle': 'Parado',
            'running': 'Executando',
            'paused': 'Pausado',
            'stopping': 'Encerrando',
            'stopped': 'Parado',
            'error': 'Erro',
        }
        status_label = labels.get(status.state, status.state)
        status_colors = {
            'idle': '#4b5563',
            'running': '#15803d',
            'paused': '#b45309',
            'stopping': '#b45309',
            'stopped': '#4b5563',
            'error': '#b91c1c',
        }
        self.version_label.setText('Beta version 0.0.1')
        self.version_label.setStyleSheet(
            f"color: {status_colors.get(status.state, '#202020')};"
            'font-size: 12px; font-weight: 600;'
        )
        tooltip = f'Status: {status_label}'
        if status.last_error:
            tooltip = f'{tooltip}\n{status.last_error}'
        self.version_label.setToolTip(tooltip)

        controls = resolve_toolbar_control_state(status)
        self.start_button.setEnabled(controls.can_start)
        self.pause_button.setEnabled(controls.can_pause)
        self.stop_button.setEnabled(controls.can_stop)
        self.cv_combo.setEnabled(controls.can_change_profile)

        if status.last_error:
            self._show_error(status.last_error)

    def _poll_target_window(self) -> None:
        try:
            target_window = self.setup_service.inspect_target_window(self.target_window_id)
        except Exception:
            target_window = None
        if target_window is None:
            self._missing_window_checks += 1
            if self._missing_window_checks >= 3:
                self._closing = True
                self.close()
            return

        self._missing_window_checks = 0

    def _set_initial_geometry(self, target_window) -> None:
        """Posiciona a barra uma vez; depois o usuario controla sua posicao."""
        bounds = target_window.bounds
        if bounds.width <= 0 or bounds.height <= 0:
            return
        geometry = calculate_toolbar_geometry(bounds)
        self.setGeometry(
            geometry.left,
            geometry.top,
            geometry.width,
            geometry.height,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Inicia o arraste quando a barra nao esta fixada."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.pin_button.isChecked()
        ):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move a janela livremente enquanto o botao esquerdo estiver pressionado."""
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and not self.pin_button.isChecked()
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Para o worker ao fechar manualmente ou junto com o Clash."""
        self._closing = True
        self.automation_service.stop()
        super().closeEvent(event)
