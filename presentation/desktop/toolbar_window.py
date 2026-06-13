"""Toolbar beta acoplada a janela do Clash of Clans."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from config import resolver_diretorio_bundle
from presentation.desktop.global_hotkeys import GlobalHotkeyManager, VK_F1, VK_F2, VK_F3
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
        global_hotkey_manager: GlobalHotkeyManager | None = None,
    ) -> None:
        super().__init__()
        self.setup_service = setup_service
        self.automation_service = automation_service
        self.settings = settings
        self.global_hotkey_manager = global_hotkey_manager or GlobalHotkeyManager(
            QApplication.instance()
        )
        self.target_window_id = target_window.window_id
        self._missing_window_checks = 0
        self._closing = False
        self._stop_requested_by_exit = False
        self._last_error_message = ''
        self._drag_offset: QPoint | None = None
        self._fallback_shortcuts: list[QShortcut] = []

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
        root.setContentsMargins(6, 5, 6, 5)
        root.setSpacing(5)

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
        self._apply_action_icons()
        self.version_label = QLabel('Beta version 0.0.1')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cv_combo.setFixedWidth(68)
        self.start_button.setFixedSize(34, 30)
        self.pause_button.setFixedSize(38, 30)
        self.stop_button.setFixedSize(38, 30)
        self.pin_button.setFixedSize(40, 30)
        self.version_label.setFixedWidth(116)

        self.start_button.clicked.connect(self._handle_start)
        self.pause_button.clicked.connect(self._handle_pause)
        self.stop_button.clicked.connect(self._handle_stop)
        self.pin_button.toggled.connect(self._handle_pin_toggled)
        self._configure_shortcuts()

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
            QPushButton[iconOnly="true"] {
                padding: 0;
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

    def _asset_icon(self, file_name: str) -> QIcon:
        icon_path = resolver_diretorio_bundle() / 'assets' / file_name
        if not icon_path.exists():
            return QIcon()
        return QIcon(str(icon_path))

    def _apply_action_icons(self) -> None:
        start_icon = self._asset_icon('toolbar_start.svg')
        pause_icon = self._asset_icon('toolbar_pause.svg')
        stop_icon = self._asset_icon('toolbar_stop.svg')
        pin_off_icon = self._asset_icon('toolbar_pin_off.svg')
        pin_on_icon = self._asset_icon('toolbar_pin_on.svg')
        self.start_button.setIcon(start_icon)
        if not start_icon.isNull():
            self.start_button.setText('')
            self.start_button.setProperty('iconOnly', True)
        self.start_button.setToolTip('Iniciar (F1)')
        self.pause_button.setIcon(pause_icon)
        if not pause_icon.isNull():
            self.pause_button.setText('')
            self.pause_button.setProperty('iconOnly', True)
        self.pause_button.setToolTip('Pausar (F2)')
        self.stop_button.setIcon(stop_icon)
        if not stop_icon.isNull():
            self.stop_button.setText('')
            self.stop_button.setProperty('iconOnly', True)
        self.stop_button.setToolTip('Encerrar app (F3)')
        self.pin_button.setIcon(pin_off_icon)
        if not pin_off_icon.isNull() or not pin_on_icon.isNull():
            self.pin_button.setText('')
            self.pin_button.setProperty('iconOnly', True)
        self._pin_icons = {
            False: pin_off_icon,
            True: pin_on_icon,
        }

    def _configure_shortcuts(self) -> None:
        shortcut_specs = (
            (1, VK_F1, 'F1', self.start_button),
            (2, VK_F2, 'F2', self.pause_button),
            (3, VK_F3, 'F3', self.stop_button),
        )
        for hotkey_id, virtual_key, key_name, button in shortcut_specs:
            registered = self.global_hotkey_manager.register(
                hotkey_id,
                virtual_key,
                lambda target=button: self._trigger_button(target),
            )
            if registered:
                continue
            shortcut = QShortcut(QKeySequence(key_name), self)
            shortcut.activated.connect(lambda target=button: self._trigger_button(target))
            self._fallback_shortcuts.append(shortcut)

    def _trigger_button(self, button: QPushButton) -> None:
        if button.isEnabled():
            button.click()

    def _handle_pin_toggled(self, pinned: bool) -> None:
        pin_icon = self._pin_icons[pinned]
        if not pin_icon.isNull():
            self.pin_button.setIcon(pin_icon)
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
        self._stop_requested_by_exit = True
        self.automation_service.stop()
        self.close()

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
        self.global_hotkey_manager.unregister_all()
        if not self._stop_requested_by_exit:
            self.automation_service.stop()
        super().closeEvent(event)
